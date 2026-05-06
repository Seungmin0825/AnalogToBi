#!/usr/bin/env python3
"""
Exact Sequence Matching Novelty Metric for AnalogGenie with FT

Measures novelty by checking if generated sequences exactly match
any sequence in the training dataset. Any sequence NOT found in
Training.npy is considered novel.

Analyzes single inference folder: Inference/

Metric: Binary classification (Novel vs Memorized)
- Novel: Sequence NOT in Training.npy
- Memorized: Exact match found in Training.npy
"""

import numpy as np
import os
from pathlib import Path
from collections import defaultdict
from tqdm import tqdm
import json
import time

# Configuration
BASE_DIR = Path(__file__).parent
_training_renamed = BASE_DIR / 'Training_renamed.npy'
_training_default = BASE_DIR / 'Training.npy'
TRAINING_NPY = _training_renamed if _training_renamed.exists() else _training_default


def parse_txt_file(file_path):
    """
    Parse .txt file and extract tokens (excluding TRUNCATE).
    
    Args:
        file_path: Path to .txt file
    
    Returns:
        Tuple of tokens (as tuple for hashing)
    """
    with open(file_path, 'r') as f:
        content = f.read().strip()
    
    # Split by '->' and remove empty/whitespace
    tokens = [t.strip() for t in content.split('->') if t.strip()]
    
    # Remove TRUNCATE tokens
    tokens = [t for t in tokens if t != 'TRUNCATE']
    
    return tuple(tokens)


def normalize_sequence(seq):
    """
    Normalize a sequence from Training.npy to tuple format.
    
    Args:
        seq: Sequence array from .npy file
        
    Returns:
        Tuple of tokens (excluding TRUNCATE)
    """
    tokens = []
    for token in seq:
        token_str = str(token).strip()
        if token_str == 'TRUNCATE' or token_str == '':
            break
        tokens.append(token_str)
    
    return tuple(tokens)


def build_training_set_index(training_npy_path):
    """
    Load Training.npy and build a set of all sequences for O(1) lookup.
    
    Args:
        training_npy_path: Path to Training.npy
        
    Returns:
        Set of sequence tuples
    """
    print(f"\n{'='*70}")
    print("Loading Training Data")
    print(f"{'='*70}")
    print(f"File: {training_npy_path}")
    
    training_data = np.load(training_npy_path, allow_pickle=True)
    print(f"Shape: {training_data.shape}")
    print(f"Total sequences: {len(training_data)}")
    
    print("\nBuilding sequence index...")
    training_sequences = set()
    
    for seq in tqdm(training_data, desc="Indexing sequences"):
        normalized = normalize_sequence(seq)
        if normalized:  # Only add non-empty sequences
            training_sequences.add(normalized)
    
    print(f"Unique sequences in training set: {len(training_sequences)}")
    
    return training_sequences


def analyze_inference_folder(folder_path, training_sequences):
    """
    Analyze inference folder and check novelty.
    
    Args:
        folder_path: Path to inference folder
        training_sequences: Set of training sequence tuples
    
    Returns:
        Dictionary with analysis results
    """
    folder_name = folder_path.name
    print(f"\n{'='*70}")
    print(f"Analyzing: {folder_name}")
    print(f"{'='*70}")
    
    # Collect all .txt files
    txt_files = sorted(folder_path.glob('run*.txt'))
    print(f"Found {len(txt_files)} files")
    
    if not txt_files:
        return {
            'folder': folder_name,
            'total': 0,
            'novel': 0,
            'memorized': 0,
            'novelty_rate': 0.0,
            'error': 'No .txt files found'
        }
    
    novel_count = 0
    memorized_count = 0
    error_count = 0
    memorized_examples = []
    
    for txt_file in tqdm(txt_files, desc=f"Processing {folder_name}"):
        try:
            infer_seq = parse_txt_file(txt_file)
            
            if not infer_seq:
                error_count += 1
                continue
            
            # Check if sequence exists in training set
            if infer_seq in training_sequences:
                memorized_count += 1
                if len(memorized_examples) < 10:  # Save first 10 examples
                    memorized_examples.append({
                        'file': txt_file.name,
                        'sequence_length': len(infer_seq)
                    })
            else:
                novel_count += 1
        
        except Exception as e:
            error_count += 1
            print(f"  Error processing {txt_file.name}: {e}")
    
    total = novel_count + memorized_count
    novelty_rate = (novel_count / total * 100) if total > 0 else 0
    
    results = {
        'folder': folder_name,
        'total': total,
        'novel': novel_count,
        'memorized': memorized_count,
        'errors': error_count,
        'novelty_rate': novelty_rate,
        'memorized_examples': memorized_examples
    }
    
    print(f"\nResults:")
    print(f"  Total analyzed: {total}")
    print(f"  Novel: {novel_count} ({novel_count/total*100:.1f}%)")
    print(f"  Memorized: {memorized_count} ({memorized_count/total*100:.1f}%)")
    if error_count > 0:
        print(f"  Errors: {error_count}")
    print(f"  Novelty Rate: {novelty_rate:.2f}%")
    
    return results


