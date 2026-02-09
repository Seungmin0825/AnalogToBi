"""
METRIC_Valid_n_Novel.py

This script evaluates generated circuit sequences on two metrics:
1. Validity: ERC (Electrical Rule Check) pass rate per circuit type
2. Novelty: Whether ERC-passing circuits are absent from the training dataset

Output:
- ERC pass rate per circuit type
- Novel rate (ERC pass + not in dataset) per circuit type
"""

import os
import json
import glob
from pathlib import Path
import networkx as nx
from tqdm import tqdm
from collections import defaultdict
import pandas as pd
import re


# ============================================================================
# VOCABULARY
# ============================================================================
print("Building vocabulary...")

vocab_tokens = []

# 1. Edge types (connection types between nodes)
# MOSFET edges (M_ prefix)
MOSFET_EDGES = [
    'M_B', 'M_D', 'M_G', 'M_S',  # Single pin
    'M_BD', 'M_BG', 'M_BS', 'M_DG', 'M_DS', 'M_GS',  # Two pins
    'M_BDG', 'M_BDS', 'M_BGS', 'M_DGS',  # Three pins
    'M_BDGS'  # Four pins
]
vocab_tokens.extend(MOSFET_EDGES)

# BJT edges (B_ prefix)
BJT_EDGES = [
    'B_B', 'B_C', 'B_E',  # Single pin
    'B_BC', 'B_BE', 'B_CE',  # Two pins
    'B_BCE'  # Three pins
]
vocab_tokens.extend(BJT_EDGES)

# Passive device edges
PASSIVE_EDGES = ['R_C', 'C_C', 'L_C']
vocab_tokens.extend(PASSIVE_EDGES)

# Diode edges (D_ prefix)
DIODE_EDGES = ['D_P', 'D_N', 'D_NP', 'D_PN']
vocab_tokens.extend(DIODE_EDGES)

# All edge types
ALL_EDGES = set(MOSFET_EDGES + BJT_EDGES + PASSIVE_EDGES + DIODE_EDGES)

# 2. Power rails
vocab_tokens.extend(['VSS', 'VDD'])

# 3. Circuit type tokens
CIRCUIT_TYPE_TOKENS = [
    'CIRCUIT_Opamp', 'CIRCUIT_LDO', 'CIRCUIT_Bandgap_Ref',
    'CIRCUIT_Power_converter', 'CIRCUIT_Oscillator', 'CIRCUIT_General',
    'CIRCUIT_Mirror', 'CIRCUIT_Mixer', 'CIRCUIT_Power_Amp',
    'CIRCUIT_PLL', 'CIRCUIT_Filter', 'CIRCUIT_Comparator',
    'CIRCUIT_Voltage_Regulator', 'CIRCUIT_Switched_Cap', 'CIRCUIT_ADC_DAC'
]
vocab_tokens.extend(CIRCUIT_TYPE_TOKENS)

# 4. Device nodes
for i in range(1, 36):
    vocab_tokens.append(f'NM{i}')
for i in range(1, 36):
    vocab_tokens.append(f'PM{i}')
for i in range(1, 28):
    vocab_tokens.append(f'NPN{i}')
for i in range(1, 28):
    vocab_tokens.append(f'PNP{i}')
for i in range(1, 29):
    vocab_tokens.append(f'R{i}')
for i in range(1, 17):
    vocab_tokens.append(f'C{i}')
for i in range(1, 25):
    vocab_tokens.append(f'L{i}')
for i in range(1, 9):
    vocab_tokens.append(f'DIO{i}')

# 5. Net nodes: NET1-NET50
for i in range(1, 51):
    vocab_tokens.append(f'NET{i}')

# 6. Port nodes
for i in range(1, 21):
    vocab_tokens.append(f'VIN{i}')
vocab_tokens.append('VOUT')
for i in range(1, 8):
    vocab_tokens.append(f'VOUT{i}')
for i in range(1, 4):
    vocab_tokens.append(f'IIN{i}')
for i in range(1, 6):
    vocab_tokens.append(f'IOUT{i}')
for i in range(1, 12):
    vocab_tokens.append(f'VB{i}')
for i in range(1, 8):
    vocab_tokens.append(f'IB{i}')
for i in range(1, 22):
    vocab_tokens.append(f'VCONT{i}')
for i in range(1, 4):
    vocab_tokens.extend([f'VCM{i}', f'VREF{i}', f'IREF{i}', f'VRF{i}', f'VIF{i}'])
