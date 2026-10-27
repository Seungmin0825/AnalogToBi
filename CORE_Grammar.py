"""
Shared vocabulary, grammar state machine, and grammar-guided batch decoding.

This is the grammar of the paper (NeurIPS 2026). A state machine keyed on the
last two tokens masks every step so the walk stays a well-formed bipartite
circuit, and TRUNCATE is unmasked only at VSS once every device pin is connected
and every internal net joins two devices (ERC tests 2 and 4). Validity is
judged afterwards on all four ERC tests (METRIC_Validity.py), which is the
definition of a valid circuit.

generate_with_masking_batch_traced() records WHY each sequence terminated
('valid' / 'max_length' / 'dead_end') and returns every sequence trimmed at its
termination point. Device selection and seeding are left to the caller.
"""


import torch
from torch.nn import functional as F

# Hyperparameters (must match TRAIN_GPT.py and the shipped checkpoint)
block_size = 1024
n_embd = 384
n_head = 6
n_layer = 6
dropout = 0.2

# Vocabulary, defined once in CORE_Vocab.py
from CORE_Vocab import (
    vocab_tokens, stoi, itos, vocab_size, circuit_type_tokens,
    mosfet_tokens, bjt_tokens, resistor_tokens, capacitor_tokens,
    inductor_tokens, diode_tokens, all_device_tokens,
    mosfet_edges, bjt_edges, diode_edges, all_edge_types,
    net_tokens, port_tokens, all_net_port_tokens,
)
devices = vocab_tokens

encode = lambda s: [stoi[c] for c in s]
decode = lambda l: '->'.join([itos[i] for i in l]) + '->'

# =========================
# Precompute Index Sets
# =========================

# Convert token sets to index sets
mosfet_edge_indices = {stoi[e] for e in mosfet_edges}
bjt_edge_indices = {stoi[e] for e in bjt_edges}
diode_edge_indices = {stoi[e] for e in diode_edges}
passive_edge_indices = {stoi['R_C'], stoi['C_C'], stoi['L_C']}
all_edge_indices = mosfet_edge_indices | bjt_edge_indices | diode_edge_indices | passive_edge_indices

mosfet_device_indices = {stoi[d] for d in mosfet_tokens}
bjt_device_indices = {stoi[d] for d in bjt_tokens}
resistor_device_indices = {stoi[d] for d in resistor_tokens}
capacitor_device_indices = {stoi[d] for d in capacitor_tokens}
inductor_device_indices = {stoi[d] for d in inductor_tokens}
diode_device_indices = {stoi[d] for d in diode_tokens}
all_device_indices = (mosfet_device_indices | bjt_device_indices | resistor_device_indices | 
                     capacitor_device_indices | inductor_device_indices | diode_device_indices)

net_port_indices = {stoi[n] for n in all_net_port_tokens}
circuit_type_indices = {stoi[t] for t in circuit_type_tokens}


external_port_indices = {stoi[p] for p in port_tokens + ['VSS', 'VDD']}
internal_net_indices = {stoi[n] for n in net_tokens}

vss_vdd_indices = {stoi['VSS'], stoi['VDD']}
truncate_idx = stoi['TRUNCATE']

# Pin extraction mapping for edges (index -> pins)
edge_to_pins = {}
for edge in mosfet_edges + bjt_edges + diode_edges:
    if edge.startswith('M_'):
        edge_to_pins[stoi[edge]] = set(edge[2:])  # M_BD -> {'B', 'D'}
    elif edge.startswith('B_'):
        edge_to_pins[stoi[edge]] = set(edge[2:])  # B_BC -> {'B', 'C'}
    elif edge.startswith('D_'):
        edge_to_pins[stoi[edge]] = set(edge[2:])  # D_NP -> {'N', 'P'}
for passive in ['R_C', 'C_C', 'L_C']:
    edge_to_pins[stoi[passive]] = {'C'}

# Device type classification (index -> type)
device_type_map = {}
for idx in mosfet_device_indices:
    device_type_map[idx] = 'MOSFET'
for idx in bjt_device_indices:
    device_type_map[idx] = 'BJT'
for idx in diode_device_indices:
    device_type_map[idx] = 'DIODE'
for idx in resistor_device_indices:
    device_type_map[idx] = 'R'
for idx in capacitor_device_indices:
    device_type_map[idx] = 'C'
