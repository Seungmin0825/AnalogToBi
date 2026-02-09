"""
Grammar-Guided Decoding for Analog Circuit Topology Generation

Generates device-level analog circuit topologies using a state machine-based grammar
that enforces bipartite graph structure and electrical validity constraints during
autoregressive generation. Implements masked token generation where only valid next
tokens are allowed at each decoding step.

State Machine (6 States):
State 1: Circuit_Type - VSS -> Edge (circuit type controlled start condition)
State 2: Net - Edge -> Device (device compatible edge token allowed)
State 3: Edge - Device -> Edge (net type compatible edge token allowed)  
State 4: Device - Edge -> Net (bipartite pattern enforcement)
State 5: Edge - Net -> Edge (if floating net remained)
State 6: Edge - VSS -> TRUNCATE (generation complete after ERC check)

The grammar ensures:
- Bipartite pattern: Device-Edge-Net-Edge-Device alternation
- Type compatibility: Device types match their edge types
- Complete connectivity: All device pins connected (e.g., S,G,D,B for MOSFETs)
- Valid internal nets: Each internal net connects at least 2 devices
- Terminal constraints: Passives connect to exactly 2 different nets

Incremental Tracking (No Full Rescan):
- Device pins used (ERC Test 2)
- Net connections per device (ERC Test 4)
- Device-edge-net pairs (prevent duplicate connections)
- Fast index-based operations (no string conversion)

Batch Generation:
- Parallel generation of multiple circuits
- Per-sequence validation and grammar enforcement
- Invalid sequences discarded (max_length exceeded or grammar violation)
- Output: Circuit-type-specific directories with token sequences

Supports 15 circuit types: Opamp, LDO, Bandgap_Ref, Power_converter, Oscillator,
Mirror, Mixer, Power_Amp, PLL, Filter, Comparator, Voltage_Regulator, 
Switched_Cap, ADC_DAC, General
"""

import torch
from torch.nn import functional as F
import numpy as np
import csv
import os
import sys
from Models.GPT import GPTLanguageModel

# Hyperparameters
block_size = 1024 
device = 'cuda:0' if torch.cuda.is_available() else 'cpu'
print(device)
n_embd = 384
n_head = 6
n_layer = 6
dropout = 0.2

filename = 'Inference'

torch.manual_seed(1337)

# Build vocabulary
print("Building vocabulary...")

vocab_tokens = []

# Edge types
mosfet_edges = [
    'M_B', 'M_D', 'M_G', 'M_S',  # Single pin
    'M_BD', 'M_BG', 'M_BS', 'M_DG', 'M_DS', 'M_GS',  # Two pins
    'M_BDG', 'M_BDS', 'M_BGS', 'M_DGS',  # Three pins
    'M_BDGS'  # Four pins
]
vocab_tokens.extend(mosfet_edges)

bjt_edges = [
    'B_B', 'B_C', 'B_E',
    'B_BC', 'B_BE', 'B_CE',
    'B_BCE'
]
vocab_tokens.extend(bjt_edges)

passive_edges = ['R_C', 'C_C', 'L_C']
vocab_tokens.extend(passive_edges)

diode_edges = ['D_P', 'D_N', 'D_NP', 'D_PN']
vocab_tokens.extend(diode_edges)

all_edge_types = set(mosfet_edges + bjt_edges + passive_edges + diode_edges)

# Power rails
vocab_tokens.extend(['VSS', 'VDD'])

# Circuit type tokens
circuit_type_tokens = [
    'CIRCUIT_Opamp', 'CIRCUIT_LDO', 'CIRCUIT_Bandgap_Ref',
    'CIRCUIT_Power_converter', 'CIRCUIT_Oscillator', 'CIRCUIT_General',
    'CIRCUIT_Mirror', 'CIRCUIT_Mixer', 'CIRCUIT_Power_Amp',
    'CIRCUIT_PLL', 'CIRCUIT_Filter', 'CIRCUIT_Comparator',
    'CIRCUIT_Voltage_Regulator', 'CIRCUIT_Switched_Cap', 'CIRCUIT_ADC_DAC'
]
vocab_tokens.extend(circuit_type_tokens)

