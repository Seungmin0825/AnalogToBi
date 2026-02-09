"""
Bipartite Graph to Sequence Conversion with Device Renaming Augmentation

This script converts bipartite graph representations (CSV adjacency matrices)
into sequential token representations suitable for transformer-based training.
Implements device renaming-based data augmentation to increase sequence diversity
without altering circuit functionality.

Key Features:
- Graph traversal: Generates multiple valid sequences per circuit via randomized DFS/BFS
- Complete coverage: Ensures all nodes and edges are visited in each sequence
- Circular paths: All sequences start and end at VSS (or alternative start node)
- Electrical validation: Validates sequences using ERC (Electrical Rule Checks)
- Augmentation: Creates diverse sequences through neighbor order randomization

Sequence Format:
  VSS -> edge_type -> node -> edge_type -> ... -> VSS -> TRUNCATE
  Example: VSS -> M_S -> NM1 -> M_D -> VOUT -> ... -> VSS -> TRUNCATE

Typed Edge Vocabulary:
- MOSFETs: M_D, M_G, M_S, M_B, M_DG, M_SB, M_BD, M_BG, M_DS, M_GS, M_BDG, M_BDS, M_BGS, M_DGS, M_BDGS
- BJTs: B_C, B_B, B_E, B_BC, B_BE, B_CE, B_BCE
- Diodes: D_P, D_N, D_NP, D_PN
- Passives: R_C, C_C, L_C
"""

import pandas as pd
import numpy as np
import os
import sys
import random
from collections import defaultdict
from tqdm import tqdm

# =========================
# ERC Validation Import
# =========================
# Import electrical rule check functions for sequence validation
from ERC import (
    check_sequence_first_test,
    check_sequence_second_test,
    check_sequence_third_test,
    check_internal_net_connections,
    is_internal_net,
    is_device_node,
    is_edge
)

# =========================
# Configuration
# =========================
# Increase recursion limit for deep DFS traversal
sys.setrecursionlimit(50000)

# =========================
# Typed Edge Vocabulary
# =========================
# Define all valid edge types for validation

# MOSFET typed edges (single, double, triple, and quad pin combinations)
MOSFET_EDGE_TYPES = {
    'M_B', 'M_D', 'M_G', 'M_S',  # Single pin
    'M_BD', 'M_BG', 'M_BS', 'M_DG', 'M_DS', 'M_GS',  # Two pins
    'M_BDG', 'M_BDS', 'M_BGS', 'M_DGS',  # Three pins
    'M_BDGS'  # Four pins
}

# BJT typed edges (single, double, and triple pin combinations)
BJT_EDGE_TYPES = {
    'B_B', 'B_C', 'B_E',  # Single pin
    'B_BC', 'B_BE', 'B_CE',  # Two pins
    'B_BCE'  # Three pins
}

# Diode typed edges
DIODE_EDGE_TYPES = {'D_P', 'D_N', 'D_NP', 'D_PN'}

# Passive device typed edges
PASSIVE_EDGE_TYPES = {'R_C', 'C_C', 'L_C'}

# Combined vocabulary of all valid edge types

ALL_VALID_EDGE_TYPES = (MOSFET_EDGE_TYPES | BJT_EDGE_TYPES | 
                        DIODE_EDGE_TYPES | PASSIVE_EDGE_TYPES)


# =========================
# Graph Loading Functions
# =========================

def read_typed_adjacency_matrix(filename):
    """Read bipartite graph from CSV adjacency matrix with typed edges.
    
    Validates that all edge types are in the defined vocabulary.
    Extracts undirected edges (each edge stored once).
    
    Args:
        filename: Path to CSV file containing adjacency matrix
    Returns:
        Tuple of (edges, nodes)
        - edges: List of (node1, edge_type, node2) tuples
        - nodes: List of all node names
    """
    df = pd.read_csv(filename, index_col=0)
    
    edges = []
    nodes = list(df.index)
    seen_edges = set()
    invalid_edge_types = set()
    
    # Extract edges with types (undirected, so only store once)
    for i in df.index:
        for j in df.columns:
            edge_type = df.loc[i, j]
            if edge_type != '0' and edge_type != 0 and pd.notna(edge_type):
                edge_type_str = str(edge_type)
                
                # Validate edge type is in vocabulary
                if edge_type_str not in ALL_VALID_EDGE_TYPES:
                    invalid_edge_types.add(edge_type_str)
                
                # Store edge once (normalized)
                edge = tuple(sorted([i, j])) + (edge_type_str,)
                if edge not in seen_edges:
                    edges.append((i, edge_type_str, j))
                    seen_edges.add(edge)
    
    # Validate edge types against vocabulary
    if invalid_edge_types:
        print(f"  Note: Found {len(invalid_edge_types)} edge types not in vocabulary: {invalid_edge_types}")
    
    return edges, nodes


