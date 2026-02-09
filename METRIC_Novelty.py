"""
Batch Novelty Analysis for Generated Circuits

Measures novelty of generated analog circuit topologies by checking graph isomorphism
against training dataset. A circuit is considered novel if its topology (represented
as a bipartite graph with typed edges) is not isomorphic to any circuit in the
training set.

Novelty Definition (Paper):
- Novel: Circuit topology not isomorphic to any training circuit
- Duplicate: Circuit topology isomorphic to at least one training circuit
- Uses NetworkX graph isomorphism with node type and edge type matching

Graph Representation:
- Nodes: Devices (MOSFETs, BJTs, passives) and nets (internal/external)
- Edges: Typed connections (M_GS, M_D, B_BC, R_C, etc.)
- Generalization: Device numbers removed (NM1/NM2 → NM, NET1/NET2 → NET)
- Bipartite structure with device-edge-net pattern preserved

Batch Processing:
- Processes multiple inference result directories
- Per-circuit-type novelty statistics
- Overall novelty rate across all circuit types
- Output: JSON files with novelty metrics and isomorphic pairs
"""

import os
import json
import argparse
from pathlib import Path
import numpy as np
import networkx as nx
import pandas as pd
from tqdm import tqdm
from collections import defaultdict


# Build vocabulary
print("Building vocabulary...")

vocab_tokens = []

# Edge types
vocab_tokens.extend([
    'M_B', 'M_D', 'M_G', 'M_S',
    'M_BD', 'M_BG', 'M_BS', 'M_DG', 'M_DS', 'M_GS',
    'M_BDG', 'M_BDS', 'M_BGS', 'M_DGS',
    'M_BDGS'
])
vocab_tokens.extend([
    'B_B', 'B_C', 'B_E',
    'B_BC', 'B_BE', 'B_CE',
    'B_BCE'
])
vocab_tokens.extend(['R_C', 'C_C', 'L_C'])
vocab_tokens.extend(['D_P', 'D_N', 'D_NP', 'D_PN'])

# Power rails
vocab_tokens.extend(['VSS', 'VDD'])

# Circuit types
circuit_type_tokens = [
    'CIRCUIT_Opamp', 'CIRCUIT_LDO', 'CIRCUIT_Bandgap_Ref',
    'CIRCUIT_Power_converter', 'CIRCUIT_Oscillator', 'CIRCUIT_General',
    'CIRCUIT_Mirror', 'CIRCUIT_Mixer', 'CIRCUIT_Power_Amp',
    'CIRCUIT_PLL', 'CIRCUIT_Filter', 'CIRCUIT_Comparator',
    'CIRCUIT_Voltage_Regulator', 'CIRCUIT_Switched_Cap', 'CIRCUIT_ADC_DAC'
]
vocab_tokens.extend(circuit_type_tokens)

# Device tokens
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

# Net nodes
for i in range(1, 51):
    vocab_tokens.append(f'NET{i}')

# Port nodes
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

vocab_tokens.append('TRUNCATE')

devices = vocab_tokens
stoi = {d: i for i, d in enumerate(devices)}
itos = {i: d for i, d in enumerate(devices)}
vocab_size = len(devices)

print(f"Vocabulary built: {vocab_size} tokens")