# Device tokens
# MOSFETs: NM1-NM35, PM1-PM35
mosfet_tokens = []
for i in range(1, 36):
    mosfet_tokens.append(f'NM{i}')
for i in range(1, 36):
    mosfet_tokens.append(f'PM{i}')
vocab_tokens.extend(mosfet_tokens)

# BJTs: NPN1-NPN27, PNP1-PNP27
bjt_tokens = []
for i in range(1, 28):
    bjt_tokens.append(f'NPN{i}')
for i in range(1, 28):
    bjt_tokens.append(f'PNP{i}')
vocab_tokens.extend(bjt_tokens)

# Resistors: R1-R28
resistor_tokens = [f'R{i}' for i in range(1, 29)]
vocab_tokens.extend(resistor_tokens)

# Capacitors: C1-C16
capacitor_tokens = [f'C{i}' for i in range(1, 17)]
vocab_tokens.extend(capacitor_tokens)

# Inductors: L1-L24
inductor_tokens = [f'L{i}' for i in range(1, 25)]
vocab_tokens.extend(inductor_tokens)

# Diodes: DIO1-DIO8
diode_tokens = [f'DIO{i}' for i in range(1, 9)]
vocab_tokens.extend(diode_tokens)

# All device tokens combined
all_device_tokens = set(mosfet_tokens + bjt_tokens + resistor_tokens + 
                        capacitor_tokens + inductor_tokens + diode_tokens)

# Net nodes
net_tokens = [f'NET{i}' for i in range(1, 51)]
vocab_tokens.extend(net_tokens)

# Port nodes
port_tokens = []
# Voltage/Current I/O
for i in range(1, 21):
    port_tokens.append(f'VIN{i}')
port_tokens.append('VOUT')  # Single VOUT token
for i in range(1, 8):
    port_tokens.append(f'VOUT{i}')
for i in range(1, 4):
    port_tokens.append(f'IIN{i}')
for i in range(1, 6):
    port_tokens.append(f'IOUT{i}')
# Bias voltages/currents
for i in range(1, 12):
    port_tokens.append(f'VB{i}')
for i in range(1, 8):
    port_tokens.append(f'IB{i}')
# Control/reference signals
for i in range(1, 22):
    port_tokens.append(f'VCONT{i}')
for i in range(1, 4):
    port_tokens.extend([f'VCM{i}', f'VREF{i}', f'IREF{i}', f'VRF{i}', f'VIF{i}'])
# RF/mixer/PLL specific
for i in range(1, 6):
    port_tokens.extend([f'VLO{i}', f'VBB{i}'])
vocab_tokens.extend(port_tokens)

# All net/port tokens (nodes that connect)
all_net_port_tokens = set(net_tokens + port_tokens + ['VSS', 'VDD'])

# Special tokens
vocab_tokens.append('TRUNCATE')

# Build mappings
devices = vocab_tokens
stoi = {d: i for i, d in enumerate(devices)}
itos = {i: d for i, d in enumerate(devices)}
vocab_size = len(devices)

print(f"Vocabulary: {vocab_size} tokens")
print(f"  Edge types: {len(all_edge_types)}")
print(f"  Device types: {len(all_device_tokens)}")
print(f"  Net/Port types: {len(all_net_port_tokens)}")

encode = lambda s: [stoi[c] for c in s]
decode = lambda l: '->'.join([itos[i] for i in l]) + '->'

# =========================
# Precompute Index Sets
# =========================
print("Building index-based lookup tables...")

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

print(f"Index lookup tables built")


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
    Get allowed token indices based on last 2 tokens using state machine (Figure 4)
    
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