for i in range(1, 6):
    vocab_tokens.extend([f'VLO{i}', f'VBB{i}'])

# 7. Special tokens
vocab_tokens.append('TRUNCATE')

devices = vocab_tokens
stoi = {d: i for i, d in enumerate(devices)}
itos = {i: d for i, d in enumerate(devices)}
vocab_size = len(devices)

print(f"Vocabulary built: {vocab_size} tokens")

# Device prefixes
MOSFET_PREFIXES = ['NM', 'PM']
BJT_PREFIXES = ['NPN', 'PNP']
PASSIVE_PREFIXES = ['R', 'C', 'L']
DIODE_PREFIXES = ['DIO']


# ============================================================================
# ERC CHECKING FUNCTIONS
# ============================================================================
POWER_RAILS = ['VSS', 'VDD']
NET_PREFIX = 'NET'
PORT_PREFIXES = ['VIN', 'VOUT', 'IIN', 'IOUT', 'VB', 'IB', 'VCONT', 
                 'VCM', 'IREF', 'VLO', 'VBB', 'VRF', 'VIF', 'VREF']


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
    if token == 'VOUT':
        return True
    return False


def is_internal_net(token):
    """Check if token is an internal net (NET1-50), excluding external ports and power rails"""
    if token.startswith(NET_PREFIX) and token[len(NET_PREFIX):].isdigit():
        return True
    return False


def is_edge(token):
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


def check_sequence_first_test(tokens):
    """Test 1: Device-Edge-Net-Edge-Device Pattern"""
    violations = []
    
    for i in range(len(tokens)):
        token = tokens[i]
        
        if token in CIRCUIT_TYPE_TOKENS:
            continue
        
        if i == 0 or (i > 0 and tokens[i-1] in CIRCUIT_TYPE_TOKENS):
            if not (is_device_node(token) or is_net_node(token)):
                if not is_edge(token):
                    violations.append(f"Position {i}: Expected node, got '{token}'")
        else:
            prev_ctx = tokens[i-1]
            
            if is_device_node(prev_ctx) or is_net_node(prev_ctx):
                if not is_edge(token):
                    violations.append(f"Position {i}: After node '{prev_ctx}', expected edge, got '{token}'")
            elif is_edge(prev_ctx):
                if not (is_device_node(token) or is_net_node(token)):
                    violations.append(f"Position {i}: After edge '{prev_ctx}', expected node, got '{token}'")
    
    return violations


def check_sequence_second_test(tokens):
    """Test 2: Required Edge Validation"""
    violations = []
    device_edges = defaultdict(set)
    
    for i in range(len(tokens)):
        token = tokens[i]
        
        if is_device_node(token):
            if i > 0:
                prev_token = tokens[i - 1]
                if is_edge(prev_token):
                    device_edges[token].add(prev_token)
            
            if i + 1 < len(tokens):
                next_token = tokens[i + 1]
                if is_edge(next_token):
                    device_edges[token].add(next_token)
    
    for device, edges in device_edges.items():
        prefix = get_device_prefix(device)
        
        if prefix in MOSFET_PREFIXES:
            pins_used = set()
            for edge in edges:
                if edge.startswith('M_'):
                    pins = edge[2:]
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
            pins_used = set()
            for edge in edges:
                if edge.startswith('B_'):
                    pins = edge[2:]
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
            expected_edge = f'{prefix}_C'
            if expected_edge not in edges:
                violations.append(f"Device {device} (passive) missing edge {expected_edge}")
        
        elif prefix in DIODE_PREFIXES:
            pins_used = set()
            for edge in edges:
                if edge.startswith('D_'):
                    pins = edge[2:]
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
    """Test 3: Pin-Level Net Connection Validation"""
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
    """Test 4: Internal Net Connection Validation - ensure internal nets have >= 2 device connections"""
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


def passes_erc(tokens):
    """Check if sequence passes all ERC tests"""
    test1 = check_sequence_first_test(tokens)
    test2 = check_sequence_second_test(tokens)
    test3 = check_sequence_third_test(tokens)
    test4 = check_internal_net_connections(tokens)
    return len(test1) == 0 and len(test2) == 0 and len(test3) == 0 and len(test4) == 0


