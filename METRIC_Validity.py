#!/usr/bin/env python3
"""
Batch Electric Rule Check for All Inference Directories

This module performs rule-based validation across all Inference_CIRCUIT_* 
directories and reports clean sequence percentages for each circuit type.

The tool automatically discovers all circuit-type directories and validates 
each inference file using four levels of electrical rule checking. Results 
are aggregated and displayed as a summary table showing validation rates 
for each functional circuit category.

Supports:
    - .npy and .txt input formats
    - Automatic directory discovery (Inference_CIRCUIT_*)
    - Aggregate statistics per circuit type
    - Overall validation summary

Usage:
    python ERC_ALL.py
"""

import os
import numpy as np
from collections import defaultdict

# =========================
# Vocabulary Definition (matches GPT_Pretrain.py)
# =========================

# Edge types (connection types between nodes)
# MOSFET edges (M_ prefix)
MOSFET_EDGES = [
    'M_B', 'M_D', 'M_G', 'M_S',  # Single pin
    'M_BD', 'M_BG', 'M_BS', 'M_DG', 'M_DS', 'M_GS',  # Two pins
    'M_BDG', 'M_BDS', 'M_BGS', 'M_DGS',  # Three pins
    'M_BDGS'  # Four pins
]

# BJT edges (B_ prefix)
BJT_EDGES = [
    'B_B', 'B_C', 'B_E',  # Single pin
    'B_BC', 'B_BE', 'B_CE',  # Two pins
    'B_BCE'  # Three pins
]

# Passive device edges
PASSIVE_EDGES = ['R_C', 'C_C', 'L_C']

# Diode edges (D_ prefix)
DIODE_EDGES = ['D_P', 'D_N', 'D_NP', 'D_PN']

# All edge types
ALL_EDGES = MOSFET_EDGES + BJT_EDGES + PASSIVE_EDGES + DIODE_EDGES

# Power rails (net nodes)
POWER_RAILS = ['VSS', 'VDD']

# Circuit type tokens
CIRCUIT_TYPE_TOKENS = [
    'CIRCUIT_Opamp', 'CIRCUIT_LDO', 'CIRCUIT_Bandgap_Ref',
    'CIRCUIT_Power_converter', 'CIRCUIT_Oscillator', 'CIRCUIT_General',
    'CIRCUIT_Mirror', 'CIRCUIT_Mixer', 'CIRCUIT_Power_Amp',
    'CIRCUIT_PLL', 'CIRCUIT_Filter', 'CIRCUIT_Comparator',
    'CIRCUIT_Voltage_Regulator', 'CIRCUIT_Switched_Cap', 'CIRCUIT_ADC_DAC'
]

# Device node prefixes
MOSFET_PREFIXES = ['NM', 'PM']
BJT_PREFIXES = ['NPN', 'PNP']
PASSIVE_PREFIXES = ['R', 'C', 'L']
DIODE_PREFIXES = ['DIO']

# Port nodes
PORT_PREFIXES = ['VIN', 'VOUT', 'IIN', 'IOUT', 'VB', 'IB', 'VCONT', 
                 'VCM', 'IREF', 'VLO', 'VBB', 'VRF', 'VIF', 'VREF']

# Net nodes
NET_PREFIX = 'NET'


def is_device_node(token):
    """Check if token is a device node"""
    for prefix in MOSFET_PREFIXES + BJT_PREFIXES + PASSIVE_PREFIXES + DIODE_PREFIXES:
        if token.startswith(prefix):
            if token[len(prefix):].isdigit():
                return True
    return False


def is_net_node(token):
    """Check if token is a net node (NET, port, or power rail)"""
    if token in POWER_RAILS:
        return True
    if token.startswith(NET_PREFIX) and token[len(NET_PREFIX):].isdigit():
        return True
    for prefix in PORT_PREFIXES:
        if token.startswith(prefix):
            return True
    if token == 'VOUT':  # Special case
        return True
    return False


def is_internal_net(token):
    """Check if token is an internal net (NET1-50), excluding external ports and power rails"""
    if token.startswith(NET_PREFIX) and token[len(NET_PREFIX):].isdigit():
        return True
    return False


def is_edge(token, prev_token=None, next_token=None):
    """Check if token is an edge type (with prefixes)"""
    return token in ALL_EDGES