def generate_with_masking_batch(model, contexts, max_new_tokens=1024, max_length=1020, temperature=0.7, debug=False):
    """
    Batch autoregressive generation with token masking based on grammar rules
    
    Args:
        contexts: [B, initial_length] starting sequences
        max_new_tokens: maximum tokens to generate
        max_length: maximum total sequence length (discard if exceeded)
        temperature: sampling temperature
        debug: print debug info
    
    Returns:
        sequences: list of generated sequences (only valid ones)
        valid_mask: boolean mask indicating which sequences are valid
    """
    batch_size = contexts.size(0)
    idx = contexts
    finished = torch.zeros(batch_size, dtype=torch.bool, device=contexts.device)
    valid = torch.ones(batch_size, dtype=torch.bool, device=contexts.device)  # Track valid sequences
    
    # Initialize device_pins, net_connections, internal_nets_seen, and device_edge_nets for each sequence
    batch_device_pins = [track_device_pins_fast(contexts[b].tolist()) for b in range(batch_size)]
    
    # Track net connections and which internal nets have appeared
    batch_net_connections = []
    batch_internal_nets_seen = []
    for b in range(batch_size):
        net_conns, nets_seen = track_net_connections_fast(contexts[b].tolist())
        batch_net_connections.append(net_conns)
        batch_internal_nets_seen.append(nets_seen)
    
    # Track device-edge to net mappings
    batch_device_edge_nets = [track_device_edge_nets(contexts[b].tolist()) for b in range(batch_size)]
    
    # Track passive device net count
    batch_passive_net_count = [track_passive_net_count(contexts[b].tolist()) for b in range(batch_size)]
    
    # Track diode device net count
    batch_diode_net_count = [track_diode_net_count(contexts[b].tolist()) for b in range(batch_size)]
    
    # Track device pin to net mappings (for MOSFET/BJT)
    batch_device_pin_nets = [track_device_pin_nets(contexts[b].tolist()) for b in range(batch_size)]
    
    for step in range(max_new_tokens):
        # Check length constraint (per-sequence, not all at once!)
        current_lengths = idx.size(1)
        
        # Mark sequences that exceed length
        for b in range(batch_size):
            if not finished[b] and idx[b].size(0) >= max_length:
                valid[b] = False
                finished[b] = True
                if debug and step < 5:
                    print(f"Seq {b} exceeded max_length at step {step}, length={idx[b].size(0)}")
        
        # Get unfinished sequences
        if finished.all():
            break
        
        # Forward pass for all sequences
        idx_cond = idx[:, -model.block_size:]
        with torch.no_grad():
            logits, _ = model(idx_cond)
            logits = logits[:, -1, :]  # (B, vocab_size)
            logits = logits / temperature
        
        # Pre-allocate mask (reuse for efficiency)
        mask = torch.full((vocab_size,), float('-inf'), device=logits.device, dtype=logits.dtype)
        
        # Process each sequence in batch
        for b in range(batch_size):
            if finished[b]:
                continue
            
            # Get last 2 tokens (NO full sequence conversion!)
            seq_len = idx[b].size(0)
            prev1_idx = idx[b, -1].item() if seq_len >= 1 else None
            prev2_idx = idx[b, -2].item() if seq_len >= 2 else None
            
            # Use cached tracking structures (NO full rescan!)
            device_pins = batch_device_pins[b]
            net_connections = batch_net_connections[b]
            internal_nets_seen = batch_internal_nets_seen[b]
            device_edge_nets = batch_device_edge_nets[b]
            passive_net_count = batch_passive_net_count[b]
            diode_net_count = batch_diode_net_count[b]
            device_pin_nets = batch_device_pin_nets[b]
            
            # Get allowed token indices (index-based, only uses last 2 tokens)
            allowed_indices = get_allowed_tokens_fast(prev2_idx, prev1_idx, device_pins, net_connections, internal_nets_seen, device_edge_nets, passive_net_count, diode_net_count, device_pin_nets, seq_len)
            
            if len(allowed_indices) == 0:
                # No valid tokens - mark as invalid and finish
                if debug and step < 5:
                    print(f"Seq {b} has no allowed tokens at step {step}, len={seq_len}")
                    print(f"Last 2 tokens: {prev2_idx}, {prev1_idx}")
                valid[b] = False
                finished[b] = True
                continue
            
            # Reset mask and set allowed tokens
            mask.fill_(float('-inf'))
            mask[allowed_indices] = 0
            
            # Apply mask to this sequence's logits
            logits[b] = logits[b] + mask
        
        # Sample from masked distribution for unfinished sequences
        probs = F.softmax(logits, dim=-1)
        idx_next = torch.multinomial(probs, num_samples=1)  # (B, 1)
        
        # Update device_pins incrementally for each new token
        for b in range(batch_size):
            if not finished[b]:
                new_token_idx = idx_next[b, 0].item()
                
                # Get previous token (current last token before concatenation)
                seq_len = idx[b].size(0)
                prev_token = idx[b, -1].item() if seq_len >= 1 else None
                prev2_token = idx[b, -2].item() if seq_len >= 2 else None
                
                # Pattern 1: net/port - edge - DEVICE (new device appears)
                # Track this device and add edge pins
                if (prev2_token in net_port_indices and 
                    prev_token in edge_to_pins and 
                    new_token_idx in all_device_indices):
                    if new_token_idx not in batch_device_pins[b]:
                        batch_device_pins[b][new_token_idx] = set()
                    batch_device_pins[b][new_token_idx].update(edge_to_pins[prev_token])
                
                # Pattern 2: device - edge - (next will be net/port)
                # Add edge pins to existing device
                elif (prev2_token in all_device_indices and 
                      prev_token in edge_to_pins):
                    if prev2_token not in batch_device_pins[b]:
                        batch_device_pins[b][prev2_token] = set()
                    batch_device_pins[b][prev2_token].update(edge_to_pins[prev_token])
                
                # Update net_connections incrementally
                # Pattern 1: device - edge - NET (internal net)
                if (prev2_token in all_device_indices and 
                    prev_token in all_edge_indices and 
                    new_token_idx in internal_net_indices):
                    # Track that this internal net has appeared
                    batch_internal_nets_seen[b].add(new_token_idx)
                    # Add device to this net's connection set
                    if new_token_idx not in batch_net_connections[b]:
                        batch_net_connections[b][new_token_idx] = set()
                    batch_net_connections[b][new_token_idx].add(prev2_token)
                
                # Pattern 2: NET - edge - device (internal net)
                if (prev2_token in internal_net_indices and 
                    prev_token in all_edge_indices and 
                    new_token_idx in all_device_indices):
                    # Track that this internal net has appeared
                    batch_internal_nets_seen[b].add(prev2_token)
                    # Add device to this net's connection set
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
                    
                    # Update passive_net_count if passive device
                    if prev_token in passive_edge_indices:
                        if prev2_token not in batch_passive_net_count[b]:
                            batch_passive_net_count[b][prev2_token] = set()
                        batch_passive_net_count[b][prev2_token].add(new_token_idx)
                    
                    # Update diode_net_count if diode device
                    if prev_token in diode_edge_indices:
                        if prev2_token not in batch_diode_net_count[b]:
                            batch_diode_net_count[b][prev2_token] = set()
                        batch_diode_net_count[b][prev2_token].add(new_token_idx)
                    
                    # Update device_pin_nets for all devices
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
                    
                    # Update passive_net_count if passive device
                    if prev_token in passive_edge_indices:
                        if new_token_idx not in batch_passive_net_count[b]:
                            batch_passive_net_count[b][new_token_idx] = set()
                        batch_passive_net_count[b][new_token_idx].add(prev2_token)
                    
                    # Update diode_net_count if diode device
                    if prev_token in diode_edge_indices:
                        if new_token_idx not in batch_diode_net_count[b]:
                            batch_diode_net_count[b][new_token_idx] = set()
                        batch_diode_net_count[b][new_token_idx].add(prev2_token)
                    
                    # Update device_pin_nets for all devices
                    if prev_token in edge_to_pins:
                        pins = edge_to_pins[prev_token]
                        for pin in pins:
                            pin_key = (new_token_idx, pin)
                            if pin_key not in batch_device_pin_nets[b]:
                                batch_device_pin_nets[b][pin_key] = set()
                            batch_device_pin_nets[b][pin_key].add(prev2_token)
                
                # Check for TRUNCATE
                if new_token_idx == truncate_idx:
                    finished[b] = True
        
        # Concatenate new tokens
        idx = torch.cat((idx, idx_next), dim=1)
    
    # Filter out invalid sequences
    sequences = []
    for b in range(batch_size):
        if valid[b]:
            sequences.append(idx[b].tolist())
    
    return sequences, valid


