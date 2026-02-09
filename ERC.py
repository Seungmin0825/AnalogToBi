#!/usr/bin/env python3
"""
Electric Rule Check (ERC) for Bipartite Graph Representation

This module performs comprehensive rule-based validation on analog circuit 
topologies represented as bipartite graphs. It validates circuit correctness 
through four levels of electrical rule checking:

1. Node-Edge Pattern Validation: Ensures proper device-edge-net alternation
2. Required Pin Validation: Verifies all required device pins are connected
3. Pin-Level Net Validation: Checks each pin connects to only one net
4. Internal Net Validation: Ensures internal nets connect to at least 2 devices

Supports:
    - .npy and .txt input formats
    - CIRCUIT_TYPE tokens (15 functional categories)
    - Comprehensive statistics and JSON output
    - Batch analysis of inference directories

Usage:
    python ERC.py Training.npy
    python ERC.py Inference_CIRCUIT_Opamp
    python ERC.py Inference
"""

import os
import time
import json
import numpy as np
from collections import defaultdict, Counter


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
    'M_B', 'B_C', 'B_E',  # Single pin
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

# Circuit type tokens (to be skipped during validation)
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

# MOSFET edges (S, G, D, B or BS)
MOSFET_REQUIRED_EDGES = ['S', 'G', 'D']  # B or BS
# BJT edges
BJT_REQUIRED_EDGES = ['B', 'C', 'E']

# Port nodes
PORT_PREFIXES = ['VIN', 'VOUT', 'IIN', 'IOUT', 'VB', 'IB', 'VCONT', 
                 'VCM', 'IREF', 'VLO', 'VBB', 'VRF', 'VIF', 'VREF']

# Net nodes
NET_PREFIX = 'NET'

# Build complete vocabulary (matches GPT_Pretrain.py exactly)
def build_vocabulary():
    vocab = []
    # 1. Edge types
    vocab.extend(MOSFET_EDGES)
    vocab.extend(BJT_EDGES)
    vocab.extend(PASSIVE_EDGES)
    vocab.extend(DIODE_EDGES)
    # 2. Power rails
    vocab.extend(POWER_RAILS)
    # 3. Circuit types
    vocab.extend(CIRCUIT_TYPE_TOKENS)
    # 4. Devices
    for i in range(1, 36): vocab.append(f'NM{i}')
    for i in range(1, 36): vocab.append(f'PM{i}')
    for i in range(1, 28): vocab.append(f'NPN{i}')
    for i in range(1, 28): vocab.append(f'PNP{i}')
    for i in range(1, 29): vocab.append(f'R{i}')
    for i in range(1, 17): vocab.append(f'C{i}')
    for i in range(1, 25): vocab.append(f'L{i}')
    for i in range(1, 9): vocab.append(f'DIO{i}')
    # 5. Nets
    for i in range(1, 51): vocab.append(f'NET{i}')
    # 6. Ports
    for i in range(1, 21): vocab.append(f'VIN{i}')
    vocab.append('VOUT')
    for i in range(1, 8): vocab.append(f'VOUT{i}')
    for i in range(1, 4): vocab.append(f'IIN{i}')
    for i in range(1, 6): vocab.append(f'IOUT{i}')
    for i in range(1, 12): vocab.append(f'VB{i}')
    for i in range(1, 8): vocab.append(f'IB{i}')
    for i in range(1, 22): vocab.append(f'VCONT{i}')
    for i in range(1, 4):
        vocab.append(f'VCM{i}')
        vocab.append(f'VREF{i}')
        vocab.append(f'IREF{i}')
        vocab.append(f'VRF{i}')
        vocab.append(f'VIF{i}')
    for i in range(1, 6):
        vocab.append(f'VLO{i}')
        vocab.append(f'VBB{i}')
    # 7. Special
    vocab.append('TRUNCATE')
    return vocab

# Build vocabulary once at module level
VOCAB = build_vocabulary()
STOI = {s: i for i, s in enumerate(VOCAB)}
ITOS = {i: s for i, s in enumerate(VOCAB)}


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
    """Check if token is an edge type"""
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