def get_device_prefix(device_token):
    """Get device prefix (NM, PM, R, C, etc.)"""
    for prefix in MOSFET_PREFIXES + BJT_PREFIXES + PASSIVE_PREFIXES + DIODE_PREFIXES:
        if device_token.startswith(prefix):
            if device_token[len(prefix):].isdigit():
                return prefix
    return None


def get_pins_from_edge(edge):
    """Extract pins from edge type (e.g., M_GD -> {'G', 'D'}, R_C -> {'C'})"""
    if edge.startswith('M_'):
        return set(edge[2:])  # M_GD -> {'G', 'D'}
    elif edge.startswith('B_'):
        return set(edge[2:])  # B_BC -> {'B', 'C'}
    elif edge.startswith('D_'):
        return set(edge[2:])  # D_NP -> {'N', 'P'}
    elif edge in PASSIVE_EDGES:
        return {'C'}  # All passives use 'C' for connection
    return set()


def check_sequence_first_test(tokens):
    """Test 1: Device-Edge-Net-Edge-Device Pattern Validation.
    
    Args:
        tokens: List of circuit tokens
        
    Returns:
        List of violation messages
    """
    violations = []
    
    for i in range(len(tokens)):
        token = tokens[i]
        
        # Skip circuit type token
        if token in CIRCUIT_TYPE_TOKENS:
            continue
        
        # Get context tokens for 'C' ambiguity
        prev_token = tokens[i-1] if i > 0 else None
        next_token = tokens[i+1] if i < len(tokens)-1 else None
        
        if i == 0 or (i > 0 and tokens[i-1] in CIRCUIT_TYPE_TOKENS):
            # First token (after circuit type) should be a node
            if not (is_device_node(token) or is_net_node(token)):
                if not is_edge(token, prev_token, next_token):
                    violations.append(f"Position {i}: Expected node, got '{token}'")
        else:
            prev_ctx = tokens[i-1]
            
            # After a node, expect an edge
            if is_device_node(prev_ctx) or is_net_node(prev_ctx):
                if not is_edge(token, prev_token, next_token):
                    violations.append(f"Position {i}: After node '{prev_ctx}', expected edge, got '{token}'")
            # After an edge, expect a node
            elif is_edge(prev_ctx, tokens[i-2] if i >= 2 else None, token):
                if not (is_device_node(token) or is_net_node(token)):
                    violations.append(f"Position {i}: After edge '{prev_ctx}', expected node, got '{token}'")
    
    return violations


def check_sequence_second_test(tokens):
    """Test 2: Required Pin Validation.
    
    Args:
        tokens: List of circuit tokens
        
    Returns:
        List of violation messages
    """
    violations = []
    device_edges = defaultdict(set)
    
    for i in range(len(tokens)):
        token = tokens[i]
        
        if is_device_node(token):
            # Check edge BEFORE device (edge -> device pattern)
            if i > 0:
                prev_token = tokens[i - 1]
                prev_prev = tokens[i - 2] if i >= 2 else None
                if is_edge(prev_token, prev_prev, token):
                    device_edges[token].add(prev_token)
            
            # Check edge AFTER device (device -> edge pattern)
            if i + 1 < len(tokens):
                next_token = tokens[i + 1]
                next_next = tokens[i + 2] if i + 2 < len(tokens) else None
                if is_edge(next_token, token, next_next):
                    device_edges[token].add(next_token)
    
    for device, edges in device_edges.items():
        prefix = get_device_prefix(device)
        
        if prefix in MOSFET_PREFIXES:
            # MOSFET: need S, G, D, and B
            # Check if pins are covered by edges (M_S, M_D, M_G, M_B or compound edges)
            pins_used = set()
            for edge in edges:
                if edge.startswith('M_'):
                    # Extract pins from edge: M_DGS -> D, G, S
                    pins = edge[2:]  # Remove 'M_' prefix
                    pins_used.update(list(pins))
            
            missing = []
            if 'S' not in pins_used:
                missing.append('S')
            if 'G' not in pins_used:
                missing.append('G')
            if 'D' not in pins_used:
                missing.append('D')
            if 'B' not in pins_used:
                missing.append('B')
            
            if missing:
                violations.append(f"Device {device} (MOSFET) missing: {', '.join(missing)}")
        
        elif prefix in BJT_PREFIXES:
            # BJT: need B, C, E
            pins_used = set()
            for edge in edges:
                if edge.startswith('B_'):
                    # Extract pins from edge: B_BC -> B, C
                    pins = edge[2:]  # Remove 'B_' prefix
                    pins_used.update(list(pins))
            
            missing = []
            if 'B' not in pins_used:
                missing.append('B')
            if 'C' not in pins_used:
                missing.append('C')
            if 'E' not in pins_used:
                missing.append('E')
            
            if missing:
                violations.append(f"Device {device} (BJT) missing: {', '.join(missing)}")
        
        elif prefix in PASSIVE_PREFIXES:
            # Passives (R, C, L): must have appropriate connection edges
            expected_edge = f'{prefix}_C'
            if expected_edge not in edges:
                violations.append(f"Device {device} (passive) missing edge {expected_edge}")
        
        elif prefix in DIODE_PREFIXES:
            # Diodes: must have P and N connections
            pins_used = set()
            for edge in edges:
                if edge.startswith('D_'):
                    # Extract pins from edge: D_NP -> N, P
                    pins = edge[2:]  # Remove 'D_' prefix
                    pins_used.update(list(pins))
            
            if 'P' not in pins_used or 'N' not in pins_used:
                missing = []
                if 'P' not in pins_used:
                    missing.append('P')
                if 'N' not in pins_used:
                    missing.append('N')
                violations.append(f"Device {device} (diode) missing: {', '.join(missing)}")
    
    return violations