# ============================================================================
# GRAPH CONVERSION FUNCTIONS
# ============================================================================
def sequence_to_graph(seq):
    """
    Convert circuit sequence to bipartite graph representation.
    
    Returns:
        node_indices: List of unique node token indices (not edge types)
        edges: List of (src_idx, dst_idx, edge_type) tuples
    """
    seq_indices = [stoi.get(str(token), stoi.get('VSS', 0)) for token in seq]
    
    first_token_str = str(seq[0])
    start_idx = 1 if first_token_str.startswith('CIRCUIT_') else 0
    
    truncate_str = 'TRUNCATE'
    edge_types = ALL_EDGES
    
    # Extract nodes (skip edge types)
    nodes_set = set()
    seq_len = len(seq)
    
    for i in range(start_idx, seq_len):
        token_str = str(seq[i])
        if token_str == truncate_str:
            break
        if token_str not in edge_types:
            token_idx = seq_indices[i]
            nodes_set.add(token_idx)
    
    node_indices = sorted(list(nodes_set))
    node_to_graph_idx = {token_idx: graph_idx for graph_idx, token_idx in enumerate(node_indices)}
    
    # Build edges with types (format: node -> edge_type -> node)
    edges = []
    i = start_idx
    while i < seq_len - 1:
        token_str = str(seq[i])
        if token_str == truncate_str:
            break
        
        # Pattern: node -> edge_type -> node
        if token_str not in edge_types:
            node1_idx = seq_indices[i]
            
            # Look for edge_type -> node2
            if i + 2 < seq_len:
                edge_type_str = str(seq[i + 1])
                node2_str = str(seq[i + 2])
                
                if edge_type_str in edge_types and node2_str not in edge_types:
                    node2_idx = seq_indices[i + 2]
                    
                    if node1_idx in node_to_graph_idx and node2_idx in node_to_graph_idx:
                        graph_idx1 = node_to_graph_idx[node1_idx]
                        graph_idx2 = node_to_graph_idx[node2_idx]
                        
                        # Add undirected edges
                        edges.append((graph_idx1, graph_idx2, edge_type_str))
                        edges.append((graph_idx2, graph_idx1, edge_type_str))
        
        i += 1
    
    return node_indices, edges


def generalize_token(token_str):
    """Generalize token by removing device numbers (NM1 -> NM)"""
    special_tokens = {'VDD', 'VSS', 'TRUNCATE', 'VOUT'}
    
    # External ports (preserve identity)
    for i in range(1, 21):
        special_tokens.add(f"VIN{i}")
    for i in range(1, 8):
        special_tokens.add(f"VOUT{i}")
    for i in range(1, 4):
        special_tokens.add(f"IIN{i}")
    for i in range(1, 6):
        special_tokens.add(f"IOUT{i}")
    for i in range(1, 12):
        special_tokens.add(f"VB{i}")
    for i in range(1, 8):
        special_tokens.add(f"IB{i}")
    for i in range(1, 22):
        special_tokens.add(f"VCONT{i}")
    for i in range(1, 4):
        special_tokens.update([f"VCM{i}", f"VREF{i}", f"IREF{i}", f"VRF{i}", f"VIF{i}"])
    for i in range(1, 6):
        special_tokens.update([f"VLO{i}", f"VBB{i}"])
    
    # Edge types (preserve)
    if token_str in special_tokens or token_str in ALL_EDGES:
        return token_str
    
    if token_str.startswith('CIRCUIT_'):
        return token_str
    
    # Remove numbers: NM1->NM, NET1->NET
    generalized = re.sub(r'(\D+)\d+', r'\1', token_str)
    return generalized


def create_networkx_graph(seq, generalize_devices=True):
    """Create NetworkX graph from sequence (v13 bipartite with edge types)"""
    node_indices, edges = sequence_to_graph(seq)
    
    G = nx.Graph()
    
    # Add nodes with token type
    for graph_idx, token_idx in enumerate(node_indices):
        token_str = itos.get(token_idx, 'UNKNOWN')
        if generalize_devices:
            token_type = generalize_token(token_str)
        else:
            token_type = token_str
        G.add_node(graph_idx, token_type=token_type)
    
    # Add edges with edge type as attribute
    for src, dst, edge_type in edges:
        if src != dst:
            if generalize_devices:
                edge_type_gen = generalize_token(edge_type)
            else:
                edge_type_gen = edge_type
            G.add_edge(src, dst, edge_type=edge_type_gen)
    
    return G