def check_sequence_first_test(tokens, debug=False):
    """Test 1: Device-Edge-Net-Edge-Device Pattern Validation.
    
    Validates that sequence follows node-edge-node-edge pattern
    (excluding circuit type token).
    
    Args:
        tokens: List of circuit tokens
        debug: If True, print violation details
        
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
        
        # Determine expected type based on position
        # After skipping circuit type, pattern should be: device/net -> edge -> device/net -> edge ...
        if i == 0 or (i > 0 and tokens[i-1] in CIRCUIT_TYPE_TOKENS):
            # First token (after circuit type) should be a node (device or net)
            if not (is_device_node(token) or is_net_node(token)):
                if not is_edge(token, prev_token, next_token):
                    violation_msg = f"Position {i}: Expected device or net node, got '{token}'"
                    violations.append(violation_msg)
                    if debug:
                        print(f"TEST 1 VIOLATION: {violation_msg}")
        else:
            # Get previous token context
            prev_ctx = tokens[i-1]
            
            # After a node, expect an edge
            if is_device_node(prev_ctx) or is_net_node(prev_ctx):
                if not is_edge(token, prev_token, next_token):
                    violation_msg = f"Position {i}: After node '{prev_ctx}', expected edge, got '{token}'"
                    violations.append(violation_msg)
                    if debug:
                        print(f"TEST 1 VIOLATION: {violation_msg}")
            
            # After an edge, expect a node
            elif is_edge(prev_ctx, tokens[i-2] if i >= 2 else None, token):
                if not (is_device_node(token) or is_net_node(token)):
                    violation_msg = f"Position {i}: After edge '{prev_ctx}', expected node, got '{token}'"
                    violations.append(violation_msg)
                    if debug:
                        print(f"TEST 1 VIOLATION: {violation_msg}")
    
    return violations


def check_sequence_second_test(tokens, debug=False):
    """Test 2: Required Pin Validation.
    
    Validates that all required device pins are connected:
    - MOSFETs: Must have S, G, D, and B connections
    - BJTs: Must have B, C, E connections  
    - Diodes: Must have P and N connections
    - Passives: Must have connections via R_C, C_C, or L_C
    
    Args:
        tokens: List of circuit tokens
        debug: If True, print violation details
        
    Returns:
        List of violation messages
    """
    violations = []
    
    # Track device connections: device -> set of edges
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
    
    # Check each device
    for device, edges in device_edges.items():
        prefix = get_device_prefix(device)
        
        if prefix in MOSFET_PREFIXES:
            # MOSFET: need M_S, M_G, M_D, and M_B
            # Check if edges contain these pins (can be combined like M_SB, M_DG, etc.)
            all_pins = set()
            for edge in edges:
                if edge.startswith('M_'):
                    # Extract pins after M_ prefix (e.g., M_DG -> D, G)
                    pins = edge[2:]  # Remove 'M_'
                    all_pins.update(list(pins))
            
            has_s = 'S' in all_pins
            has_g = 'G' in all_pins
            has_d = 'D' in all_pins
            has_b = 'B' in all_pins
            
            missing = []
            if not has_s:
                missing.append('S')
            if not has_g:
                missing.append('G')
            if not has_d:
                missing.append('D')
            if not has_b:
                missing.append('B')
            
            if missing:
                violation_msg = f"Device {device} (MOSFET) missing required pins: {', '.join(missing)} (has edges: {', '.join(sorted(edges))}, pins: {sorted(all_pins)})"
                violations.append(violation_msg)
                if debug:
                    print(f"TEST 2 VIOLATION: {violation_msg}")
        
        elif prefix in BJT_PREFIXES:
            # BJT: need B_B, B_C, B_E
            # Check if edges contain these pins (can be combined like B_BC, B_BE, etc.)
            all_pins = set()
            for edge in edges:
                if edge.startswith('B_'):
                    # Extract pins after B_ prefix (e.g., B_BC -> B, C)
                    pins = edge[2:]  # Remove 'B_'
                    all_pins.update(list(pins))
            
            has_b = 'B' in all_pins
            has_c = 'C' in all_pins
            has_e = 'E' in all_pins
            
            missing = []
            if not has_b:
                missing.append('B')
            if not has_c:
                missing.append('C')
            if not has_e:
                missing.append('E')
            
            if missing:
                violation_msg = f"Device {device} (BJT) missing required pins: {', '.join(missing)} (has edges: {', '.join(sorted(edges))}, pins: {sorted(all_pins)})"
                violations.append(violation_msg)
                if debug:
                    print(f"TEST 2 VIOLATION: {violation_msg}")
        
        elif prefix in PASSIVE_PREFIXES:
            # Passives (R, C, L): must have appropriate connection edges
            expected_edge = f'{prefix}_C' if prefix != 'C' else 'C_C'
            
            # Check if connected via proper passive edge
            passive_connections = [e for e in edges if e in PASSIVE_EDGES]
            if not passive_connections:
                violation_msg = f"Device {device} (passive) has no passive connection edges (expected {expected_edge})"
                violations.append(violation_msg)
                if debug:
                    print(f"TEST 2 VIOLATION: {violation_msg}")
        
        elif prefix in DIODE_PREFIXES:
            # Diodes: must have D_P and D_N connections
            has_p = any(e in edges for e in ['D_P', 'D_NP', 'D_PN'])
            has_n = any(e in edges for e in ['D_N', 'D_NP', 'D_PN'])
            
            if not (has_p and has_n):
                missing = []
                if not has_p:
                    missing.append('P')
                if not has_n:
                    missing.append('N')
                violation_msg = f"Device {device} (diode) missing required pins: {', '.join(missing)} (has: {', '.join(sorted(edges))})"
                violations.append(violation_msg)
                if debug:
                    print(f"TEST 2 VIOLATION: {violation_msg}")
    
    return violations


def check_sequence_third_test(tokens, debug=False):
    """Test 3: Pin-Level Net Connection Validation.
    
    Validates that each device pin connects to only one net:
    - MOSFET/BJT/Diode: Each pin can connect to only ONE net
    - Passives: 2-terminal devices can connect to exactly 2 different nets
    
    Checks both patterns: device->edge->net AND net->edge->device
    
    Args:
        tokens: List of circuit tokens
        debug: If True, print violation details
        
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
            violation_msg = f"Device {device} pin {pin} connects to multiple nets: {', '.join(sorted(nets))}"
            violations.append(violation_msg)
            if debug:
                print(f"TEST 3 VIOLATION: {violation_msg}")
    
    # Check Passive violations: 2-terminal devices should connect to exactly 2 nets
    for device, nets in device_nets.items():
        if len(nets) > 2:
            violation_msg = f"2-terminal device {device} connects to more than 2 nets: {', '.join(sorted(nets))}"
            violations.append(violation_msg)
            if debug:
                print(f"TEST 3 VIOLATION: {violation_msg}")
    
    return violations
    
    return violations