def check_sequence_third_test(tokens):
    """Test 3: Pin-Level Net Connection Validation.
    
    Args:
        tokens: List of circuit tokens
        
    Returns:
        List of violation messages
    """
    violations = []
    
    # Track: (device, pin) -> set of nets (for MOSFET/BJT/Diode)
    device_pin_nets = defaultdict(set)
    
    # Track: device -> set of nets (for passives only)
    device_nets = defaultdict(set)
    
    for i in range(len(tokens) - 2):
        token1 = tokens[i]
        token2 = tokens[i + 1]
        token3 = tokens[i + 2]
        
        # Pattern 1: device -> edge -> net
        if is_device_node(token1) and is_edge(token2) and is_net_node(token3):
            pins = get_pins_from_edge(token2)
            prefix = get_device_prefix(token1)
            
            # Track pin-level for MOSFET/BJT/Diode
            if prefix in MOSFET_PREFIXES or prefix in BJT_PREFIXES or prefix in DIODE_PREFIXES:
                for pin in pins:
                    device_pin_nets[(token1, pin)].add(token3)
            # Track device-level for passives only
            elif prefix in PASSIVE_PREFIXES:
                device_nets[token1].add(token3)
        
        # Pattern 2: net -> edge -> device (reverse direction)
        elif is_net_node(token1) and is_edge(token2) and is_device_node(token3):
            pins = get_pins_from_edge(token2)
            prefix = get_device_prefix(token3)
            
            # Track pin-level for MOSFET/BJT/Diode
            if prefix in MOSFET_PREFIXES or prefix in BJT_PREFIXES or prefix in DIODE_PREFIXES:
                for pin in pins:
                    device_pin_nets[(token3, pin)].add(token1)
            # Track device-level for passives only
            elif prefix in PASSIVE_PREFIXES:
                device_nets[token3].add(token1)
    
    # Check MOSFET/BJT/Diode violations: each pin should connect to only ONE net
    for (device, pin), nets in device_pin_nets.items():
        if len(nets) > 1:
            violations.append(f"Device {device} pin {pin} connects to multiple nets: {', '.join(sorted(nets))}")
    
    # Check Passive violations: 2-terminal devices should connect to max 2 nets
    for device, nets in device_nets.items():
        if len(nets) > 2:
            violations.append(f"2-terminal device {device} connects to more than 2 nets: {', '.join(sorted(nets))}")
    
    return violations


def check_internal_net_connections(tokens):
    """Test 4: Internal Net Connection Validation.
    
    Ensures internal nets (NET1-50) have at least 2 device connections.
    
    Args:
        tokens: List of circuit tokens
        
    Returns:
        List of violation messages
    """
    violations = []
    net_connections = defaultdict(set)
    
    for i in range(len(tokens) - 2):
        token1 = tokens[i]
        token2 = tokens[i + 1]
        token3 = tokens[i + 2]
        
        # Pattern 1: device - edge - internal_net
        if is_device_node(token1) and is_edge(token2) and is_internal_net(token3):
            net_connections[token3].add(token1)
        
        # Pattern 2: internal_net - edge - device
        elif is_internal_net(token1) and is_edge(token2) and is_device_node(token3):
            net_connections[token1].add(token3)
    
    # Check each internal net has >= 2 device connections
    for net, devices in net_connections.items():
        if len(devices) < 2:
            violations.append(f"Internal net {net} has only {len(devices)} device connection(s): {', '.join(sorted(devices))} (minimum 2 required)")
    
    return violations