def graphs_are_isomorphic(G1, G2):
    """Check if two graphs are isomorphic (considering both node types and edge types)"""
    if G1.number_of_nodes() != G2.number_of_nodes():
        return False
    if G1.number_of_edges() != G2.number_of_edges():
        return False
    
    def node_match(n1, n2):
        return n1.get('token_type') == n2.get('token_type')
    
    def edge_match(e1, e2):
        return e1.get('edge_type') == e2.get('edge_type')
    
    return nx.is_isomorphic(G1, G2, node_match=node_match, edge_match=edge_match)


# ============================================================================
# DATASET LOADING
# ============================================================================
def load_csv_bipartite_graph(csv_path, generalize_devices=True):
    """Load bipartite graph from a CSV adjacency matrix with typed edges."""
    df = pd.read_csv(csv_path, index_col=0)
    
    G = nx.Graph()
    nodes = list(df.index)
    
    # Add nodes
    for idx, node_name in enumerate(nodes):
        if generalize_devices:
            token_type = generalize_token(str(node_name))
        else:
            token_type = str(node_name)
        G.add_node(idx, token_type=token_type)
    
    # Add edges with types
    for i, node1 in enumerate(nodes):
        for j, node2 in enumerate(nodes):
            if i < j:
                edge_type = df.iloc[i, j]
                if edge_type != '0' and edge_type != 0 and pd.notna(edge_type):
                    edge_type_str = str(edge_type)
                    if generalize_devices:
                        edge_type_gen = generalize_token(edge_type_str)
                    else:
                        edge_type_gen = edge_type_str
                    G.add_edge(i, j, edge_type=edge_type_gen)
    
    return G


def load_dataset_graphs():
    """Load all dataset graphs from Graph_Bipart*.csv files"""
    print("\nLoading dataset graphs from CSV files...")
    
    dataset_path = "Dataset"
    graphs = []
    
    # Find all Graph_Bipart*.csv files
    for folder_num in tqdm(range(1, 3351), desc="Loading dataset"):
        csv_path = os.path.join(dataset_path, str(folder_num), f"Graph_Bipart{folder_num}.csv")
        
        if not os.path.exists(csv_path):
            continue
        
        try:
            G = load_csv_bipartite_graph(csv_path, generalize_devices=True)
            if G.number_of_nodes() > 0:
                graphs.append(G)
        except Exception:
            continue
    
    print(f"Loaded {len(graphs)} dataset graphs\n")
    return graphs


# ============================================================================
# MAIN ANALYSIS
# ============================================================================
def analyze_inference_folder(inference_dir, dataset_graphs):
    """Analyze one inference folder for validity (ERC) and novelty."""
    results = {
        'total': 0,
        'erc_pass': 0,
        'erc_pass_novel': 0,
        'all_novel': 0,
        'all_graphs': []
    }
    
    # Get circuit type from folder name
    folder_name = os.path.basename(inference_dir)
    if folder_name.startswith("Inference_CIRCUIT_"):
        circuit_type = folder_name.replace("Inference_CIRCUIT_", "").replace("_masked", "")
    else:
        circuit_type = "Unknown"
    
    # Process all txt files
    txt_files = sorted(glob.glob(os.path.join(inference_dir, "*.txt")))
    results['total'] = len(txt_files)
    
    for txt_file in tqdm(txt_files, desc=f"  Processing {circuit_type}", leave=True, ncols=100, mininterval=0.1):
        try:
            with open(txt_file, 'r') as f:
                content = f.read().strip()
                if '->' not in content:
                    continue
                tokens = [t.strip() for t in content.split('->') if t.strip() and t.strip() != 'TRUNCATE']
                if not tokens:
                    continue
                
                # Remove CIRCUIT_ prefix token (first token)
                if tokens and tokens[0].startswith('CIRCUIT_'):
                    tokens = tokens[1:]
                
                if not tokens:
                    continue
            
            # Convert to graph for novelty check (ERC independent)
            try:
                G_all = create_networkx_graph(tokens, generalize_devices=True)
                if G_all.number_of_nodes() > 0:
                    results['all_graphs'].append(G_all)
            except Exception:
                pass
            
            # Check ERC
            passes_erc_check = passes_erc(tokens)
            
            if not passes_erc_check:
                continue
            
            results['erc_pass'] += 1
            
            # Check novelty for ERC-passing circuits
            try:
                G_gen = create_networkx_graph(tokens, generalize_devices=True)
                
                if G_gen.number_of_nodes() == 0:
                    continue
                
                is_novel = True
                for G_dataset in dataset_graphs:
                    if graphs_are_isomorphic(G_gen, G_dataset):
                        is_novel = False
                        break
                
                if is_novel:
                    results['erc_pass_novel'] += 1
            except Exception:
                continue
        
        except Exception:
            continue
    
    # Check novelty for ALL generated circuits (ERC independent)
    print(f"  Checking novelty for {len(results['all_graphs'])} circuits...")
    
    for G_all in tqdm(results['all_graphs'], desc="  Novelty check", leave=True, ncols=100, mininterval=0.5):
        is_novel = True
        for G_dataset in dataset_graphs:
            if graphs_are_isomorphic(G_all, G_dataset):
                is_novel = False
                break
        if is_novel:
            results['all_novel'] += 1
    
    return results


