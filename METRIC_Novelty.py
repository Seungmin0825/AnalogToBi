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
- Generalization: Device numbers removed (NM1/NM2 -> NM, NET1/NET2 -> NET)
- Bipartite structure with device-edge-net pattern preserved

Batch Processing:
- Processes multiple inference result directories
- Per-circuit-type novelty statistics
- Overall novelty rate across all circuit types
- Output: JSON files with novelty metrics and isomorphic pairs
"""

import argparse
import json
import os
import re
from pathlib import Path

from tqdm import tqdm

# Graph construction and isomorphism are defined once in CORE_Graph.py, so the
# generated side and the dataset side are always built and compared the same way.
from CORE_Graph import (create_networkx_graph, graphs_are_isomorphic,
                        load_dataset_graphs)



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
    """Command-line entry point."""
    parser = argparse.ArgumentParser(
        description='Batch novelty analysis of generated bipartite circuit graphs'
    )
    
    parser.add_argument('run_dir', nargs='?', default='.',
                        help='generation run directory holding the Inference_CIRCUIT_* folders '
                             '(default: the current directory)')
    parser.add_argument('--reference', type=str, default='Dataset/',
                       help='Reference dataset directory (default: Dataset/)')
    parser.add_argument('--output-dir', type=str, default=None,
                       help='Output directory (default: <run_dir>/novelty_results)')
    parser.add_argument('--pattern', type=str, default='Inference_CIRCUIT_*/',
                       help='Pattern to match inference directories')
    parser.add_argument('--max-ref', type=int, default=None,
                       help='Maximum number of reference graphs to load')
    
    args = parser.parse_args()
    if args.output_dir is None:
        args.output_dir = os.path.join(args.run_dir, 'novelty_results')
    
    # Find inference results
    inference_dirs = find_inference_results(args.run_dir, pattern=args.pattern)
    
    if not inference_dirs:
        print(f"No inference directories matching {args.pattern} in {args.run_dir}")
        return
    
    os.makedirs(args.output_dir, exist_ok=True)
    print(f"Found {len(inference_dirs)} inference result directories")
    
    # Load reference graphs
    print(f"\n{'='*60}")
    print("Loading reference dataset...")
    print(f"{'='*60}")
    reference_graphs = load_dataset_graphs(args.reference, max_graphs=args.max_ref,
                                          with_ids=True)
    
    # Analyze each inference result
    all_results = {}
    
    for dir_path, query_path in inference_dirs:
        circuit_type = Path(dir_path).name.replace('Inference_CIRCUIT_', '').replace('_masked', '')
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
    print(f"{'Circuit Type':<40} {'Novel':>8} {'Rate':>10}")
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
        
        print(f"{circuit_type:<40} {results['novel_circuits']:>8} {results['novelty_rate']*100:>9.2f}%")
    
    print('-'*60)
    
    if total_queries > 0:
        overall_rate = total_novel / total_queries
        print(f"{'OVERALL':<40} {total_novel:>8} {overall_rate*100:>9.2f}%")
        
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