def sequence_to_graph(seq):
    """
    Convert circuit sequence to bipartite graph representation
    
    Args:
        seq: Token sequence from generated circuit
    
    Returns:
        node_indices: List of unique node token indices (excludes edge types)
        edges: List of (src_idx, dst_idx, edge_type) tuples
    """
    seq_indices = [stoi.get(str(token), stoi.get('VSS', 0)) for token in seq]
    
    first_token_str = str(seq[0])
    start_idx = 1 if first_token_str.startswith('CIRCUIT_') else 0
    
    truncate_str = 'TRUNCATE'
    
    # Edge type tokens (these appear between nodes but are not nodes themselves)
    edge_types = {'M_B', 'M_D', 'M_G', 'M_S', 'M_BD', 'M_BG', 'M_BS', 'M_DG', 'M_DS', 'M_GS',
                  'M_BDG', 'M_BDS', 'M_BGS', 'M_DGS', 'M_BDGS',
                  'B_B', 'B_C', 'B_E', 'B_BC', 'B_BE', 'B_CE', 'B_BCE',
                  'R_C', 'C_C', 'L_C', 'D_P', 'D_N', 'D_NP', 'D_PN'}
    
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
    """
    Generalize token by removing instance numbers for topology comparison
    
    Examples: NM1/NM2 → NM, NET1/NET2 → NET, R5 → R
    Preserves: External ports (VIN1, VOUT), edge types (M_GS, R_C)
    """
    import re
    
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
    
    # Edge types (preserve, with prefixes)
    edge_types = {'M_B', 'M_D', 'M_G', 'M_S', 'M_BD', 'M_BG', 'M_BS', 'M_DG', 'M_DS', 'M_GS',
                  'M_BDG', 'M_BDS', 'M_BGS', 'M_DGS', 'M_BDGS',
                  'B_B', 'B_C', 'B_E', 'B_BC', 'B_BE', 'B_CE', 'B_BCE',
                  'R_C', 'C_C', 'L_C', 'D_P', 'D_N', 'D_NP', 'D_PN'}
    
    if token_str in special_tokens or token_str in edge_types:
        return token_str
    
    if token_str.startswith('CIRCUIT_'):
        return token_str
    
    # Remove numbers: NM1->NM, NET1->NET
    generalized = re.sub(r'(\D+)\d+', r'\1', token_str)
    return generalized


def create_networkx_graph(seq, generalize_devices=True):
    """
    Create NetworkX graph from circuit sequence with typed edges
    
    Args:
        seq: Token sequence
        generalize_devices: Whether to remove device instance numbers
    
    Returns:
        NetworkX graph with node types and edge types as attributes
    """
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
    """
    Check graph isomorphism with node type and edge type matching
    
    Returns:
        True if graphs are topologically identical (isomorphic)
    """
    if G1.number_of_nodes() != G2.number_of_nodes():
        return False
    if G1.number_of_edges() != G2.number_of_edges():
        return False
    
    def node_match(n1, n2):
        return n1.get('token_type') == n2.get('token_type')
    
    def edge_match(e1, e2):
        return e1.get('edge_type') == e2.get('edge_type')
    
    return nx.is_isomorphic(G1, G2, node_match=node_match, edge_match=edge_match)


def load_csv_bipartite_graph(csv_path, generalize_devices=True):
    """
    Load bipartite graph from CSV adjacency matrix
    
    CSV format: Adjacency matrix where cell values are edge types
    """
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
    seen_edges = set()
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


def load_dataset_graphs(dataset_path, max_graphs=None):
    """
    Load training dataset graphs from Graph_Bipart*.csv files
    
    Args:
        dataset_path: Path to dataset directory
        max_graphs: Maximum graphs to load (None = load all)
    
    Returns:
        List of (folder_num, graph) tuples
    """
    print(f"\nLoading dataset from {dataset_path}...")
    
    graphs = []
    
    # Find all Graph_Bipart*.csv files
    for folder_num in tqdm(range(1, 3351), desc="Loading dataset"):
        csv_path = os.path.join(dataset_path, str(folder_num), f"Graph_Bipart{folder_num}.csv")
        
        if not os.path.exists(csv_path):
            continue
        
        try:
            G = load_csv_bipartite_graph(csv_path, generalize_devices=True)
            if G.number_of_nodes() > 0:
                graphs.append((folder_num, G))
        except Exception as e:
            continue
        
        if max_graphs and len(graphs) >= max_graphs:
            break
    
    print(f"Successfully loaded {len(graphs)} graphs")
    return graphs