for idx in inductor_device_indices:
    device_type_map[idx] = 'L'


def track_device_pins_fast(sequence_indices):
    """
    Track which pins have been used for each device (index-based)
    
    Args:
        sequence_indices: list of token indices
    
    Returns:
        device_pins: dict {device_idx: set(pins_used)}
    """
    device_pins = {}
    
    i = 0
    while i < len(sequence_indices):
        token_idx = sequence_indices[i]
        
        # Check if it's a device (O(1) set lookup)
        if token_idx in all_device_indices:
            # Initialize if first time seeing this device
            if token_idx not in device_pins:
                device_pins[token_idx] = set()
            
            # Next token should be edge type
            if i + 1 < len(sequence_indices):
                edge_idx = sequence_indices[i + 1]
                
                # Get pins from precomputed mapping
                if edge_idx in edge_to_pins:
                    device_pins[token_idx].update(edge_to_pins[edge_idx])
        
        i += 1
    
    return device_pins


def track_net_connections_fast(sequence_indices):
    """
    Track which unique devices are connected to each internal net
    Also track which internal nets have appeared in the sequence
    
    Args:
        sequence_indices: list of token indices
    
    Returns:
        (net_connections, internal_nets_seen): 
            net_connections - dict {net_idx: set(device_indices)}
            internal_nets_seen - set of internal net indices that appeared
    """
    net_connections = {}
    internal_nets_seen = set()
    
    i = 0
    while i < len(sequence_indices) - 2:
        token1_idx = sequence_indices[i]
        token2_idx = sequence_indices[i + 1]
        token3_idx = sequence_indices[i + 2]
        
        # Pattern 1: device - edge - net
        if (token1_idx in all_device_indices and 
            token2_idx in all_edge_indices and 
            token3_idx in internal_net_indices):
            internal_nets_seen.add(token3_idx)
            if token3_idx not in net_connections:
                net_connections[token3_idx] = set()
            net_connections[token3_idx].add(token1_idx)
        
        # Pattern 2: net - edge - device
        if (token1_idx in internal_net_indices and 
            token2_idx in all_edge_indices and 
            token3_idx in all_device_indices):
            internal_nets_seen.add(token1_idx)
            if token1_idx not in net_connections:
                net_connections[token1_idx] = set()
            net_connections[token1_idx].add(token3_idx)
        
        i += 1
    
    return net_connections, internal_nets_seen


def track_device_edge_nets(sequence_indices):
    """
    Track which nets are connected to each (device, edge) pair
    Used to enforce unique net connection per device-edge combination
    
    Args:
        sequence_indices: list of token indices
    
    Returns:
        device_edge_nets: dict {(device_idx, edge_idx): net_idx or None}
    """
    device_edge_nets = {}
    
    i = 0
    while i < len(sequence_indices) - 2:
        token1_idx = sequence_indices[i]
        token2_idx = sequence_indices[i + 1]
        token3_idx = sequence_indices[i + 2]
        
        # Pattern 1: device - edge - net
        if (token1_idx in all_device_indices and 
            token2_idx in all_edge_indices and 
            token3_idx in net_port_indices):
            key = (token1_idx, token2_idx)
            if key not in device_edge_nets:
                device_edge_nets[key] = token3_idx
        
        # Pattern 2: net - edge - device (reverse)
        if (token1_idx in net_port_indices and 
            token2_idx in all_edge_indices and 
            token3_idx in all_device_indices):
            key = (token3_idx, token2_idx)
            if key not in device_edge_nets:
                device_edge_nets[key] = token1_idx
        
        i += 1
    
    return device_edge_nets


def track_passive_net_count(sequence_indices):
    """
    Track how many different nets each passive component is connected to
    Passives (R/C/L) are 2-terminal devices and can only connect to exactly 2 different nets
    
    Args:
        sequence_indices: list of token indices
    
    Returns:
        passive_net_count: dict {device_idx: set(net_indices)}
    """
    from collections import defaultdict
    passive_net_count = defaultdict(set)
    
    i = 0
    while i < len(sequence_indices) - 2:
        token1_idx = sequence_indices[i]
        token2_idx = sequence_indices[i + 1]
        token3_idx = sequence_indices[i + 2]
        
        # Pattern 1: device - edge - net (passive device)
        if (token1_idx in all_device_indices and 
            token2_idx in passive_edge_indices and 
            token3_idx in net_port_indices):
            passive_net_count[token1_idx].add(token3_idx)
        
        # Pattern 2: net - edge - device (passive device)
        if (token1_idx in net_port_indices and 
            token2_idx in passive_edge_indices and 
            token3_idx in all_device_indices):
            passive_net_count[token3_idx].add(token1_idx)
        
        i += 1
    
    return passive_net_count