def check_internal_net_connections(tokens, debug=False):
    """Test 4: Internal Net Connection Validation.
    
    Validates that internal nets (NET1-50) are connected to at least 2 devices.
    External ports (VIN, IB, etc.) and power rails (VDD, VSS) are excluded.
    
    Args:
        tokens: List of circuit tokens
        debug: If True, print violation details
        
    Returns:
        List of violation messages
    """
    violations = []
    
    # Track: internal_net -> set of connected devices
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
            violation_msg = f"Internal net {net} has only {len(devices)} device connection(s): {', '.join(sorted(devices))} (minimum 2 required)"
            violations.append(violation_msg)
            if debug:
                print(f"TEST 4 VIOLATION: {violation_msg}")
    
    return violations


def parse_inference_file(file_path):
    """Parse inference file and extract tokens.
    
    Supports .npy and .txt formats. Handles CIRCUIT_TYPE tokens and 
    removes TRUNCATE tokens.
    
    Args:
        file_path: Path to inference file
        
    Returns:
        Tuple of (tokens, circuit_type)
    """
    if file_path.endswith('.npy'):
        # Load .npy file
        data = np.load(file_path, allow_pickle=True)
        if data.ndim == 0:
            # Single sequence
            all_tokens = [str(token) for token in data.item() if str(token) != 'TRUNCATE']
        elif data.ndim == 1:
            # 1D array of tokens
            all_tokens = [str(token) for token in data if str(token) != 'TRUNCATE']
        else:
            # 2D array, take first sequence
            all_tokens = [str(token) for token in data[0] if str(token) != 'TRUNCATE']
    else:
        # Assume .txt format
        with open(file_path, 'r') as f:
            content = f.read().strip()
        # Split by -> and remove empty tokens and TRUNCATE tokens
        all_tokens = [token.strip() for token in content.split('->') if token.strip() and token.strip() != 'TRUNCATE']
    
    # Check if first token is a CIRCUIT_TYPE and keep it for info but process separately
    circuit_type = None
    tokens = all_tokens
    
    if all_tokens and all_tokens[0] in CIRCUIT_TYPE_TOKENS:
        circuit_type = all_tokens[0]
        # Keep circuit type in tokens for pattern validation (will be skipped in tests)
    
    return tokens, circuit_type