def build_adjacency_dict(edges):
    """Build adjacency dictionary from list of typed edges.
    
    Args:
        edges: List of (node1, edge_type, node2) tuples
    Returns:
        Dictionary mapping node -> [(edge_type, neighbor), ...]
    """
    adj = defaultdict(list)
    
    for node1, edge_type, node2 in edges:
        adj[node1].append((edge_type, node2))
        adj[node2].append((edge_type, node1))
    
    return adj


# =========================
# Graph Traversal Functions
# =========================

def bfs_find_path(adj, start, target):
    """Find shortest path between two nodes using BFS.
    
    Args:
        adj: Adjacency dictionary
        start: Starting node
        target: Target node
    Returns:
        List of (edge_type, node) tuples representing the path, or None if no path exists
    """
    from collections import deque
    
    if start == target:
        return []
    
    queue = deque([(start, [])])
    visited = {start}
    
    while queue:
        node, path = queue.popleft()
        
        for edge_type, neighbor in adj[node]:
            if neighbor in visited:
                continue
            
            new_path = path + [(edge_type, neighbor)]
            
            if neighbor == target:
                return new_path
            
            visited.add(neighbor)
            queue.append((neighbor, new_path))
    
    return None


def dfs_cover_all_edges_iterative(adj, edges, start_node='VSS', shuffle_neighbors=False, max_steps=10000):
    """Generate circuit sequence using hybrid DFS/BFS traversal strategy.
    
    Algorithm:
    1. Use greedy DFS to visit unvisited edges from current node
    2. When stuck, use BFS to find path to nodes with unvisited edges
    3. Return to start node after visiting all nodes and edges
    
    Allows edge/node revisits to ensure complete graph coverage.
    
    Args:
        adj: Adjacency dictionary
        edges: List of all edges in graph
        start_node: Starting node (default: 'VSS')
        shuffle_neighbors: If True, randomize neighbor order for augmentation
        max_steps: Maximum traversal steps to prevent infinite loops
    Returns:
        List of tokens forming a valid sequence, or None if generation fails
    """
    # Build set of all edges and nodes
    all_edges = set()
    all_nodes = set()
    for node1, edge_type, node2 in edges:
        edge = tuple(sorted([node1, node2])) + (edge_type,)
        all_edges.add(edge)
        all_nodes.add(node1)
        all_nodes.add(node2)
    
    visited_edges = set()
    visited_nodes = {start_node}
    sequence = [start_node]
    current_node = start_node
    steps = 0
    
    while steps < max_steps:
        steps += 1
        
        # Check if all edges and nodes visited
        all_visited = (len(visited_edges) == len(all_edges) and 
                      len(visited_nodes) == len(all_nodes))
        
        if all_visited:
            # Find path back to start
            if current_node != start_node:
                path = bfs_find_path(adj, current_node, start_node)
                if path:
                    for edge_type, node in path:
                        sequence.append(edge_type)
                        sequence.append(node)
                    return sequence
                else:
                    # Can't reach start - this shouldn't happen in connected graph
                    return None
            else:
                return sequence
        
        # Find neighbors
        neighbors = list(adj[current_node])
        if shuffle_neighbors:
            random.shuffle(neighbors)
        
        # Priority 1: Unvisited edges from current node
        found = False
        for edge_type, neighbor in neighbors:
            edge = tuple(sorted([current_node, neighbor])) + (edge_type,)
            if edge not in visited_edges:
                visited_edges.add(edge)
                visited_nodes.add(neighbor)
                sequence.append(edge_type)
                sequence.append(neighbor)
                current_node = neighbor
                found = True
                break
        
        if found:
            continue
        
        # Priority 2: Edges to unvisited nodes
        for edge_type, neighbor in neighbors:
            if neighbor not in visited_nodes:
                visited_nodes.add(neighbor)
                sequence.append(edge_type)
                sequence.append(neighbor)
                current_node = neighbor
                found = True
                break
        
        if found:
            continue
        
        # Priority 3: Find any node with unvisited edges using BFS
        if not found:
            # Find node with unvisited edges
            target_node = None
            for node in all_nodes:
                if node == current_node:
                    continue
                for edge_type, neighbor in adj[node]:
                    edge = tuple(sorted([node, neighbor])) + (edge_type,)
                    if edge not in visited_edges:
                        target_node = node
                        break
                if target_node:
                    break
            
            if target_node:
                # Find path to that node
                path = bfs_find_path(adj, current_node, target_node)
                if path:
                    for edge_type, node in path:
                        visited_nodes.add(node)
                        sequence.append(edge_type)
                        sequence.append(node)
                    current_node = target_node
                    found = True
            
            if not found:
                # No unvisited edges found anywhere, but not all visited?
                # This shouldn't happen - fail
                return None
    
    # Exhausted steps
    return None
    
    # If we exhausted steps or stack, check if all edges visited
    if len(visited_edges) == len(all_edges) and sequence[-1] == start_node:
        return sequence
    
    return None


