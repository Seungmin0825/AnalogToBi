#!/usr/bin/env python3
"""
Validity of a generation run, per circuit type

This module performs rule-based validation across all Inference_CIRCUIT_* 
directories and reports the validity of each circuit type.

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
    python METRIC_Validity.py runs/AnalogToBi
"""

import argparse
import os
import numpy as np
from collections import defaultdict

# =========================
# Vocabulary
# =========================
# CORE_Vocab.py holds the single definition of the token list.
from CORE_Vocab import circuit_type_tokens

CIRCUIT_TYPE_TOKENS = circuit_type_tokens

# =========================
# Electric rule checks
# =========================
# The four tests live in CORE_ERC.py, which is the single definition of what
# "valid" means. Importing them keeps this script and the generator in step: a
# change to a rule reaches both at once.
from CORE_ERC import (is_device_node, is_net_node, is_internal_net, is_edge,
                      get_device_prefix, get_pins_from_edge,
                      check_sequence_first_test, check_sequence_second_test,
                      check_sequence_third_test, check_internal_net_connections,
                      passes_erc)



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
            all_tokens = [str(token) for token in data.item() if str(token) not in ('TRUNCATE', 'End')]
        elif data.ndim == 1:
            all_tokens = [str(token) for token in data if str(token) not in ('TRUNCATE', 'End')]
        else:
            all_tokens = [str(token) for token in data[0] if str(token) not in ('TRUNCATE', 'End')]
    else:
        with open(file_path, 'r') as f:
            content = f.read().strip()
        all_tokens = [token.strip() for token in content.split('->') if token.strip() and token.strip() not in ('TRUNCATE', 'End')]
    
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


def check_all_inference_folders(run_dir='.'):
    """Score all Inference_CIRCUIT_* folders of a run and report validity.

    Args:
        run_dir: generation run directory holding the Inference_CIRCUIT_* folders
    """
    print("=" * 70)
    print("VALIDITY")
    print("=" * 70)
    
    # Find all Inference_CIRCUIT_* folders
    inference_folders = [f for f in os.listdir(run_dir) if f.startswith('Inference_CIRCUIT_')]
    
    if not inference_folders:
        print(f"No Inference_CIRCUIT_* folders found in {run_dir}")
        return
    
    print(f"Found {len(inference_folders)} inference folders\n")
    
    results = []
    
    for folder in sorted(inference_folders):
        circuit_type = folder.replace('Inference_CIRCUIT_', '').replace('_masked', '')
        
        folder_path = os.path.join(run_dir, folder)

        # Get all inference files
        files = [f for f in os.listdir(folder_path) if f.startswith('run') and (f.endswith('.txt') or f.endswith('.npy'))]
        
        if not files:
            continue
        
        clean_count = 0
        total_count = len(files)
        
        for filename in files:
            file_path = os.path.join(folder_path, filename)
            
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
        
        print(f"{circuit_type:30s}: Valid {clean_count:4d}/{total_count:4d}   Validity {clean_percentage:5.1f}%")
    
    # Summary
    total_files = sum(r['total'] for r in results)
    total_clean = sum(r['clean'] for r in results)
    overall_percentage = (total_clean / total_files * 100) if total_files > 0 else 0
    
    print("\n" + "=" * 70)
    print(f"{'OVERALL':30s}: Valid {total_clean:4d}/{total_files:4d}   Validity {overall_percentage:5.1f}%")
    print("=" * 70)


def main():
    """Command-line entry point."""
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('run_dir', nargs='?', default='.',
                        help='generation run directory holding the Inference_CIRCUIT_* folders '
                             '(default: the current directory)')
    args = parser.parse_args()
    check_all_inference_folders(args.run_dir)


if __name__ == "__main__":
    main()