def run_rule_validation(tokens, verbose=False, debug=False):
    """Run all four rule-based electrical checks.
    
    Args:
        tokens: List of circuit tokens
        verbose: If True, print test results
        debug: If True, print detailed violation info
        
    Returns:
        Tuple of (is_clean, violations_1, violations_2, violations_3, violations_4)
    """
    if verbose:
        print("Running rule-based circuit validation...")
    
    # Test 1: Device-Pin Connection Rules
    violations_1 = check_sequence_first_test(tokens, debug=debug)
    if verbose and violations_1:
        print(f"Test 1: {len(violations_1)} violations")
    elif verbose:
        print("Test 1: No violations")
    
    # Test 2: Missing Pin Detection
    violations_2 = check_sequence_second_test(tokens, debug=debug)
    if verbose and violations_2:
        print(f"Test 2: {len(violations_2)} violations")
    elif verbose:
        print("Test 2: No violations")
    
    # Test 3: Port Connection Validation
    violations_3 = check_sequence_third_test(tokens, debug=debug)
    if verbose and violations_3:
        print(f"Test 3: {len(violations_3)} violations")
    elif verbose:
        print("Test 3: No violations")
    
    # Test 4: Internal Net Connection Validation
    violations_4 = check_internal_net_connections(tokens, debug=debug)
    if verbose and violations_4:
        print(f"Test 4: {len(violations_4)} violations")
    elif verbose:
        print("Test 4: No violations")
    
    total = len(violations_1) + len(violations_2) + len(violations_3) + len(violations_4)
    if verbose:
        print(f"Total: {total} violations")
    
    is_clean = (total == 0)
    
    return is_clean, violations_1, violations_2, violations_3, violations_4