# Load model
model = GPTLanguageModel(vocab_size, n_embd, block_size, n_head, n_layer, dropout)
m = model.to(device)
print(f"{sum(p.numel() for p in m.parameters())/1e6:.1f}M parameters")

savemodel_name = 'Pretrain.pth'
model.load_state_dict(torch.load(savemodel_name), strict=False)
model.eval()

run = 1000  # Circuits per circuit type
batch_size = 16  # Batch size for parallel generation
max_length = 1020  # Maximum sequence length

# Find all circuit type tokens
all_circuit_types = [token for token in vocab_tokens if token.startswith('CIRCUIT_')]

# Filter by command line argument if provided
if len(sys.argv) > 1:
    target = sys.argv[1]
    # Support both "CIRCUIT_Opamp" and "Opamp" formats
    if not target.startswith('CIRCUIT_'):
        target = f'CIRCUIT_{target}'
    if target not in all_circuit_types:
        print(f"Error: '{target}' is not a valid circuit type.")
        print(f"Available types: {[t.replace('CIRCUIT_', '') for t in all_circuit_types]}")
        sys.exit(1)
    all_circuit_types = [target]

print(f'\n{"="*70}')
print(f'Circuit types to generate: {[t.replace("CIRCUIT_", "") for t in all_circuit_types]}')
print(f'Will generate {run} circuits for each type')
print(f'Total circuits to generate: {run * len(all_circuit_types)}')
print(f'{"="*70}\n')