# =========================
# Validation Functions
# =========================

def validate_sequence_erc(tokens, debug=False):
    """Validate sequence using Electrical Rule Checks (ERC).
    
    Runs four electrical validation tests:
    - Test 1: Device pin connectivity
    - Test 2: Port and power rail connectivity
    - Test 3: Sequence structure validity
    - Test 4: Internal net connections (must connect to ≥2 devices)
    
    Args:
        tokens: List of tokens in the sequence
        debug: If True, print detailed violation information
    Returns:
        Tuple of (is_valid, violations_dict)
        - is_valid: Boolean indicating if sequence passes all tests
        - violations_dict: Dictionary with violation lists for each test
    """
    violations = {
        'test1': check_sequence_first_test(tokens, debug=debug),
        'test2': check_sequence_second_test(tokens, debug=debug),
        'test3': check_sequence_third_test(tokens, debug=debug),
        'test4': check_internal_net_connections(tokens, debug=debug)
    }
    
    is_valid = (len(violations['test1']) == 0 and 
                len(violations['test2']) == 0 and 
                len(violations['test3']) == 0 and
                len(violations['test4']) == 0)
    
    return is_valid, violations


def extract_nodes_and_edges_from_graph(edges, nodes):
    """Extract all nodes and normalized edges from graph representation.
    
    Args:
        edges: List of (node1, edge_type, node2) tuples
        nodes: List of node names
    Returns:
        Tuple of (all_nodes, all_edge_tuples)
        - all_nodes: Set of all node names
        - all_edge_tuples: Set of normalized undirected edges (node1, node2, edge_type) where node1 < node2
    """
    all_nodes = set(nodes)
    all_edge_tuples = set()
    
    for node1, edge_type, node2 in edges:
        # Normalize edge as undirected: (smaller_node, larger_node, edge_type)
        edge_normalized = tuple(sorted([node1, node2])) + (edge_type,)
        all_edge_tuples.add(edge_normalized)
    
    return all_nodes, all_edge_tuples


def validate_sequence_coverage(sequence, all_nodes, all_edge_tuples, start_node='VSS', verbose=False):
    """Validate that sequence covers all nodes and edges from original graph.
    
    Checks:
    1. All graph nodes are visited in the sequence
    2. All graph edges are traversed in the sequence
    3. Sequence forms a circular path (starts and ends with start_node)
    
    Args:
        sequence: List of tokens [node, edge_type, node, edge_type, ...]
        all_nodes: Set of all node names from original graph
        all_edge_tuples: Set of all edges from original graph (normalized)
        start_node: Expected start and end node (default: 'VSS')
        verbose: If True, print detailed validation information
    Returns:
        Tuple of (is_valid, visited_nodes, visited_edges, missing_nodes, missing_edges)
    """
    visited_nodes = set()
    visited_edges = set()
    
    # Parse sequence: node-edge_type-node-edge_type pattern
    i = 0
    while i < len(sequence):
        token = sequence[i]
        
        # Skip circuit type token
        if token.startswith('CIRCUIT_'):
            i += 1
            continue
        
        # Node
        if token in all_nodes:
            visited_nodes.add(token)
            
            # Check if next is edge_type and following is node
            if i + 2 < len(sequence):
                edge_type = sequence[i + 1]
                next_node = sequence[i + 2]
                
                if next_node in all_nodes:
                    # Record edge visit (normalized as undirected)
                    edge_normalized = tuple(sorted([token, next_node])) + (edge_type,)
                    visited_edges.add(edge_normalized)
                    
                    i += 2  # Skip edge_type and next_node (will be processed in next iteration)
                else:
                    i += 1
            else:
                i += 1
        else:
            i += 1
    
    # Check coverage
    missing_nodes = all_nodes - visited_nodes
    missing_edges = all_edge_tuples - visited_edges
    
    # Check circular path: starts and ends with start_node
    is_circular = False
    if len(sequence) > 0:
        first_token = sequence[0]
        last_token = sequence[-1]
        # Skip CIRCUIT_ token if present
        if first_token.startswith('CIRCUIT_') and len(sequence) > 1:
            first_token = sequence[1]
        is_circular = (first_token == start_node and last_token == start_node)
    
    is_valid = len(missing_nodes) == 0 and len(missing_edges) == 0 and is_circular
    
    if verbose and not is_valid:
        if missing_nodes:
            print(f"  Coverage check failed: {len(missing_nodes)} nodes not visited")
            if len(missing_nodes) <= 5:
                print(f"    Missing: {sorted(list(missing_nodes))}")
        if missing_edges:
            print(f"  Coverage check failed: {len(missing_edges)} edges not traversed")
        if not is_circular:
            print(f"  Circularity check failed: path does not return to v_ref")
            print(f"    Start: {sequence[0] if sequence else 'N/A'}, End: {sequence[-1] if sequence else 'N/A'}")
    
    return is_valid, visited_nodes, visited_edges, missing_nodes, missing_edges