def analyze_inference_directory(inference_dir="Inference", output_file="inference_analysis_results.json", sample_size=None):
    """Analyze all inference files in a directory.
    
    Args:
        inference_dir: Directory containing inference files
        output_file: JSON file to save results
        sample_size: Number of files to sample (None for all files)
        
    Returns:
        List of analysis results for all files
    """
    print("Electric Rule Check - Inference Validation")
    print("=" * 70)
    
    # Get all run*.txt files
    all_files = [f for f in os.listdir(inference_dir) if f.startswith('run') and f.endswith('.txt')]
    all_files.sort(key=lambda x: int(x.replace('run', '').replace('.txt', '')))
    
    if sample_size and sample_size < len(all_files):
        import random
        files = random.sample(all_files, sample_size)
        print(f"Found {len(all_files)} files, analyzing {len(files)} samples")
    else:
        files = all_files
        print(f"Analyzing all {len(files)} files")
    
    print("Starting analysis...")
    
    start_time = time.time()
    
    # Statistics collectors
    all_results = []
    violation_stats = defaultdict(int)
    test_stats = {'test1': 0, 'test2': 0, 'test3': 0, 'test4': 0}
    sequence_lengths = []
    clean_files = []
    problematic_files = []
    circuit_type_stats = defaultdict(int)
    
    # Device and violation tracking
    device_violations = defaultdict(int)
    port_violations = defaultdict(int)
    
    # Progress tracking
    processed = 0
    print_interval = max(1, len(files) // 20)  # Print 20 updates
    
    for i, filename in enumerate(files):
        file_path = os.path.join(inference_dir, filename)
        
        # Progress update
        if (i + 1) % print_interval == 0 or i == 0:
            elapsed = time.time() - start_time
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            eta = (len(files) - (i + 1)) / rate if rate > 0 else 0
            print(f"Progress: {i+1}/{len(files)} ({(i+1)/len(files)*100:.1f}%) - "
                  f"Rate: {rate:.1f} files/sec - ETA: {eta:.1f}s")
        
        # Parse file
        try:
            tokens, circuit_type = parse_inference_file(file_path)
            sequence_lengths.append(len(tokens))
            
            # Track circuit types
            if circuit_type:
                circuit_type_stats[circuit_type] += 1
            else:
                circuit_type_stats['NO_TYPE'] += 1
            
            # Run rule validation
            if len(tokens) > 0:
                is_clean, violations_1, violations_2, violations_3, violations_4 = run_rule_validation(tokens, verbose=False)
                
                # Collect statistics
                total_violations = len(violations_1) + len(violations_2) + len(violations_3) + len(violations_4)
                violation_stats[total_violations] += 1
                
                test_stats['test1'] += len(violations_1)
                test_stats['test2'] += len(violations_2)
                test_stats['test3'] += len(violations_3)
                test_stats['test4'] += len(violations_4)
                
                # Track specific violations
                for violation in violations_1 + violations_2 + violations_3 + violations_4:
                    if 'Device' in violation:
                        device_name = violation.split('Device ')[1].split(' ')[0]
                        device_violations[device_name] += 1
                    if 'Pin' in violation and 'port' in violation:
                        if ':' in violation:
                            ports_part = violation.split(':')[1].strip()
                            for port in ports_part.replace(' and ', ',').split(','):
                                port = port.strip()
                                if port and not port.startswith('Pin'):
                                    port_violations[port] += 1
                
                result_entry = {
                    'filename': filename,
                    'run_id': int(filename.replace('run', '').replace('.txt', '')),
                    'circuit_type': circuit_type,
                    'sequence_length': len(tokens),
                    'total_violations': total_violations,
                    'test1_violations': len(violations_1),
                    'test2_violations': len(violations_2),
                    'test3_violations': len(violations_3),
                    'test4_violations': len(violations_4),
                    'violations_detail': {
                        'test1': violations_1,
                        'test2': violations_2,
                        'test3': violations_3,
                        'test4': violations_4
                    }
                }
                
                all_results.append(result_entry)
                
                if total_violations == 0:
                    clean_files.append(result_entry)
                else:
                    problematic_files.append(result_entry)
            else:
                print(f"Warning: Empty sequence: {filename}")
                
        except Exception as e:
            print(f"Error processing {filename}: {e}")
            continue
        
        processed += 1
    
    end_time = time.time()
    total_time = end_time - start_time
    
    # Generate comprehensive report
    print("\n" + "="*70)
    print("COMPREHENSIVE ANALYSIS RESULTS")
    print("="*70)
    
    print(f"Analysis completed in {total_time:.2f} seconds")
    print(f"Files processed: {processed}/{len(files)}")
    print(f"Processing rate: {processed/total_time:.2f} files/second")
    
    # Basic statistics
    total_violations_all = sum(r['total_violations'] for r in all_results)
    avg_violations = total_violations_all / len(all_results) if all_results else 0
    avg_sequence_length = sum(sequence_lengths) / len(sequence_lengths) if sequence_lengths else 0
    
    print(f"\nOVERALL STATISTICS:")
    print(f"   Total violations found: {total_violations_all}")
    print(f"   Average violations per file: {avg_violations:.3f}")
    print(f"   Average sequence length: {avg_sequence_length:.1f} tokens")
    print(f"   Min sequence length: {min(sequence_lengths) if sequence_lengths else 0}")
    print(f"   Max sequence length: {max(sequence_lengths) if sequence_lengths else 0}")
    
    # Circuit type statistics
    if circuit_type_stats:
        print(f"\nCIRCUIT TYPE DISTRIBUTION:")
        for circuit_type, count in sorted(circuit_type_stats.items(), key=lambda x: x[1], reverse=True):
            percentage = (count / processed * 100) if processed > 0 else 0
            print(f"   {circuit_type}: {count} files ({percentage:.1f}%)")
    
    # Quality assessment
    clean_count = len(clean_files)
    problematic_count = len(problematic_files)
    clean_percentage = (clean_count / processed * 100) if processed > 0 else 0
    
    print(f"\nQUALITY ASSESSMENT:")
    print(f"   Clean files (no violations): {clean_count} ({clean_percentage:.1f}%)")
    print(f"   Problematic files: {problematic_count} ({100-clean_percentage:.1f}%)")
    
    # Violation type breakdown
    print(f"\nVIOLATION TYPE BREAKDOWN:")
    print(f"   Test 1 (Device-Pin Rules): {test_stats['test1']} violations")
    print(f"   Test 2 (Missing Pins): {test_stats['test2']} violations")
    print(f"   Test 3 (Port Connections): {test_stats['test3']} violations")
    print(f"   Test 4 (Floating Nets): {test_stats['test4']} violations")
    
    if port_violations:
        print(f"\nTOP PROBLEMATIC PORTS:")
        top_ports = sorted(port_violations.items(), key=lambda x: x[1], reverse=True)[:10]
        for port, count in top_ports:
            print(f"   {port}: {count} violations")
    
    # Worst files
    if all_results:
        if problematic_files:
            print(f"\nWORST FILES (most violations):")
            worst_files = sorted(problematic_files, key=lambda x: x['total_violations'], reverse=True)[:10]
            for result in worst_files:
                print(f"   {result['filename']}: {result['total_violations']} violations "
                      f"(length {result['sequence_length']}, type: {result['circuit_type'] or 'N/A'})")
    
    # Save results
    results_data = {
        'summary': {
            'total_files': processed,
            'total_violations': total_violations_all,
            'avg_violations': avg_violations,
            'avg_sequence_length': avg_sequence_length,
            'clean_files_count': clean_count,
            'clean_percentage': clean_percentage,
            'analysis_time': total_time
        },
        'circuit_type_stats': dict(circuit_type_stats),
        'test_stats': test_stats,
        'violation_distribution': dict(violation_stats),
        'device_violations': dict(device_violations),
        'port_violations': dict(port_violations),
        'all_results': all_results
    }
    
    with open(output_file, 'w') as f:
        json.dump(results_data, f, indent=2)
    
    print(f"\nDetailed results saved to: {output_file}")
    
    return all_results


if __name__ == "__main__":
    import sys
    import numpy as np
    import time
    from collections import Counter
    
    # Priority: Command line arg > Environment variable > Default
    if len(sys.argv) > 1:
        input_path = sys.argv[1]
    else:
        input_path = "Inference"
    
    # Check if input is .npy file or directory
    if input_path.endswith('.npy'):
        # Process .npy file
        print(f"Processing .npy file: {input_path}")
        print(f"")
        
        # Decode function using global vocabulary
        def decode(seq):
            return [ITOS.get(int(idx), 'TRUNCATE') for idx in seq if int(idx) != STOI.get('TRUNCATE', len(VOCAB))]
        
        # Load data
        print(f"Loading {input_path}...")
        data = np.load(input_path, allow_pickle=True)
        print(f"Shape: {data.shape}")
        print(f"Total sequences: {data.shape[0]}")
        
        # Check data type
        sample = data[0][0] if len(data) > 0 else None
        is_string_format = isinstance(sample, str)
        print(f"Data format: {'String tokens' if is_string_format else 'Integer indices'}\n")
        
        # Track statistics
        circuit_types = defaultdict(lambda: {'total': 0, 'clean': 0})
        violation_counts = Counter()
        all_test1 = 0
        all_test2 = 0
        all_test3 = 0
        all_test4 = 0
        
        start_time = time.time()
        
        # Test all sequences
        for idx in range(len(data)):
            seq = data[idx]
            
            # Decode if integer format, otherwise use as-is
            if is_string_format:
                tokens = [t for t in seq if t != 'TRUNCATE']
            else:
                tokens = decode(seq)
            
            # Get circuit type
            circuit_type = tokens[0] if tokens and tokens[0].startswith('CIRCUIT_') else 'Unknown'
            circuit_types[circuit_type]['total'] += 1
            
            # Validate
            is_clean, test1_violations, test2_violations, test3_violations, test4_violations = run_rule_validation(tokens, verbose=False, debug=False)
            
            total_violations = len(test1_violations) + len(test2_violations) + len(test3_violations) + len(test4_violations)
            violation_counts[total_violations] += 1
            
            if is_clean:
                circuit_types[circuit_type]['clean'] += 1
            
            all_test1 += len(test1_violations)
            all_test2 += len(test2_violations)
            all_test3 += len(test3_violations)
            all_test4 += len(test4_violations)
            
            # Progress
            if (idx + 1) % 10000 == 0:
                elapsed = time.time() - start_time
                rate = (idx + 1) / elapsed
                print(f"Processed {idx+1}/{len(data)} ({rate:.0f} seq/s)")
        
        elapsed = time.time() - start_time
        rate = len(data) / elapsed
        
        print(f"\n{'='*60}")
        print(f"VALIDATION COMPLETE")
        print(f"Time: {elapsed:.2f}s ({rate:.0f} sequences/second)")
        print(f"\n{'='*60}")
        print(f"OVERALL STATISTICS")
        print(f"{'='*60}")
        
        clean_total = sum(ct['clean'] for ct in circuit_types.values())
        print(f"Clean sequences: {clean_total} ({100*clean_total/len(data):.2f}%)")
        print(f"Sequences with violations: {len(data) - clean_total} ({100*(len(data)-clean_total)/len(data):.2f}%)")
        print(f"\nTotal violations:")
        print(f"  Test1: {all_test1:,}")
        print(f"  Test2: {all_test2:,}")
        print(f"  Test3: {all_test3:,}")
        print(f"  Test4: {all_test4:,}")
        print(f"  TOTAL: {all_test1 + all_test2 + all_test3 + all_test4:,}")
        
        print(f"\n{'='*60}")
        print(f"BY CIRCUIT TYPE")
        print(f"{'='*60}")
        for circuit_type in sorted(circuit_types.keys()):
            stats = circuit_types[circuit_type]
            pct = 100 * stats['clean'] / stats['total'] if stats['total'] > 0 else 0
            print(f"{circuit_type:20s}: {stats['clean']:6d}/{stats['total']:6d} clean ({pct:5.2f}%)")
        
        print(f"\n{'='*60}")
        print(f"VIOLATION DISTRIBUTION")
        print(f"{'='*60}")
        for num_violations in sorted(violation_counts.keys())[:20]:
            count = violation_counts[num_violations]
            pct = 100 * count / len(data)
            print(f"{num_violations:3d} violations: {count:6d} sequences ({pct:5.2f}%)")
        
        # Show sample violations
        print(f"\n{'='*60}")
        print(f"SAMPLE VIOLATIONS (first 5 with issues)")
        print(f"{'='*60}")
        
        if total_violations == 0:
            print("No violations found - all sequences are clean!")
        else:
            log_filename = input_path.replace('.npy', '_violation_samples.txt')
            with open(log_filename, 'w') as log_file:
                log_file.write("="*80 + "\n")
                log_file.write("SAMPLE VIOLATIONS FROM " + input_path + "\n")
                log_file.write("="*80 + "\n\n")
                
                sample_count = 0
                for idx in range(len(data)):
                    seq = data[idx]
                    if is_string_format:
                        tokens = [t for t in seq if t != 'TRUNCATE']
                    else:
                        tokens = decode(seq)
                    
                    is_clean, test1_violations, test2_violations, test3_violations, test4_violations = run_rule_validation(tokens, verbose=False, debug=False)
                    
                    if not is_clean:
                        sample_count += 1
                        circuit_type = tokens[0] if tokens and tokens[0].startswith('CIRCUIT_') else 'Unknown'
                        
                        # Write to log file
                        log_file.write(f"\n{'='*80}\n")
                        log_file.write(f"SAMPLE {sample_count} - Index: {idx}\n")
                        log_file.write(f"{'='*80}\n")
                        log_file.write(f"Circuit type: {circuit_type}\n")
                        log_file.write(f"Length: {len(tokens)} tokens\n")
                        log_file.write(f"Violations: Test1={len(test1_violations)}, Test2={len(test2_violations)}, Test3={len(test3_violations)}, Test4={len(test4_violations)}\n")
                        log_file.write(f"\n{'='*80}\n")
                        log_file.write(f"FULL SEQUENCE (all tokens before TRUNCATE):\n")
                        log_file.write(f"{'='*80}\n")
                        log_file.write(' -> '.join(tokens) + "\n")
                    
                    if test1_violations:
                        log_file.write(f"\n{'-'*80}\n")
                        log_file.write(f"TEST 1 VIOLATIONS ({len(test1_violations)} total):\n")
                        log_file.write(f"{'-'*80}\n")
                        for v in test1_violations:
                            log_file.write(f"  {v}\n")
                    
                    if test2_violations:
                        log_file.write(f"\n{'-'*80}\n")
                        log_file.write(f"TEST 2 VIOLATIONS ({len(test2_violations)} total):\n")
                        log_file.write(f"{'-'*80}\n")
                        for v in test2_violations:
                            log_file.write(f"  {v}\n")
                    
                    if test3_violations:
                        log_file.write(f"\n{'-'*80}\n")
                        log_file.write(f"TEST 3 VIOLATIONS ({len(test3_violations)} total):\n")
                        log_file.write(f"{'-'*80}\n")
                        for v in test3_violations:
                            log_file.write(f"  {v}\n")
                    
                    if test4_violations:
                        log_file.write(f"\n{'-'*80}\n")
                        log_file.write(f"TEST 4 VIOLATIONS - FLOATING NETS ({len(test4_violations)} total):\n")
                        log_file.write(f"{'-'*80}\n")
                        for v in test4_violations:
                            log_file.write(f"  {v}\n")
                    
                    log_file.write("\n\n")
                    
                    # Print to console (summary only)
                    print(f"\n[Sample {sample_count}] Index: {idx}")
                    print(f"Circuit type: {circuit_type}")
                    print(f"Length: {len(tokens)} tokens")
                    print(f"Violations: Test1={len(test1_violations)}, Test2={len(test2_violations)}, Test3={len(test3_violations)}, Test4={len(test4_violations)}")
                    
                    if sample_count >= 5:
                        break
            
            print(f"\nDetailed violation samples saved to: {log_filename}")
    
    else:
        # Process directory (Inference folder)
        inference_dir = input_path
        print(f"Processing directory: {inference_dir}")
        
        if len(sys.argv) > 2:
            output_file = sys.argv[2]
        else:
            # Auto-generate output filename based on directory name
            dir_basename = os.path.basename(inference_dir.rstrip('/'))
            output_file = f"inference_analysis_{dir_basename}.json"
        
        print(f"Output file: {output_file}")
        print(f"")
        print(f"Usage options:")
        print(f"   1. For .npy file: python ERC.py Training.npy")
        print(f"   2. For .npy file: python ERC.py Validation.npy")
        print(f"   3. For directory: python ERC.py Inference_CIRCUIT_Opamp")
        print(f"   4. Default: python ERC.py (uses 'Inference' folder)")
        print(f"")
        
        # Run analysis
        results = analyze_inference_directory(inference_dir, output_file)