def load_txt_file(txt_path):
    """Load circuit sequence from txt file"""
    with open(txt_path, 'r') as f:
        content = f.read().strip()
    tokens = content.split('->')
    return tokens


def load_txt_directory(directory_path, max_files=None):
    """Load all txt files from directory"""
    import glob
    import re
    
    txt_files = glob.glob(os.path.join(directory_path, '*.txt'))
    
    file_info = []
    for txt_file in txt_files:
        filename = os.path.basename(txt_file)
        match = re.search(r'(\d+)', filename)
        if match:
            file_num = int(match.group(1))
            file_info.append((file_num, txt_file))
        else:
            file_info.append((-1, txt_file))
    
    file_info.sort(key=lambda x: x[0])
    
    if max_files is not None:
        file_info = file_info[:max_files]
    
    sequences = []
    for file_num, txt_file in tqdm(file_info, desc="Loading txt files"):
        try:
            seq = load_txt_file(txt_file)
            sequences.append((file_num, seq))
        except Exception as e:
            continue
    
    return sequences


def measure_novelty(query_sequences, reference_graphs, verbose=True):
    """
    Measure novelty by checking graph isomorphism against training set
    
    Args:
        query_sequences: Generated circuit sequences to evaluate
        reference_graphs: Training dataset graphs
        verbose: Print progress information
    
    Returns:
        Dictionary with novelty statistics and isomorphic pairs
    """
    if verbose:
        print(f"\nChecking novelty for {len(query_sequences)} query sequences...")
        print(f"Reference set contains {len(reference_graphs)} graphs")
    
    results = {
        'total_queries': len(query_sequences),
        'novel_circuits': 0,
        'duplicate_circuits': 0,
        'novel_indices': [],
        'duplicate_indices': [],
        'isomorphic_pairs': []
    }
    
    for query_item in tqdm(query_sequences, desc="Checking novelty", disable=not verbose):
        try:
            if isinstance(query_item, tuple):
                query_idx, query_seq = query_item
            else:
                query_idx = query_sequences.index(query_item)
                query_seq = query_item
            
            query_graph = create_networkx_graph(query_seq, generalize_devices=True)
            
            is_novel = True
            
            for ref_item in reference_graphs:
                if isinstance(ref_item, tuple):
                    ref_idx, ref_graph = ref_item
                else:
                    ref_idx = reference_graphs.index(ref_item)
                    ref_graph = ref_item
                
                if graphs_are_isomorphic(query_graph, ref_graph):
                    is_novel = False
                    results['isomorphic_pairs'].append((query_idx, ref_idx))
                    break
            
            if is_novel:
                results['novel_circuits'] += 1
                results['novel_indices'].append(query_idx)
            else:
                results['duplicate_circuits'] += 1
                results['duplicate_indices'].append(query_idx)
        
        except Exception as e:
            print(f"\nWarning: Failed to process query {query_idx}: {e}")
            continue
    
    if results['total_queries'] > 0:
        results['novelty_rate'] = results['novel_circuits'] / results['total_queries']
        results['duplicate_rate'] = results['duplicate_circuits'] / results['total_queries']
    else:
        results['novelty_rate'] = 0.0
        results['duplicate_rate'] = 0.0
    
    return results


def find_inference_results(base_dir='.', pattern='Inference_CIRCUIT_*/'):
    """Find all inference result directories"""
    inference_dirs = []
    
    for path in Path(base_dir).glob(pattern):
        if path.is_dir():
            # Use directory path for txt files
            inference_dirs.append((str(path), str(path)))
    
    return inference_dirs