def main():
    print("="*80)
    print("VALIDITY & NOVELTY ANALYSIS")
    print("="*80)
    print()
    
    # Load dataset graphs once
    dataset_graphs = load_dataset_graphs()
    
    # Find all Inference folders
    inference_folders = sorted(glob.glob("Inference_CIRCUIT_*"))
    
    if not inference_folders:
        print("No Inference folders found.")
        return
    
    print(f"Found {len(inference_folders)} inference folders\n")
    
    # Analyze folders
    results_list = []
    
    print("="*80)
    print("ANALYZING INFERENCE FOLDERS")
    print("="*80)
    print()
    
    for inference_dir in inference_folders:
        folder_name = os.path.basename(inference_dir)
        circuit_type = folder_name.replace("Inference_CIRCUIT_", "").replace("_masked", "")
        print(f"Analyzing {circuit_type}...")
        
        results = analyze_inference_folder(inference_dir, dataset_graphs)
        results['circuit_type'] = circuit_type
        results_list.append(results)
        
        print(f"  Total: {results['total']}")
        print(f"  All Novel (no ERC): {results['all_novel']} ({results['all_novel']/results['total']*100:.1f}%)")
        print(f"  ERC Pass: {results['erc_pass']} ({results['erc_pass']/results['total']*100:.1f}%)")
        print(f"  ERC + Novel: {results['erc_pass_novel']} ({results['erc_pass_novel']/results['total']*100:.1f}%)")
        print()
    
    # Define circuit type order
    circuit_order = [
        'Opamp', 'Mirror', 'Comparator', 'Mixer', 'LDO', 'Oscillator',
        'Filter', 'Bandgap_Ref', 'Power_Amp', 'Voltage_Regulator',
        'Power_converter', 'PLL', 'Switched_Cap', 'ADC_DAC', 'General'
    ]
    
    def get_sort_key(result):
        circuit_type = result['circuit_type']
        try:
            return circuit_order.index(circuit_type)
        except ValueError:
            return len(circuit_order)
    
    # Summary table
    print("="*80)
    print("SUMMARY TABLE")
    print("="*80)
    
    results_sorted = sorted(results_list, key=get_sort_key)
    
    df = pd.DataFrame([
        {
            'Circuit Type': r['circuit_type'],
            'Total': r['total'],
            'All Novel': r['all_novel'],
            'All Novel %': f"{r['all_novel']/r['total']*100:.1f}%",
            'ERC Pass': r['erc_pass'],
            'ERC Pass %': f"{r['erc_pass']/r['total']*100:.1f}%",
            'ERC+Novel': r['erc_pass_novel'],
            'ERC+Novel %': f"{r['erc_pass_novel']/r['total']*100:.1f}%"
        }
        for r in results_sorted
    ])
    
    print(df.to_string(index=False))
    print()
    
    # Save to CSV
    output_file = "METRIC_Valid_n_Novel_RESULTS.csv"
    df.to_csv(output_file, index=False)
    print(f"Results saved to {output_file}")
    
    # Overall statistics
    total = sum(r['total'] for r in results_list)
    all_novel = sum(r['all_novel'] for r in results_list)
    erc_pass = sum(r['erc_pass'] for r in results_list)
    novel = sum(r['erc_pass_novel'] for r in results_list)
    
    print()
    print("="*80)
    print("OVERALL STATISTICS")
    print("="*80)
    print(f"Total circuits: {total}")
    print(f"All novel (no ERC): {all_novel} ({all_novel/total*100:.1f}%)")
    print(f"ERC pass: {erc_pass} ({erc_pass/total*100:.1f}%)")
    print(f"ERC + Novel: {novel} ({novel/total*100:.1f}%)")
    print("="*80)


if __name__ == "__main__":
    main()