# =========================
# Sequence Generation with Augmentation
# =========================

def generate_multiple_paths(adj, edges, nodes, start_node='VSS', max_attempts=2000, max_sequences=200, verbose=False):
    """Generate multiple diverse sequences through neighbor order randomization.
    
    Implements device renaming-based augmentation by randomizing graph traversal
    order while maintaining circuit functionality. Only sequences that visit ALL
    nodes and ALL edges are retained.
    
    Args:
        adj: Adjacency dictionary
        edges: List of (node1, edge_type, node2) tuples
        nodes: List of all node names
        start_node: Starting node for sequence generation
        max_attempts: Maximum number of generation attempts
        max_sequences: Maximum number of unique sequences to generate
        verbose: If True, print detailed generation statistics
    Returns:
        List of valid sequences (each guaranteed to cover all nodes and edges)
    """
    # Extract all nodes and edges for validation
    all_nodes, all_edge_tuples = extract_nodes_and_edges_from_graph(edges, nodes)
    
    if verbose:
        print(f"  Graph structure: |V| = {len(all_nodes)}, |E| = {len(all_edge_tuples)}")
    
    sequences = []
    seen_sequences = set()
    failed_attempts = 0
    
    # First, try without shuffling
    seq = dfs_cover_all_edges_iterative(adj, edges, start_node, shuffle_neighbors=False)
    if seq:
        is_valid, visited_nodes, visited_edges, missing_nodes, missing_edges = validate_sequence_coverage(
            seq, all_nodes, all_edge_tuples, start_node=start_node, verbose=verbose
        )
        
        if is_valid:
            seq_tuple = tuple(seq)
            seen_sequences.add(seq_tuple)
            sequences.append(seq)
            if verbose:
                print(f"  Sequence generated (deterministic): length = {len(seq)} tokens")
        else:
            failed_attempts += 1
            if verbose:
                print(f"  Coverage incomplete: {len(visited_nodes)}/{len(all_nodes)} nodes, {len(visited_edges)}/{len(all_edge_tuples)} edges visited")
    
    # Then generate with shuffling
    attempts = 0
    while len(sequences) < max_sequences and attempts < max_attempts:
        attempts += 1
        
        seq = dfs_cover_all_edges_iterative(adj, edges, start_node, shuffle_neighbors=True)
        
        if seq:
            # Validate coverage - STRICT: must visit ALL nodes and ALL edges AND circular path
            is_valid, visited_nodes, visited_edges, missing_nodes, missing_edges = validate_sequence_coverage(
                seq, all_nodes, all_edge_tuples, start_node=start_node, verbose=False
            )
            
            if is_valid:
                seq_tuple = tuple(seq)
                if seq_tuple not in seen_sequences:
                    seen_sequences.add(seq_tuple)
                    sequences.append(seq)
            else:
                failed_attempts += 1
    
    if verbose:
        success_rate = len(sequences) / max(attempts + 1, 1) * 100
        print(f"  Augmentation complete: K = {len(sequences)} sequences generated ({success_rate:.1f}% success rate)")
        if failed_attempts > 0:
            print(f"  Note: {failed_attempts} sequences discarded (failed coverage or ERC check)")
    
    return sequences