def track_diode_net_count(sequence_indices):
    """
    Track which nets each diode is connected to (across all edges)
    Diodes are 2-terminal devices: same edge can reconnect to same net, 
    but different edges must connect to different nets
    
    Args:
        sequence_indices: list of token indices
    
    Returns:
        diode_net_count: dict {device_idx: set(net_indices)}
    """
    from collections import defaultdict
    diode_net_count = defaultdict(set)
    
    i = 0
    while i < len(sequence_indices) - 2:
        token1_idx = sequence_indices[i]
        token2_idx = sequence_indices[i + 1]
        token3_idx = sequence_indices[i + 2]
        
        # Pattern 1: device - edge - net (diode device)
        if (token1_idx in all_device_indices and 
            token2_idx in diode_edge_indices and 
            token3_idx in net_port_indices):
            diode_net_count[token1_idx].add(token3_idx)
        
        # Pattern 2: net - edge - device (diode device)
        if (token1_idx in net_port_indices and 
            token2_idx in diode_edge_indices and 
            token3_idx in all_device_indices):
            diode_net_count[token3_idx].add(token1_idx)
        
        i += 1
    
    return diode_net_count


def track_device_pin_nets(sequence_indices):
    """
    Track which nets each device pin is connected to
    For MOSFET/BJT: same pin cannot connect to same net via different edges
    Example: NM1->M_GD->NET1 means D pin connected to NET1
             Later NET1->M_D->NM1 should be blocked (D already connected to NET1)
    
    Args:
        sequence_indices: list of token indices
    
    Returns:
        device_pin_nets: dict {(device_idx, pin): set(net_indices)}
    """
    from collections import defaultdict
    device_pin_nets = defaultdict(set)
    
    i = 0
    while i < len(sequence_indices) - 2:
        token1_idx = sequence_indices[i]
        token2_idx = sequence_indices[i + 1]
        token3_idx = sequence_indices[i + 2]
        
        # Pattern 1: device - edge - net
        if (token1_idx in all_device_indices and 
            token2_idx in all_edge_indices and 
            token3_idx in net_port_indices):
            # Get pins from this edge
            if token2_idx in edge_to_pins:
                pins = edge_to_pins[token2_idx]
                for pin in pins:
                    device_pin_nets[(token1_idx, pin)].add(token3_idx)
        
        # Pattern 2: net - edge - device (reverse)
        if (token1_idx in net_port_indices and 
            token2_idx in all_edge_indices and 
            token3_idx in all_device_indices):
            # Get pins from this edge
            if token2_idx in edge_to_pins:
                pins = edge_to_pins[token2_idx]
                for pin in pins:
                    device_pin_nets[(token3_idx, pin)].add(token1_idx)
        
        i += 1
    
    return device_pin_nets


def check_all_nets_connected(net_connections, internal_nets_seen):
    """
    Check if all internal nets that appeared in sequence have at least 2 unique device connections    
    Args:
        net_connections: dict {net_idx: set(device_indices)}
        internal_nets_seen: set of internal net indices that have appeared
    
    Returns:
        True if all seen internal nets have >= 2 unique device connections
    """
    for net_idx in internal_nets_seen:
        if len(net_connections.get(net_idx, set())) < 2:
            return False
    return True


def check_all_pins_used_fast(device_pins):
    """
    Check if all devices have used all required pins
    
    Returns:
        True if all devices are complete
    """
    for device_idx, pins_used in device_pins.items():
        device_type = device_type_map.get(device_idx)
        
        if device_type == 'MOSFET':
            required = {'D', 'G', 'S', 'B'}
            if not required.issubset(pins_used):
                return False
        elif device_type == 'BJT':
            required = {'B', 'C', 'E'}
            if not required.issubset(pins_used):
                return False
        elif device_type == 'DIODE':
            required = {'P', 'N'}
            if not required.issubset(pins_used):
                return False
        elif device_type in ['R', 'C', 'L']:
            if 'C' not in pins_used:
                return False
    
    return True


