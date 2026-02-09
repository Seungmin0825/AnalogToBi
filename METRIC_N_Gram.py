#!/usr/bin/env python3
"""
N-gram Matching Analysis for GPT Model Memorization

This module measures the memorization of training data by a GPT model using 
10-gram matching. It samples generated circuits uniformly across circuit types 
for fair comparison. A circuit is considered memorized if both the first and 
last 10-grams match those in the training set.

Usage:
    python GPT_N_gram_matching.py
    
The script automatically detects Inference_CIRCUIT* directories for balanced 
sampling, or falls back to the Inference folder if circuit-type directories 
are not available.
"""

import numpy as np
import os
from pathlib import Path
from tqdm import tqdm
import json
from collections import defaultdict
import random
import glob

class MemorizationAnalyzer:
    """Analyzer for measuring GPT model memorization using n-gram matching.
    
    Attributes:
        base_dir: Base directory containing Inference_CIRCUIT folders
        training_npy_path: Path to Training.npy file
        samples_per_type: Number of files to sample per circuit type (default: 67)
        training_data: Loaded training sequences
        training_ngrams: Index of n-grams from training data
        sampled_files: List of sampled file paths for analysis
    """
    
    def __init__(self, base_dir, training_npy_path, samples_per_type=67):
        """Initialize the MemorizationAnalyzer.
        
        Args:
            base_dir: Base directory containing Inference_CIRCUIT folders
            training_npy_path: Path to Training.npy file
            samples_per_type: Number of files to sample per circuit type (default: 1000/15 ≈ 67)
        """
        self.base_dir = Path(base_dir)
        self.training_npy_path = Path(training_npy_path)
        self.samples_per_type = samples_per_type
        self.training_data = None
        self.training_ngrams = None
        self.sampled_files = []
        
    def load_training_data(self):
        """Load training sequences from .npy file."""
        print(f"Loading training data from {self.training_npy_path}...")
        self.training_data = np.load(self.training_npy_path, allow_pickle=True)
        print(f"Loaded {len(self.training_data)} training sequences")
        
    def parse_inference_file(self, file_path):
        """Parse inference result txt file and extract token sequence.
        
        Args:
            file_path: Path to the inference txt file
            
        Returns:
            List of tokens (up to TRUNCATE marker)
        """
        with open(file_path, 'r') as f:
            content = f.read().strip()
        
        # Split by -> delimiter
        tokens = content.split('->')
        
        # Extract tokens up to TRUNCATE marker
        valid_tokens = []
        for token in tokens:
            if token == 'TRUNCATE':
                break
            valid_tokens.append(token)
        
        return valid_tokens
    
    def extract_ngrams(self, tokens, n=10):
        """Extract first and last n-grams from token sequence.
        
        Args:
            tokens: List of tokens
            n: Size of n-gram (default: 10)
            
        Returns:
            Tuple of (first_ngram, last_ngram) where each is a tuple of n tokens,
            or (None, None) if sequence length is insufficient
        """
        first_ngram = None
        last_ngram = None
        
        if len(tokens) >= n:
            first_ngram = tuple(tokens[:n])
            last_ngram = tuple(tokens[-n:])
        
        return first_ngram, last_ngram
    
    def build_training_ngram_index(self, n=10):
        """Build n-gram index from training data for efficient matching.
        
        For memory efficiency, only the first and last n-grams of each 
        training sequence are indexed.
        
        Args:
            n: Size of n-gram (default: 10)
        """
        print(f"Building {n}-gram index from training data...")
        
        # Dictionary: ngram -> [sequence_idx, ...]
        self.training_ngrams = {
            'first': defaultdict(list),
            'last': defaultdict(list)
        }
        
        for idx, sequence in enumerate(tqdm(self.training_data, desc="Indexing training data")):
            # Sequence shape: (1025,), last element may be a label
            # Extract tokens up to TRUNCATE or special tokens
            tokens = []
            for token in sequence:
                if token == 'TRUNCATE' or token is None or token == '':
                    break
                tokens.append(token)
            
            if len(tokens) >= n:
                # First n-gram
                first_ngram = tuple(tokens[:n])
                self.training_ngrams['first'][first_ngram].append(idx)
                
                # Last n-gram
                last_ngram = tuple(tokens[-n:])
                self.training_ngrams['last'][last_ngram].append(idx)
        
        print(f"Indexed {len(self.training_ngrams['first'])} unique first {n}-grams")
        print(f"Indexed {len(self.training_ngrams['last'])} unique last {n}-grams")
    
    def collect_inference_files_balanced(self):
        """Collect inference files with balanced sampling across circuit types.
        
        If Inference_CIRCUIT* directories exist, samples uniformly from each.
        Otherwise, uses all files from the Inference directory.
        
        Returns:
            List of sampled file paths
        """
        # Find all directories starting with Inference_CIRCUIT
        circuit_dirs = sorted(self.base_dir.glob("Inference_CIRCUIT*"))
        
        if not circuit_dirs:
            # Fallback to Inference folder if no circuit-type directories
            print(f"\nNo Inference_CIRCUIT directories found.")
            print(f"Using Inference folder instead...")
            
            inference_dir = self.base_dir / "Inference"
            if not inference_dir.exists():
                print(f"Error: {inference_dir} does not exist")
                return []
            
            # Collect all txt files from Inference folder
            txt_files = sorted(inference_dir.glob("run*.txt"))
            
            if not txt_files:
                print(f"Error: No txt files found in {inference_dir}")
                return []
            
            print(f"Found {len(txt_files)} files in Inference folder")
            
            self.sampled_files = txt_files
            self.sampling_info = [{
                'circuit_type': 'Inference (all)',
                'available': len(txt_files),
                'sampled': len(txt_files)
            }]
            
            return txt_files
        
        # Balanced sampling from circuit-type directories
        print(f"\nFound {len(circuit_dirs)} circuit type directories:")
        for d in circuit_dirs:
            print(f"  - {d.name}")
        
        print(f"\nSampling {self.samples_per_type} files from each directory...")
        
        sampled_files = []
        sampling_info = []
        
        for circuit_dir in circuit_dirs:
            # Collect run*.txt files from this directory
            txt_files = sorted(circuit_dir.glob("run*.txt"))
            
            if not txt_files:
                print(f"  Warning: No txt files found in {circuit_dir.name}")
                sampling_info.append({
                    'circuit_type': circuit_dir.name,
                    'available': 0,
                    'sampled': 0
                })
                continue
            
            # Determine sample size (use all if insufficient files)
            num_to_sample = min(self.samples_per_type, len(txt_files))
            
            # Random sampling
            sampled = random.sample(txt_files, num_to_sample)
            sampled_files.extend(sampled)
            
            sampling_info.append({
                'circuit_type': circuit_dir.name,
                'available': len(txt_files),
                'sampled': num_to_sample
            })
            
            print(f"  {circuit_dir.name}: sampled {num_to_sample} / {len(txt_files)} files")
        
        print(f"\nTotal sampled files: {len(sampled_files)}")
        
        self.sampled_files = sampled_files
        self.sampling_info = sampling_info
        
        return sampled_files
    
    def analyze_inference_results(self, n=10):
        """Analyze sampled inference files for n-gram matches with training data.
        
        Args:
            n: Size of n-gram (default: 10)
            
        Returns:
            Dictionary containing analysis results with match statistics
        """
        # Use sampled files
        txt_files = self.sampled_files
        
        if not txt_files:
            print("Error: No files to analyze. Run collect_inference_files_balanced() first.")
            return None
        
        print(f"Analyzing {len(txt_files)} inference files...")
        
        results = {
            'total_files': len(txt_files),
            'matches': {
                'first_only': 0,
                'last_only': 0,
                'both': 0,
                'none': 0
            },
            'detailed_matches': []
        }
        
        for file_path in tqdm(txt_files, desc="Analyzing inference files"):
            # Parse file
            tokens = self.parse_inference_file(file_path)
            
            # Extract n-grams
            first_ngram, last_ngram = self.extract_ngrams(tokens, n)
            
            if first_ngram is None or last_ngram is None:
                results['matches']['none'] += 1
                results['detailed_matches'].append({
                    'file': file_path.name,
                    'match_type': 'insufficient_length',
                    'length': len(tokens)
                })
                continue
            
            # Check for matches
            first_matches = self.training_ngrams['first'].get(first_ngram, [])
            last_matches = self.training_ngrams['last'].get(last_ngram, [])
            
            # Intersection: sequences matching both first and last n-grams
            both_matches = set(first_matches) & set(last_matches)
            
            match_info = {
                'file': file_path.name,
                'length': len(tokens),
                'first_ngram': list(first_ngram),
                'last_ngram': list(last_ngram),
                'first_match_count': len(first_matches),
                'last_match_count': len(last_matches),
                'both_match_count': len(both_matches),
                'match_type': None,
                'training_indices': []
            }
            
            if both_matches:
                results['matches']['both'] += 1
                match_info['match_type'] = 'both'
                match_info['training_indices'] = list(both_matches)
            elif first_matches:
                results['matches']['first_only'] += 1
                match_info['match_type'] = 'first_only'
            elif last_matches:
                results['matches']['last_only'] += 1
                match_info['match_type'] = 'last_only'
            else:
                results['matches']['none'] += 1
                match_info['match_type'] = 'none'
            
            results['detailed_matches'].append(match_info)
        
        return results
    
    def calculate_statistics(self, results):
        """Calculate statistics from analysis results.
        
        Args:
            results: Output from analyze_inference_results()
            
        Returns:
            Dictionary containing memorization statistics
        """
        total = results['total_files']
        matches = results['matches']
        
        statistics = {
            'total_sequences': total,
            'memorized_sequences': matches['both'],
            'memorization_rate': matches['both'] / total if total > 0 else 0,
            'partial_matches': {
                'first_only': matches['first_only'],
                'last_only': matches['last_only'],
                'first_only_rate': matches['first_only'] / total if total > 0 else 0,
                'last_only_rate': matches['last_only'] / total if total > 0 else 0
            },
            'no_matches': matches['none'],
            'no_match_rate': matches['none'] / total if total > 0 else 0
        }
        
        return statistics
    
    def print_report(self, statistics):
        """Print formatted analysis report.
        
        Args:
            statistics: Output from calculate_statistics()
        """
        print("\n" + "="*60)
        print("N-GRAM MATCHING ANALYSIS")
        print("="*60)
        print(f"Total sequences analyzed: {statistics['total_sequences']}")
        print(f"Memorized sequences: {statistics['memorized_sequences']}")
        print(f"Memorization rate: {statistics['memorization_rate']:.2%}")
        print("="*60)
    
    def save_results(self, results, statistics, output_path):
        """Save analysis results to JSON file.
        
        Args:
            results: Output from analyze_inference_results()
            statistics: Output from calculate_statistics()
            output_path: Path to save JSON file
        """
        output = {
            'statistics': statistics,
            'results': results
        }
        
        with open(output_path, 'w') as f:
            json.dump(output, f, indent=2)
        
        print(f"\nResults saved to: {output_path}")
    
    def run_full_analysis(self, n=10, output_path=None):
        """Execute complete analysis pipeline.
        
        Args:
            n: Size of n-gram (default: 10)
            output_path: Path to save results JSON (optional)
            
        Returns:
            Tuple of (results, statistics)
        """
        # Load training data
        self.load_training_data()
        
        # Build n-gram index from training data
        self.build_training_ngram_index(n=n)
        
        # Collect inference files with balanced sampling
        self.collect_inference_files_balanced()
        
        # Analyze inference results
        results = self.analyze_inference_results(n=n)
        
        if results is None:
            print("Analysis failed.")
            return None, None
        
        # Add sampling information
        results['sampling_info'] = self.sampling_info
        
        # Calculate statistics
        statistics = self.calculate_statistics(results)
        
        # Print report
        self.print_report(statistics)
        
        # Save results
        if output_path:
            self.save_results(results, statistics, output_path)
        
        return results, statistics