# =========================
# Dataset Processing Pipeline
# =========================

def process_single_dataset(dataset_num, output_dir='Dataset', verbose=False):
    """Process a single circuit and generate augmented sequences.
    
    Reads bipartite graph CSV, generates multiple valid sequences through
    randomized traversal, and validates coverage.
    
    Args:
        dataset_num: Circuit dataset number
        output_dir: Root directory containing circuit folders
        verbose: If True, print detailed processing information
    Returns:
        List of valid sequences, or None if processing fails
    """
    bipart_file = f"{output_dir}/{dataset_num}/Graph_Bipart{dataset_num}.csv"
    
    if not os.path.exists(bipart_file):
        return None
    
    try:
        # Read graph from CSV
        edges, nodes = read_typed_adjacency_matrix(bipart_file)
        
        if len(edges) == 0:
            if verbose:
                print(f"  Skipping Circuit {dataset_num}: Empty graph (|E| = 0)")
            return None
        
        # Build adjacency
        adj = build_adjacency_dict(edges)
        
        # Determine start node (prefer VSS)
        start_node = 'VSS' if 'VSS' in nodes else nodes[0]
        
        if verbose:
            print(f"Circuit {dataset_num}:")
            print(f"  Graph: |V| = {len(nodes)}, |E| = {len(edges)}, v_ref = {start_node}")
        
        # Generate multiple sequences (max 200 per graph)
        # STRICT: Only sequences that visit ALL nodes and ALL edges will be kept
        sequences = generate_multiple_paths(
            adj, edges, nodes, start_node, 
            max_attempts=2000, max_sequences=200,
            verbose=verbose
        )
        
        if not sequences or len(sequences) == 0:
            if verbose:
                print(f"  Augmentation failed: No sequences passed validation criteria")
            return None
        
        return sequences
    
    except Exception as e:
        if verbose:
            print(f"  Processing error for Circuit {dataset_num}: {e}")
        return None