def get_allowed_tokens_fast(prev2_idx, prev1_idx, device_pins, net_connections, internal_nets_seen, device_edge_nets, passive_net_count, diode_net_count, device_pin_nets, seq_length):
    """
    Get allowed token indices based on last 2 tokens using the state machine
    
    State Transitions:
    State 1: Circuit_Type - VSS -> Edge (circuit type controlled start)
    State 2: Net - Edge -> Device (device compatible edge token allowed)
    State 3: Edge - Device -> Edge (net type compatible edge token allowed)
    State 4: Device - Edge -> Net (bipartite pattern enforcement)
    State 5: Edge - Net -> Edge (if floating net remained)
    State 6: Edge - VSS -> TRUNCATE (generation complete after ERC check)
    
    Args:
        prev2_idx: second-to-last token index (or None)
        prev1_idx: last token index (or None)
        device_pins: dict from track_device_pins_fast
        net_connections: dict from track_net_connections_fast
        internal_nets_seen: set of internal nets that have appeared
        device_edge_nets: dict from track_device_edge_nets
        seq_length: current sequence length
    
    Returns:
        list of allowed token indices
    """
    if seq_length == 0:
        return list(circuit_type_indices)
    
    if seq_length == 1:
        return list(vss_vdd_indices)
        
    # State 1: Circuit_Type - VSS -> Edge (circuit type controlled start)
    if prev2_idx in circuit_type_indices and prev1_idx in vss_vdd_indices:
        return list(all_edge_indices)
    
    # State 2: Net - Edge -> Device (device compatible edge token allowed)
    elif prev1_idx in all_edge_indices and prev2_idx in net_port_indices:
        # Get base candidates matching edge type
        if prev1_idx in mosfet_edge_indices:
            candidates = set(mosfet_device_indices)
        elif prev1_idx in bjt_edge_indices:
            candidates = set(bjt_device_indices)
        elif prev1_idx in diode_edge_indices:
            candidates = set(diode_device_indices)
        elif prev1_idx == stoi['R_C']:
            candidates = set(resistor_device_indices)
        elif prev1_idx == stoi['C_C']:
            candidates = set(capacitor_device_indices)
        elif prev1_idx == stoi['L_C']:
            candidates = set(inductor_device_indices)
        else:
            candidates = set()
        
        # Exclude devices already connected via this edge to different nets
        allowed_devices = []
        for dev in candidates:
            device_edge_key = (dev, prev1_idx)
            
            # Check if device is passive
            dev_type = device_type_map.get(dev)
            if dev_type in ['R', 'C', 'L']:
                # Passive: 2-terminal device, max 2 different nets
                net_count = len(passive_net_count.get(dev, set()))
                if net_count >= 2:
                    # Already connected to 2 nets - fully used, skip
                    continue
                elif device_edge_key in device_edge_nets:
                    # Has 1 connection
                    existing_net = device_edge_nets[device_edge_key]
                    if existing_net != prev2_idx:
                        # Different net - allow (NET1-R1 exists, NET2->R_C->R1 OK)
                        allowed_devices.append(dev)
                    # else: same net - skip (NET1-R1 exists, NET1->R_C->R1 NOT OK)
                else:
                    # No connection yet - allow
                    allowed_devices.append(dev)
            elif dev_type == 'DIODE':
                # Diode: 2-terminal with multiple edges
                # Same edge + same net: OK (reconnection)
                # Same edge + different net: NOT OK
                # Different edge + same net: NOT OK
                # Different edge + different net: OK
                if device_edge_key in device_edge_nets:
                    # This specific edge has a connection
                    existing_net = device_edge_nets[device_edge_key]
                    if existing_net == prev2_idx:
                        # Same edge, same net - allow reconnection
                        allowed_devices.append(dev)
                    # else: same edge, different net - exclude
                else:
                    # Different edge - check if current net already used
                    connected_nets = diode_net_count.get(dev, set())
                    if prev2_idx not in connected_nets:
                        # Different edge, different net - allow
                        allowed_devices.append(dev)
                    # else: different edge, same net - exclude
            else:
                # Active device logic (MOSFET, BJT)
                # Same edge + same net: OK (reconnection)
                # Same edge + different net: NOT OK
                # Different edge + pins already on different net: NOT OK
                # Different edge + pins on same net or unused: OK
                if device_edge_key in device_edge_nets:
                    # Same edge already connected
                    existing_net = device_edge_nets[device_edge_key]
                    if existing_net == prev2_idx:
                        # Same edge + same net - allow reconnection
                        allowed_devices.append(dev)
                    # else: same edge + different net - exclude
                else:
                    # Different edge - check if any of its pins already connected to DIFFERENT net
                    if prev1_idx in edge_to_pins:
                        pins_in_edge = edge_to_pins[prev1_idx]
                        # Check if any pin in this edge is already connected to a DIFFERENT net
                        has_conflict = False
                        for pin in pins_in_edge:
                            pin_nets = device_pin_nets.get((dev, pin), set())
                            # If pin is connected to other nets (not current net), conflict
                            other_nets = pin_nets - {prev2_idx}
                            if other_nets:
                                # This pin already connected to different net - conflict
                                has_conflict = True
                                break
                        
                        if not has_conflict:
                            # No conflict - allow (pins unused or already on same net)
                            allowed_devices.append(dev)
                    else:
                        # No pin info - allow (fallback)
                        allowed_devices.append(dev)
        
        return allowed_devices if allowed_devices else list(candidates)
    
    # State 3: Edge - Device -> Edge (net type compatible edge token allowed)
    elif prev1_idx in all_device_indices and prev2_idx in all_edge_indices:
        device_type = device_type_map.get(prev1_idx)
        if device_type == 'MOSFET':
            return list(mosfet_edge_indices)
        elif device_type == 'BJT':
            return list(bjt_edge_indices)
        elif device_type == 'DIODE':
            return list(diode_edge_indices)
        elif device_type == 'R':
            return [stoi['R_C']]
        elif device_type == 'C':
            return [stoi['C_C']]
        elif device_type == 'L':
            return [stoi['L_C']]
    
    # State 4: Device - Edge -> Net (bipartite pattern enforcement)
    elif prev1_idx in all_edge_indices and prev2_idx in all_device_indices:
        device_edge_key = (prev2_idx, prev1_idx)
        
        # Check if device is passive
        dev_type = device_type_map.get(prev2_idx)
        if dev_type in ['R', 'C', 'L']:
            # Passive: 2-terminal device, max 2 different nets
            connected_nets = passive_net_count.get(prev2_idx, set())
            net_count = len(connected_nets)
            
            if net_count >= 2:
                # Already connected to 2 nets - only allow those 2 nets (reuse)
                return list(connected_nets)
            elif net_count == 1:
                # Has 1 connection - exclude that net (must use different net for 2nd terminal)
                existing_net = list(connected_nets)[0]
                all_nets = list(net_port_indices)
                return [net for net in all_nets if net != existing_net]
            else:
                # No connection yet - allow all nets
                return list(net_port_indices)
        elif dev_type == 'DIODE':
            # Diode: 2-terminal with multiple edges (D_P, D_N, etc.)
            # Same edge can reconnect to same net (OK)
            # Different edge must connect to different net (exclude already connected nets)
            if device_edge_key in device_edge_nets:
                # This specific edge already connected - only allow that net
                existing_net = device_edge_nets[device_edge_key]
                return [existing_net]
            else:
                # Different edge - exclude nets already connected via other edges
                connected_nets = diode_net_count.get(prev2_idx, set())
                if connected_nets:
                    all_nets = list(net_port_indices)
                    return [net for net in all_nets if net not in connected_nets]
                else:
                    # No connection yet - allow all nets
                    return list(net_port_indices)
        else:
            # Active device logic (MOSFET, BJT)
            # Same edge + same net: OK (reconnection)
            # Same edge + different net: NOT OK  
            # Different edge: check pins - if pins already on different net, exclude that net
            if device_edge_key in device_edge_nets:
                # Same edge already connected - only allow that net
                existing_net = device_edge_nets[device_edge_key]
                return [existing_net]
            else:
                # Different edge - check which nets this edge's pins are already connected to
                if prev1_idx in edge_to_pins:
                    pins_in_edge = edge_to_pins[prev1_idx]
                    
                    # Collect all nets that any of these pins are connected to
                    connected_nets = set()
                    for pin in pins_in_edge:
                        pin_nets = device_pin_nets.get((prev2_idx, pin), set())
                        connected_nets.update(pin_nets)
                    
                    if connected_nets:
                        # Pins already connected to some nets - only allow those nets (reuse)
                        return list(connected_nets)
                    else:
                        # Pins not yet connected - allow all nets
                        return list(net_port_indices)
                else:
                    return list(net_port_indices)
    
    # State 5 & 6: Edge - Net(VSS) -> Edge
    elif prev1_idx in net_port_indices and prev2_idx in all_edge_indices:
        allowed = list(all_edge_indices)
        
        if (prev1_idx == stoi['VSS'] and 
            check_all_pins_used_fast(device_pins) and 
            check_all_nets_connected(net_connections, internal_nets_seen)):
            allowed.append(truncate_idx)
        
        return allowed
    
    # Fallback: allow everything except circuit types
    return [i for i in range(vocab_size) if i not in circuit_type_indices]