vss_idx = stoi.get('VSS')
if vss_idx is None:
    raise ValueError("VSS token not found in vocabulary")

# Loop through all circuit types
for circuit_idx, desired_circuit in enumerate(all_circuit_types, 1):
    print(f'\n{"="*70}')
    print(f'[{circuit_idx}/{len(all_circuit_types)}] Processing: {desired_circuit}')
    print(f'{"="*70}')
    
    if desired_circuit not in stoi:
        print(f"Warning: '{desired_circuit}' not in vocabulary, skipping...")
        continue

    # Create circuit type specific directory
    circuit_type_dir = f"Inference_{desired_circuit}_masked"
    os.makedirs(circuit_type_dir, exist_ok=True)
    print(f"Saving to: {circuit_type_dir}")
    print(f"Batch size: {batch_size}, Max length: {max_length}")

    print("\nStarting masked generation...")
    generated_count = 0
    discarded_count = 0
    batch_num = 0

    while generated_count < run:
        # Determine current batch size (handle last batch)
        current_batch_size = min(batch_size, run - generated_count + discarded_count)
        
        if batch_num % 10 == 0:
            print(f"  Batch {batch_num}: Generated {generated_count}/{run} circuits (discarded {discarded_count})...")
        
        # Create batch of initial contexts: [CIRCUIT_xxx, VSS]
        contexts = torch.tensor([[stoi[desired_circuit], vss_idx]] * current_batch_size, 
                               dtype=torch.long, device=device)
        
        # Generate batch
        sequences, valid_mask = generate_with_masking_batch(
            m, contexts, 
            max_new_tokens=1024, 
            max_length=max_length,
            temperature=0.7,
            debug=(batch_num == 0 and circuit_idx == 1)  # Debug first batch of first circuit type only
        )
        
        # Save valid sequences
        for seq in sequences:
            save_dir = circuit_type_dir + f'/run{generated_count}.txt'
            with open(save_dir, 'w') as f:
                f.write(decode(seq))
            generated_count += 1
            
            if generated_count >= run:
                break
        
        # Track discarded sequences
        num_discarded = current_batch_size - len(sequences)
        discarded_count += num_discarded
        
        batch_num += 1

    print(f"\nGenerated {generated_count} valid circuits in {circuit_type_dir}/")
    print(f"Discarded {discarded_count} sequences (exceeded max_length={max_length} or invalid)")

print(f"\n{'='*70}")
print(f"ALL COMPLETE!")
print(f"Generated {run} circuits × {len(all_circuit_types)} types = {run * len(all_circuit_types)} total circuits")
print(f"{'='*70}")