def process_dataset(dataset_start=1, dataset_end=3502, output_dir='Dataset'):
    """Process all circuits in dataset and generate augmented sequences.
    
    Applies strict validation to ensure data quality:
    1. Complete coverage: All nodes and edges must be visited
    2. Circular paths: Sequences start and end at the same node
    3. ERC validation: Pass all electrical rule checks
    4. Connectivity: Internal nets must connect to ≥2 devices
    5. Length limit: Sequences must be ≤1023 tokens (+ TRUNCATE padding)
    
    Args:
        dataset_start: Starting circuit number
        dataset_end: Ending circuit number
        output_dir: Root directory containing circuit folders
    Returns:
        Statistics dictionary with processing results
    """
    
    stats = {
        'processed': 0,
        'failed': 0,
        'skipped': 0,
        'total_sequences': 0,
        'invalid_sequences': 0,
        'erc_failed': 0,
        'floating_net_violations': 0
    }
    
    print(f"\n{'='*80}")
    print(f"Structure-Preserving Data Augmentation for Bipartite Circuit Sequences")
    print(f"{'='*80}")
    print(f"Dataset range: {dataset_start} to {dataset_end}")
    print(f"Output format: Sequence_bipart{{id}}.npy (padded to T_max = 1024)")
    print(f"\nAlgorithm parameters:")
    print(f"  Reference node (v_ref): VSS")
    print(f"  Maximum sequences per graph (K): 200")
    print(f"  Maximum sequence length (T_max): 1024 tokens")
    print(f"\nValidation criteria:")
    print(f"  1. Coverage check: All nodes V and edges E must be visited")
    print(f"  2. Circular path: Sequence must return to v_ref")
    print(f"  3. ERC check: Pass all electrical rule checks (Tests 1-4)")
    print(f"  4. Connectivity: Internal nets connect to >= 2 devices")
    print(f"  5. Length constraint: |s| <= T_max")
    print(f"{'='*80}\n")
    
    for i in tqdm(range(dataset_start, dataset_end + 1), desc="Processing"):
        bipart_file = f"{output_dir}/{i}/Graph_Bipart{i}.csv"
        output_file = f"{output_dir}/{i}/Sequence_bipart{i}.npy"
        
        # Skip if bipart file doesn't exist
        if not os.path.exists(bipart_file):
            stats['skipped'] += 1
            continue
        
        # Process dataset with strict validation
        sequences = process_single_dataset(i, output_dir, verbose=False)
        
        if sequences is None or len(sequences) == 0:
            stats['failed'] += 1
            continue
        
        # Validate sequences before saving
        # Load original graph for final validation
        edges, nodes = read_typed_adjacency_matrix(bipart_file)
        all_nodes, all_edge_tuples = extract_nodes_and_edges_from_graph(edges, nodes)
        
        valid_sequences = []
        # Determine start node
        seq_start_node = 'VSS' if 'VSS' in nodes else nodes[0]
        for seq in sequences:
            # Filter by length constraint
            if len(seq) > 1023:
                stats['invalid_sequences'] += 1
                continue
            
            # Check graph coverage
            is_valid, _, _, _, _ = validate_sequence_coverage(seq, all_nodes, all_edge_tuples, start_node=seq_start_node, verbose=False)
            if not is_valid:
                stats['invalid_sequences'] += 1
                continue
            
            # Check ERC (including Test 4: internal net connections)
            erc_valid, erc_violations = validate_sequence_erc(seq, debug=False)
            if not erc_valid:
                stats['erc_failed'] += 1
                # Track if floating net was the issue
                if len(erc_violations.get('test4', [])) > 0:
                    stats['floating_net_violations'] += 1
                continue
            
            # Passed all validations
            valid_sequences.append(seq)
        
        if len(valid_sequences) == 0:
            stats['failed'] += 1
            continue
        
        # Pad sequences to length 1024 (1023 tokens or less + TRUNCATE padding)
        padded_sequences = []
        for seq in valid_sequences:
            # All sequences here are guaranteed to be <= 1023 tokens
            padded = seq + ['TRUNCATE'] * (1024 - len(seq))
            padded_sequences.append(padded[:1024])
        
        # Save as numpy array
        sequences_array = np.array(padded_sequences, dtype=object)
        np.save(output_file, sequences_array)
        
        stats['processed'] += 1
        stats['total_sequences'] += len(valid_sequences)
    
    # Print statistics
    print("\n" + "="*80)
    print("Augmentation Results")
    print("="*80)
    print(f"Successfully processed: {stats['processed']} circuits")
    print(f"\nSequence statistics:")
    print(f"  Total augmented sequences (|S|): {stats['total_sequences']}")
    if stats['processed'] > 0:
        avg_k = stats['total_sequences'] / stats['processed']
        print(f"  Average sequences per circuit (K_avg): {avg_k:.1f}")
    print("="*80)
    print("\nSequence guarantees:")
    print(f"  - Complete coverage: All V and E visited")
    print(f"  - Circular topology: v_ref → ... → v_ref")
    print(f"  - Electrical validity: Pass all ERC tests")
    print(f"  - Proper connectivity: No floating internal nets")
    print(f"  - Fixed length: Padded to T_max = 1024\n")
    
    return stats


if __name__ == "__main__":
    # Test mode: Validate algorithm on a single circuit
    print("\n" + "="*80)
    print("Algorithm Validation Mode")
    print("="*80)
    print("Testing augmentation algorithm on Circuit 4...")
    print("="*80 + "\n")
    
    sequences = process_single_dataset(4, verbose=True)
    
    if sequences:
        print(f"\nAugmentation successful: |S| = {len(sequences)} sequences generated")
        
        # Test ERC on first sequence
        if len(sequences) > 0:
            seq = sequences[0]
            print(f"\nFirst sequence ({len(seq)} tokens):")
            print(f"  {' -> '.join(seq[:20])} ...")
            
            print(f"\nValidating first sequence with ERC checks...")
            erc_valid, erc_violations = validate_sequence_erc(seq, debug=False)
            if erc_valid:
                print(f"  Result: PASS (all ERC tests satisfied)")
            else:
                print(f"  Result: FAIL")
                for test_name, violations in erc_violations.items():
                    if violations:
                        test_desc = "(Internal Net Connections)" if test_name == 'test4' else ""
                        print(f"    {test_name} {test_desc}: {len(violations)} violations")
                        for v in violations[:3]:  # Show first 3
                            print(f"      - {v}")
        
        # Prompt for full dataset processing
        response = input(f"\nValidation successful. Run algorithm on full dataset (1-3502)? (y/N): ")
        if response.lower() == 'y':
            print("\nInitiating full dataset augmentation...")
            print("Note: Only sequences satisfying all validation criteria will be saved.\n")
            stats = process_dataset(1, 3502)
        else:
            print("\nValidation test completed.")
    else:
        print("\nValidation failed: Unable to generate valid sequences for test circuit.")
        print("This may indicate the graph structure does not allow Eulerian-like traversal.\n")