def find_inference_folders(base_dir):
    """
    Auto-detect inference folder structure.

    Two patterns supported:
    1. Single 'Inference/' folder with run*.txt files (AnalogGenie style)
    2. Multiple 'Inference_*/' folders each with run*.txt files (AnalogToBi style)

    Returns:
        List of Path objects to inference folders that contain run*.txt files
    """
    # Pattern 1: single Inference/ with files
    single = base_dir / 'Inference'
    if single.exists() and any(single.glob('run*.txt')):
        return [single]

    # Pattern 2: multiple Inference_*/ folders
    multi = sorted(base_dir.glob('Inference_*/'))
    multi = [p for p in multi if p.is_dir() and any(p.glob('run*.txt'))]
    if multi:
        return multi

    return []


def main():
    start_time = time.time()
    
    print("="*70)
    print("EXACT SEQUENCE MATCHING NOVELTY METRIC")
    print("="*70)
    print("\nMethod: Binary classification")
    print(f"  Training file: {TRAINING_NPY.name}")
    print("  Novel:      Sequence NOT in training set")
    print("  Memorized:  Exact match found in training set")
    
    # Load training data
    training_sequences = build_training_set_index(TRAINING_NPY)
    
    # Auto-detect inference folders
    inference_folders = find_inference_folders(BASE_DIR)
    if not inference_folders:
        print(f"\nError: No inference folders with run*.txt files found in {BASE_DIR}")
        return
    
    print(f"\nDetected {len(inference_folders)} inference folder(s)")
    
    # Analyze each folder
    all_results = []
    for folder in inference_folders:
        results = analyze_inference_folder(folder, training_sequences)
        all_results.append(results)
    
    # Aggregate totals
    total_all = sum(r['total'] for r in all_results)
    novel_all = sum(r['novel'] for r in all_results)
    memorized_all = sum(r['memorized'] for r in all_results)
    novelty_rate_all = (novel_all / total_all * 100) if total_all > 0 else 0
    
    # Summary
    print(f"\n{'='*70}")
    print("SUMMARY - EXACT SEQUENCE MATCHING NOVELTY")
    print(f"{'='*70}")
    if len(all_results) > 1:
        for r in all_results:
            print(f"  [{r['folder']}] total={r['total']} novel={r['novel']} ({r['novelty_rate']:.1f}%)")
        print(f"{'─'*70}")
    print(f"Total generated: {total_all}")
    print(f"Novel:           {novel_all} ({novelty_rate_all:.2f}%)")
    print(f"Memorized:       {memorized_all} ({memorized_all/total_all*100:.2f}%)" if total_all > 0 else "Memorized:       0")
    errors_all = sum(r.get('errors', 0) for r in all_results)
    if errors_all > 0:
        print(f"Errors:          {errors_all}")
    
    # Save results as JSON
    output_file = BASE_DIR / 'NOVELTY_ExactMatching_Results.json'
    
    summary = {
        'method': 'exact_sequence_matching',
        'description': 'Binary novelty: sequence not in training set = novel',
        'training_data': {
            'file': str(TRAINING_NPY.name),
            'unique_sequences': len(training_sequences)
        },
        'inference_folders': [str(f.name) for f in inference_folders],
        'per_folder_results': all_results,
        'aggregate': {
            'total': total_all,
            'novel': novel_all,
            'memorized': memorized_all,
            'novelty_rate': novelty_rate_all
        },
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'computation_time_seconds': time.time() - start_time
    }
    
    with open(output_file, 'w') as f:
        json.dump(summary, f, indent=2)
    
    print(f"\n{'='*70}")
    print("RESULTS SAVED")
    print(f"{'='*70}")
    print(f"  Output file: {output_file}")
    print(f"  Computation time: {time.time() - start_time:.1f}s")
    
    print(f"\nExact Sequence Matching Novelty analysis complete")
    print(f"Method: Binary classification (novel vs memorized)")
    print(f"Training set: {len(training_sequences):,} unique sequences")
    print(f"Novelty rate: {novelty_rate_all:.2f}%")


if __name__ == '__main__':
    main()