def main():
    parser = argparse.ArgumentParser(
        description='Batch novelty analysis for v6 (bipartite graphs)'
    )
    
    parser.add_argument('--reference', type=str, default='Dataset/',
                       help='Reference dataset directory (default: Dataset/)')
    parser.add_argument('--output-dir', type=str, default='novelty_results',
                       help='Output directory (default: novelty_results)')
    parser.add_argument('--pattern', type=str, default='Inference_CIRCUIT_*/',
                       help='Pattern to match inference directories')
    parser.add_argument('--max-ref', type=int, default=None,
                       help='Maximum number of reference graphs to load')
    
    args = parser.parse_args()
    
    os.makedirs(args.output_dir, exist_ok=True)
    
    # Find inference results
    inference_dirs = find_inference_results(pattern=args.pattern)
    
    if not inference_dirs:
        print(f"No inference directories found matching pattern: {args.pattern}")
        return
    
    print(f"Found {len(inference_dirs)} inference result directories")
    
    # Load reference graphs
    print(f"\n{'='*60}")
    print("Loading reference dataset...")
    print(f"{'='*60}")
    reference_graphs = load_dataset_graphs(args.reference, max_graphs=args.max_ref)
    
    # Analyze each inference result
    all_results = {}
    
    for dir_path, query_path in inference_dirs:
        circuit_type = Path(dir_path).name
        print(f"\n{'='*60}")
        print(f"Analyzing: {circuit_type}")
        print(f"{'='*60}")
        
        output_file = os.path.join(args.output_dir, f"{circuit_type}_novelty.json")
        
        try:
            # Load query sequences
            query_sequences = load_txt_directory(query_path)
            print(f"Loaded {len(query_sequences)} query sequences")
            
            results = measure_novelty(query_sequences, reference_graphs, verbose=True)
            
            if results:
                all_results[circuit_type] = results
                
                # Save results
                results_serializable = {
                    'total_queries': int(results['total_queries']),
                    'novel_circuits': int(results['novel_circuits']),
                    'duplicate_circuits': int(results['duplicate_circuits']),
                    'novelty_rate': float(results['novelty_rate']),
                    'duplicate_rate': float(results['duplicate_rate']),
                    'novel_indices': [int(x) for x in results['novel_indices']],
                    'duplicate_indices': [int(x) for x in results['duplicate_indices']],
                    'isomorphic_pairs': [(int(q), int(r)) for q, r in results['isomorphic_pairs']]
                }
                
                with open(output_file, 'w') as f:
                    json.dump(results_serializable, f, indent=2)
                
                print(f"Results saved to: {output_file}")
        
        except Exception as e:
            print(f"Error processing {circuit_type}: {e}")
            continue
    
    # Generate summary
    summary_file = os.path.join(args.output_dir, 'summary.json')
    
    summary = {
        'reference': args.reference,
        'results_by_circuit_type': {}
    }
    
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print(f"{'Circuit Type':<40} {'Novel':<10} {'Rate':<10}")
    print('-'*60)
    
    total_queries = 0
    total_novel = 0
    
    for circuit_type, results in sorted(all_results.items()):
        summary['results_by_circuit_type'][circuit_type] = {
            'total': results['total_queries'],
            'novel': results['novel_circuits'],
            'duplicate': results['duplicate_circuits'],
            'novelty_rate': results['novelty_rate']
        }
        
        total_queries += results['total_queries']
        total_novel += results['novel_circuits']
        
        print(f"{circuit_type:<40} {results['novel_circuits']:<10} {results['novelty_rate']*100:>6.2f}%")
    
    print('-'*60)
    
    if total_queries > 0:
        overall_rate = total_novel / total_queries
        print(f"{'OVERALL':<40} {total_novel:<10} {overall_rate*100:>6.2f}%")
        
        summary['overall'] = {
            'total_queries': total_queries,
            'novel_circuits': total_novel,
            'novelty_rate': overall_rate
        }
    
    print('='*60)
    
    # Save summary
    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2)
    
    print(f"\nSummary saved to: {summary_file}")
    print(f"Individual results saved to: {args.output_dir}/")


if __name__ == '__main__':
    main()