def parse_inference_file(file_path):
    """Parse inference file.
    
    Supports .npy and .txt formats. Extracts tokens and circuit type.
    
    Args:
        file_path: Path to inference file
        
    Returns:
        Tuple of (tokens, circuit_type)
    """
    if file_path.endswith('.npy'):
        data = np.load(file_path, allow_pickle=True)
        if data.ndim == 0:
            all_tokens = [str(token) for token in data.item() if str(token) != 'TRUNCATE']
        elif data.ndim == 1:
            all_tokens = [str(token) for token in data if str(token) != 'TRUNCATE']
        else:
            all_tokens = [str(token) for token in data[0] if str(token) != 'TRUNCATE']
    else:
        with open(file_path, 'r') as f:
            content = f.read().strip()
        all_tokens = [token.strip() for token in content.split('->') if token.strip() and token.strip() != 'TRUNCATE']
    
    circuit_type = None
    tokens = all_tokens
    
    if all_tokens and all_tokens[0] in CIRCUIT_TYPE_TOKENS:
        circuit_type = all_tokens[0]
    
    return tokens, circuit_type


def run_rule_validation(tokens):
    """Run all four rule-based electrical checks.
    
    Args:
        tokens: List of circuit tokens
        
    Returns:
        Dictionary with test results and total violation count
    """
    violations_1 = check_sequence_first_test(tokens)
    violations_2 = check_sequence_second_test(tokens)
    violations_3 = check_sequence_third_test(tokens)
    violations_4 = check_internal_net_connections(tokens)
    
    total = len(violations_1) + len(violations_2) + len(violations_3) + len(violations_4)
    
    return {
        'test1': violations_1,
        'test2': violations_2,
        'test3': violations_3,
        'test4': violations_4,
        'total': total
    }


def check_all_inference_folders():
    """Check all Inference_CIRCUIT_* folders and report clean percentages.
    
    Automatically discovers all circuit-type inference directories, validates
    each file using four-level ERC, and reports aggregate statistics.
    """
    print("=" * 70)
    print("Electric Rule Check - All Inference Folders")
    print("=" * 70)
    
    # Find all Inference_CIRCUIT_* folders
    inference_folders = [f for f in os.listdir('.') if f.startswith('Inference_CIRCUIT_')]
    
    if not inference_folders:
        print("No Inference_CIRCUIT_* folders found")
        return
    
    print(f"Found {len(inference_folders)} inference folders\n")
    
    results = []
    
    for folder in sorted(inference_folders):
        circuit_type = folder.replace('Inference_', '')
        
        # Get all inference files
        files = [f for f in os.listdir(folder) if f.startswith('run') and (f.endswith('.txt') or f.endswith('.npy'))]
        
        if not files:
            continue
        
        clean_count = 0
        total_count = len(files)
        
        for filename in files:
            file_path = os.path.join(folder, filename)
            
            try:
                tokens, _ = parse_inference_file(file_path)
                
                if len(tokens) > 0:
                    result = run_rule_validation(tokens)
                    
                    if result['total'] == 0:
                        clean_count += 1
            except Exception:
                continue
        
        clean_percentage = (clean_count / total_count * 100) if total_count > 0 else 0
        
        results.append({
            'circuit_type': circuit_type,
            'total': total_count,
            'clean': clean_count,
            'percentage': clean_percentage
        })
        
        print(f"{circuit_type:30s}: {clean_count:4d}/{total_count:4d} clean ({clean_percentage:5.1f}%)")
    
    # Summary
    total_files = sum(r['total'] for r in results)
    total_clean = sum(r['clean'] for r in results)
    overall_percentage = (total_clean / total_files * 100) if total_files > 0 else 0
    
    print("\n" + "=" * 70)
    print(f"{'OVERALL':30s}: {total_clean:4d}/{total_files:4d} clean ({overall_percentage:5.1f}%)")
    print("=" * 70)


if __name__ == "__main__":
    check_all_inference_folders()