# =========================================================================
# Decoding, with the reason every walk stopped
# =========================================================================


REASON_VALID = 'valid'            # TRUNCATE sampled (grammar-enforced completion satisfied)
REASON_MAX_LENGTH = 'max_length'  # sequence reached max_length before completing
REASON_DEAD_END = 'dead_end'      # grammar mask left no allowed next token



def generate_with_masking_batch_traced(model, contexts, max_new_tokens=1024, max_length=1020,
                                       temperature=0.7, dead_end_hook=None):
    """
    Grammar-guided batch decoding. Every sequence is returned (trimmed at its
    termination point) together with the reason it terminated: REASON_VALID,
    REASON_MAX_LENGTH, or REASON_DEAD_END.

    dead_end_hook(b, step, sequence_indices) is called at each dead-end event.

    Returns:
        sequences: list of B token-index lists (valid ones end with TRUNCATE)
        reasons:   list of B termination reasons
    """
    batch_size = contexts.size(0)
    idx = contexts
    finished = torch.zeros(batch_size, dtype=torch.bool, device=contexts.device)
    reasons = ['running'] * batch_size
    finish_lens = [None] * batch_size

    # Initialize per-sequence incremental tracking structures
    batch_device_pins = [track_device_pins_fast(contexts[b].tolist()) for b in range(batch_size)]

    batch_net_connections = []
    batch_internal_nets_seen = []
    for b in range(batch_size):
        net_conns, nets_seen = track_net_connections_fast(contexts[b].tolist())
        batch_net_connections.append(net_conns)
        batch_internal_nets_seen.append(nets_seen)

    batch_device_edge_nets = [track_device_edge_nets(contexts[b].tolist()) for b in range(batch_size)]
    batch_passive_net_count = [track_passive_net_count(contexts[b].tolist()) for b in range(batch_size)]
    batch_diode_net_count = [track_diode_net_count(contexts[b].tolist()) for b in range(batch_size)]
    batch_device_pin_nets = [track_device_pin_nets(contexts[b].tolist()) for b in range(batch_size)]

    for step in range(max_new_tokens):
        # Termination condition 2: max sequence length exceeded
        for b in range(batch_size):
            if not finished[b] and idx[b].size(0) >= max_length:
                finished[b] = True
                reasons[b] = REASON_MAX_LENGTH
                finish_lens[b] = idx[b].size(0)

        if finished.all():
            break

        idx_cond = idx[:, -model.block_size:]
        with torch.no_grad():
            logits, _ = model(idx_cond)
            logits = logits[:, -1, :]
            logits = logits / temperature

        mask = torch.full((vocab_size,), float('-inf'), device=logits.device, dtype=logits.dtype)

        for b in range(batch_size):
            if finished[b]:
                continue

            seq_len = idx[b].size(0)
            prev1_idx = idx[b, -1].item() if seq_len >= 1 else None
            prev2_idx = idx[b, -2].item() if seq_len >= 2 else None

            allowed_indices = get_allowed_tokens_fast(
                prev2_idx, prev1_idx,
                batch_device_pins[b], batch_net_connections[b], batch_internal_nets_seen[b],
                batch_device_edge_nets[b], batch_passive_net_count[b], batch_diode_net_count[b],
                batch_device_pin_nets[b], seq_len)

            # Termination condition 3: grammar dead-end (no valid next token)
            if len(allowed_indices) == 0:
                finished[b] = True
                reasons[b] = REASON_DEAD_END
                finish_lens[b] = seq_len
                if dead_end_hook is not None:
                    dead_end_hook(b, step, idx[b].tolist())
                continue

            mask.fill_(float('-inf'))
            mask[allowed_indices] = 0
            logits[b] = logits[b] + mask

        probs = F.softmax(logits, dim=-1)
        idx_next = torch.multinomial(probs, num_samples=1)  # (B, 1)

        # Incremental tracking updates
        for b in range(batch_size):
            if not finished[b]:
                new_token_idx = idx_next[b, 0].item()

                seq_len = idx[b].size(0)
                prev_token = idx[b, -1].item() if seq_len >= 1 else None
                prev2_token = idx[b, -2].item() if seq_len >= 2 else None

                # Pattern 1: net/port - edge - DEVICE (new device appears)
                if (prev2_token in net_port_indices and
                    prev_token in edge_to_pins and
                    new_token_idx in all_device_indices):
                    if new_token_idx not in batch_device_pins[b]:
                        batch_device_pins[b][new_token_idx] = set()
                    batch_device_pins[b][new_token_idx].update(edge_to_pins[prev_token])

                # Pattern 2: device - edge - (next will be net/port)
                elif (prev2_token in all_device_indices and
                      prev_token in edge_to_pins):
                    if prev2_token not in batch_device_pins[b]:
                        batch_device_pins[b][prev2_token] = set()
                    batch_device_pins[b][prev2_token].update(edge_to_pins[prev_token])

                # Update net_connections incrementally
                if (prev2_token in all_device_indices and
                    prev_token in all_edge_indices and
                    new_token_idx in internal_net_indices):
                    batch_internal_nets_seen[b].add(new_token_idx)
                    if new_token_idx not in batch_net_connections[b]:
                        batch_net_connections[b][new_token_idx] = set()
                    batch_net_connections[b][new_token_idx].add(prev2_token)

                if (prev2_token in internal_net_indices and
                    prev_token in all_edge_indices and
                    new_token_idx in all_device_indices):
                    batch_internal_nets_seen[b].add(prev2_token)
                    if prev2_token not in batch_net_connections[b]:
                        batch_net_connections[b][prev2_token] = set()
                    batch_net_connections[b][prev2_token].add(new_token_idx)

                # Update device_edge_nets incrementally
                # Pattern 1: device - edge - NET/PORT
                if (prev2_token in all_device_indices and
                    prev_token in all_edge_indices and
                    new_token_idx in net_port_indices):
                    device_edge_key = (prev2_token, prev_token)
                    if device_edge_key not in batch_device_edge_nets[b]:
                        batch_device_edge_nets[b][device_edge_key] = new_token_idx

                    if prev_token in passive_edge_indices:
                        if prev2_token not in batch_passive_net_count[b]:
                            batch_passive_net_count[b][prev2_token] = set()
                        batch_passive_net_count[b][prev2_token].add(new_token_idx)

                    if prev_token in diode_edge_indices:
                        if prev2_token not in batch_diode_net_count[b]:
                            batch_diode_net_count[b][prev2_token] = set()
                        batch_diode_net_count[b][prev2_token].add(new_token_idx)

                    if prev_token in edge_to_pins:
                        pins = edge_to_pins[prev_token]
                        for pin in pins:
                            pin_key = (prev2_token, pin)
                            if pin_key not in batch_device_pin_nets[b]:
                                batch_device_pin_nets[b][pin_key] = set()
                            batch_device_pin_nets[b][pin_key].add(new_token_idx)

                # Pattern 2: NET/PORT - edge - device
                if (prev2_token in net_port_indices and
                    prev_token in all_edge_indices and
                    new_token_idx in all_device_indices):
                    device_edge_key = (new_token_idx, prev_token)
                    if device_edge_key not in batch_device_edge_nets[b]:
                        batch_device_edge_nets[b][device_edge_key] = prev2_token

                    if prev_token in passive_edge_indices:
                        if new_token_idx not in batch_passive_net_count[b]:
                            batch_passive_net_count[b][new_token_idx] = set()
                        batch_passive_net_count[b][new_token_idx].add(prev2_token)

                    if prev_token in diode_edge_indices:
                        if new_token_idx not in batch_diode_net_count[b]:
                            batch_diode_net_count[b][new_token_idx] = set()
                        batch_diode_net_count[b][new_token_idx].add(prev2_token)

                    if prev_token in edge_to_pins:
                        pins = edge_to_pins[prev_token]
                        for pin in pins:
                            pin_key = (new_token_idx, pin)
                            if pin_key not in batch_device_pin_nets[b]:
                                batch_device_pin_nets[b][pin_key] = set()
                            batch_device_pin_nets[b][pin_key].add(prev2_token)

                # Termination condition 1: TRUNCATE (valid completion)
                if new_token_idx == truncate_idx:
                    finished[b] = True
                    reasons[b] = REASON_VALID
                    finish_lens[b] = seq_len + 1  # include the TRUNCATE token

        idx = torch.cat((idx, idx_next), dim=1)

    # Safety net: max_new_tokens exhausted without hitting any condition
    for b in range(batch_size):
        if reasons[b] == 'running':
            reasons[b] = REASON_MAX_LENGTH
            finish_lens[b] = idx[b].size(0)

    sequences = [idx[b].tolist()[:finish_lens[b]] for b in range(batch_size)]
    return sequences, reasons