def main():
    """Main execution function."""
    import sys
    
    # Set paths relative to script directory
    script_dir = Path(__file__).parent.absolute()
    base_dir = script_dir
    
    # Find training data (prefer Training_renamed.npy over Training.npy)
    if (script_dir / "Training_renamed.npy").exists():
        training_npy_path = script_dir / "Training_renamed.npy"
    elif (script_dir / "Training.npy").exists():
        training_npy_path = script_dir / "Training.npy"
    else:
        print("Error: Training.npy or Training_renamed.npy not found in current directory")
        return
    
    output_path = script_dir / "GPT_Memorization_Analysis_Balanced_Results.json"
    
    # Sample size per circuit type (1000 total / 15 types ≈ 67)
    samples_per_type = 67
    
    # Set random seed for reproducibility
    random.seed(42)
    
    print(f"\n{'='*60}")
    print(f"N-GRAM MATCHING ANALYSIS")
    print(f"{'='*60}")
    print(f"Training data: {training_npy_path.name}")
    print(f"Samples per type: {samples_per_type}")
    print(f"{'='*60}\n")
    
    # Create analyzer and run analysis
    analyzer = MemorizationAnalyzer(base_dir, training_npy_path, samples_per_type=samples_per_type)
    results, statistics = analyzer.run_full_analysis(
        n=10,
        output_path=output_path
    )
    
    if results is None:
        return


if __name__ == "__main__":
    main()
