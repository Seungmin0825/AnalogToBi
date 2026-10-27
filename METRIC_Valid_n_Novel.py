"""
METRIC_Valid_n_Novel.py

This script evaluates the generated sequences of a run directory, given as an
argument (default: the current directory), on two metrics:
1. Validity: ERC (Electrical Rule Check) pass rate per circuit type
2. Novelty: whether a circuit is isomorphic to no dataset circuit, reported
   both over every sequence and over the ERC-passing ones

Output:
- ERC pass rate per circuit type
- Novel rate (ERC pass + not in dataset) per circuit type

With --write-ids the run ids behind those counts are also written, one
valid_novel_ids_<Type>.json per circuit type, next to the Inference folders.
SPICE_translation/GRAPH2CADENCE_subckt_general.py reads them to netlist the
valid and topology-novel walks of a run.
"""

import argparse
import glob
import json
import os
import re

import pandas as pd
from tqdm import tqdm

# The four ERC tests are defined once in CORE_ERC.py, and graph construction and
# isomorphism once in CORE_Graph.py, so this script, the generator and the other
# metrics cannot drift apart on what "valid" or "the same topology" means.
from CORE_ERC import passes_erc
from CORE_Graph import (create_networkx_graph, graphs_are_isomorphic,
                        load_dataset_graphs)



# ============================================================================
# MAIN ANALYSIS
# ============================================================================
def analyze_inference_folder(inference_dir, dataset_graphs, collect_ids=False):
    """Analyze one inference folder for validity (ERC) and novelty.

    With collect_ids the run numbers behind the two ERC counters are kept as
    well, so --write-ids can name the walks rather than only count them.
    """
    results = {
        'total': 0,
        'erc_pass': 0,
        'erc_pass_novel': 0,
        'all_novel': 0,
        'all_graphs': [],
        'erc_pass_ids': [],
        'valid_novel_ids': []
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
        run_match = re.search(r'run(\d+)', os.path.basename(txt_file))
        run_id = int(run_match.group(1)) if run_match else None
        try:
            with open(txt_file, 'r') as f:
                content = f.read().strip()
                if '->' not in content:
                    continue
                tokens = [t.strip() for t in content.split('->') if t.strip() and t.strip() not in ('TRUNCATE', 'End')]
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
            if collect_ids and run_id is not None:
                results['erc_pass_ids'].append(run_id)
            
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
                    if collect_ids and run_id is not None:
                        results['valid_novel_ids'].append(run_id)
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


def write_valid_novel_ids(run_dir, results_list):
    """Write valid_novel_ids_<Type>.json next to each Inference_CIRCUIT_<Type>_masked/."""
    for results in results_list:
        circuit = results['circuit_type']
        out = os.path.join(run_dir, f'valid_novel_ids_{circuit}.json')
        with open(out, 'w') as fh:
            json.dump({'circuit_type': circuit,
                       'erc_pass_ids': sorted(results['erc_pass_ids']),
                       'valid_novel_ids': sorted(results['valid_novel_ids']),
                       'count': len(results['valid_novel_ids'])}, fh, indent=1)
        print(f"  valid_novel_ids_{circuit}.json: "
              f"{len(results['valid_novel_ids'])} valid & novel of "
              f"{len(results['erc_pass_ids'])} valid")


def main():
    """Command-line entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_dir', nargs='?', default='.',
                        help='generation run directory holding the Inference_CIRCUIT_* folders '
                             '(default: the current directory)')
    parser.add_argument('--write-ids', action='store_true',
                        help='also write valid_novel_ids_<Type>.json into the run '
                             'directory: the ids of the valid and of the valid & novel walks')
    args = parser.parse_args()

    print("="*80)
    print("VALIDITY AND NOVELTY")
    print("="*80)
    print()
    
    # Load dataset graphs once
    dataset_graphs = load_dataset_graphs()
    
    # Find all Inference folders
    inference_folders = sorted(glob.glob(os.path.join(args.run_dir, "Inference_CIRCUIT_*")))
    
    if not inference_folders:
        print(f"No Inference_CIRCUIT_* folders found in {args.run_dir}")
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
        
        results = analyze_inference_folder(inference_dir, dataset_graphs,
                                          collect_ids=args.write_ids)
        results['circuit_type'] = circuit_type
        results_list.append(results)
        
        n = results['total']
        print(f"  Samples:      {n}")
        print(f"  Valid:        {results['erc_pass']}   Validity {results['erc_pass']/n*100:.1f}%")
        print(f"  Novel:        {results['all_novel']}   Novelty {results['all_novel']/n*100:.1f}%")
        print(f"  Valid&Novel:  {results['erc_pass_novel']}   {results['erc_pass_novel']/n*100:.1f}%")
        print()

    if args.write_ids:
        print("Writing the valid & novel id lists")
        write_valid_novel_ids(args.run_dir, results_list)
        print()

    # Define circuit type order
    circuit_order = [
        'Opamp', 'Mirror', 'Comparator', 'Mixer', 'LDO', 'Oscillator',
        'Filter', 'Bandgap_Ref', 'Power_Amp', 'Voltage_Regulator',
        'Power_converter', 'PLL', 'Switched_Cap', 'ADC_DAC', 'General'
    ]
    
    def get_sort_key(result):
        """Sort key that lists circuit types in the fixed reporting order."""
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
            'Samples': r['total'],
            'Valid': r['erc_pass'],
            'Validity': f"{r['erc_pass']/r['total']*100:.1f}%",
            'Novel': r['all_novel'],
            'Novelty': f"{r['all_novel']/r['total']*100:.1f}%",
            'Valid&Novel': r['erc_pass_novel'],
            'Valid&Novel %': f"{r['erc_pass_novel']/r['total']*100:.1f}%"
        }
        for r in results_sorted
    ])
    
    print(df.to_string(index=False))
    print()
    
    # Save to CSV
    output_file = os.path.join(args.run_dir, "METRIC_Valid_n_Novel_RESULTS.csv")
    df.to_csv(output_file, index=False)
    print(f"Results saved to {output_file}")
    
    # Overall statistics
    total = sum(r['total'] for r in results_list)
    all_novel = sum(r['all_novel'] for r in results_list)
    erc_pass = sum(r['erc_pass'] for r in results_list)
    novel = sum(r['erc_pass_novel'] for r in results_list)
    
    print()
    print("="*80)
    print("OVERALL")
    print("="*80)
    print(f"Samples:      {total}")
    print(f"Valid:        {erc_pass}   Validity {erc_pass/total*100:.1f}%")
    print(f"Novel:        {all_novel}   Novelty {all_novel/total*100:.1f}%")
    print(f"Valid&Novel:  {novel}   {novel/total*100:.1f}%")
    print("="*80)


if __name__ == "__main__":
    main()