REASON_ERC_FAIL = 'erc_fail'   # unmasked run: the model stopped, but ERC rejects it


def generate_free_batch(model, contexts, max_new_tokens=1024, max_length=1020,
                        temperature=0.7):
    """Sample with no grammar mask at all.

    Nothing constrains the tokens, so nothing guarantees the result is a circuit.
    A walk ends when the model itself emits TRUNCATE, or when it runs out of
    budget. Whether the finished sequence is actually valid is not knowable here
    and is decided afterwards by ERC: with the grammar, validity is enforced;
    here it is observed.
    """
    idx = contexts
    batch_size = contexts.size(0)
    finished = torch.zeros(batch_size, dtype=torch.bool, device=idx.device)
    reasons = ['running'] * batch_size
    finish_lens = [None] * batch_size

    for _ in range(max_new_tokens):
        for b in range(batch_size):
            if not finished[b] and idx[b].size(0) >= max_length:
                finished[b] = True
                reasons[b] = REASON_MAX_LENGTH
                finish_lens[b] = idx[b].size(0)
        if finished.all():
            break

        idx_cond = idx[:, -model.block_size:]
        with torch.no_grad():
            logits, _ = model(idx_cond)
            logits = logits[:, -1, :] / temperature

        probs = F.softmax(logits, dim=-1)
        idx_next = torch.multinomial(probs, num_samples=1)
        for b in range(batch_size):
            if not finished[b] and idx_next[b, 0].item() == truncate_idx:
                finished[b] = True
                reasons[b] = REASON_VALID     # provisional; ERC decides later
                finish_lens[b] = idx[b].size(0) + 1
        idx = torch.cat((idx, idx_next), dim=1)

    seqs = []
    for b in range(batch_size):
        n = finish_lens[b] if finish_lens[b] is not None else idx[b].size(0)
        if reasons[b] == 'running':
            reasons[b] = REASON_MAX_LENGTH
        seqs.append(idx[b, :n].tolist())
    return seqs, reasons


def sample_walks(model, circuit_token, n, batch_size, device,
                 max_new_tokens=1024, max_length=1020, temperature=0.7,
                 grammar=True, on_batch=None):
    """
    Sample n independent walks in batches of batch_size.

    on_batch, if given, is called with the reasons of every finished batch, so
    the caller can report progress.

    Returns:
        (sequences, reasons): parallel lists of length n
    """
    all_seqs, all_reasons = [], []
    ctx_row = [stoi[circuit_token], stoi['VSS']]
    while len(all_seqs) < n:
        cur = min(batch_size, n - len(all_seqs))
        contexts = torch.tensor([ctx_row] * cur, dtype=torch.long, device=device)
        if grammar:
            seqs, reasons = generate_with_masking_batch_traced(
                model, contexts, max_new_tokens=max_new_tokens, max_length=max_length,
                temperature=temperature)
        else:
            seqs, reasons = generate_free_batch(
                model, contexts, max_new_tokens=max_new_tokens,
                max_length=max_length, temperature=temperature)
        all_seqs.extend(seqs)
        all_reasons.extend(reasons)
        if on_batch is not None:
            on_batch(reasons)
    return all_seqs, all_reasons
