"""
Circuit Type Token Injection for Conditional Generation

This script adds circuit type tokens to the beginning of each sequence to enable
functional control during generation. Each circuit is categorized into one of 15
functional types based on dataset ID ranges.

Circuit Categories (15 types):
- CIRCUIT_Opamp: Operational amplifiers
- CIRCUIT_LDO: Low-dropout regulators
- CIRCUIT_Bandgap_Ref: Bandgap reference circuits
- CIRCUIT_Power_converter: DC-DC converters and power management
- CIRCUIT_Oscillator: Clock and signal generators
- CIRCUIT_Comparator: Voltage comparators
- CIRCUIT_Mirror: Current mirrors
- CIRCUIT_Mixer: RF mixers
- CIRCUIT_Filter: Active filters
- CIRCUIT_Power_Amp: Power amplifiers
- CIRCUIT_Voltage_Regulator: Voltage regulators
- CIRCUIT_PLL: Phase-locked loops
- CIRCUIT_Switched_Cap: Switched-capacitor circuits
- CIRCUIT_ADC_DAC: Data converters
- CIRCUIT_General: Uncategorized circuits

Sequence Modification:
- Original: [VSS, ..., TRUNCATE, TRUNCATE, ...]
- Modified: [CIRCUIT_Type, VSS, ..., TRUNCATE, ...]
- Length preserved at T_max = 1024 tokens
"""

import numpy as np
import os
from tqdm import tqdm

def get_circuit_category(dataset_number):
    """Determine circuit functional category based on dataset ID.
    
    Maps dataset IDs to one of 15 predefined circuit functional categories.
    Dataset ID ranges are assigned based on circuit functionality analysis.
    
    Args:
        dataset_number: Integer dataset ID (1-3502)
    Returns:
        String circuit type token (e.g., 'CIRCUIT_Opamp', 'CIRCUIT_LDO')
    """
    if (1 <= dataset_number <= 97) or (184 <= dataset_number <= 355) or (461 <= dataset_number <= 492) or (614 <= dataset_number <= 621) or (628 <= dataset_number <= 631) or (636 <= dataset_number <= 639) or (669 <= dataset_number <= 687) or (702 <= dataset_number <= 725) or (822 <= dataset_number <= 833) or (868 <= dataset_number <= 902) or (907 <= dataset_number <= 914) or (921 <= dataset_number <= 932) or (953 <= dataset_number <= 1029) or (1781 <= dataset_number <= 2180):
        return "CIRCUIT_Opamp"
    elif (98 <= dataset_number <= 159) or (604 <= dataset_number <= 613) or (622 <= dataset_number <= 623) or (834 <= dataset_number <= 867):
        return "CIRCUIT_Mirror"
    elif (632 <= dataset_number <= 635) or (738 <= dataset_number <= 749) or (1039 <= dataset_number <= 1041) or (1045 <= dataset_number <= 1080):
        return "CIRCUIT_Comparator"
    elif (494 <= dataset_number <= 520) or (1091 <= dataset_number <= 1099):
        return "CIRCUIT_Mixer"
    elif (2181 <= dataset_number <= 2630):
        return "CIRCUIT_LDO"
    elif (403 <= dataset_number <= 437) or (521 <= dataset_number <= 544) or (640 <= dataset_number <= 646) or (1109 <= dataset_number <= 1190):
        return "CIRCUIT_Oscillator"
    elif (651 <= dataset_number <= 651) or (768 <= dataset_number <= 788):
        return "CIRCUIT_Filter"
    elif (368 <= dataset_number <= 384) or (624 <= dataset_number <= 627) or (1461 <= dataset_number <= 1780):
        return "CIRCUIT_Bandgap_Ref"
    elif (578 <= dataset_number <= 592) or (1100 <= dataset_number <= 1108):
        return "CIRCUIT_Power_Amp"
    elif (726 <= dataset_number <= 737):
        return "CIRCUIT_Voltage_Regulator"
    elif (1191 <= dataset_number <= 1460):
        return "CIRCUIT_Power_converter"
    elif (438 <= dataset_number <= 440) or (545 <= dataset_number <= 577) or (647 <= dataset_number <= 650) or (819 <= dataset_number <= 821):
        return "CIRCUIT_PLL"
    elif (385 <= dataset_number <= 395) or (750 <= dataset_number <= 767) or (789 <= dataset_number <= 811) or (1044 <= dataset_number <= 1044) or (2631 <= dataset_number <= 3502):
        return "CIRCUIT_Switched_Cap"
    elif (812 <= dataset_number <= 818) or (1042 <= dataset_number <= 1043):
        return "CIRCUIT_ADC_DAC"
    else:
        return "CIRCUIT_General"

def add_circuit_type_to_sequences(dataset_start=1, dataset_end=3502, backup=True, use_bipart=True):
    """Inject circuit type tokens at the beginning of each sequence.
    
    Modifies existing sequence files by prepending circuit type tokens while
    maintaining fixed sequence length (T_max = 1024). Creates backups of
    original files if requested.
    
    Process:
    1. Load existing sequences from .npy files
    2. Determine circuit category from dataset ID
    3. Insert circuit type token at position 0
    4. Maintain T_max = 1024 by adjusting TRUNCATE padding
    5. Save modified sequences back to file
    
    Args:
        dataset_start: Starting dataset ID
        dataset_end: Ending dataset ID
        backup: If True, save original files as *_VSS.npy before modification
        use_bipart: If True, process Sequence_bipart files; if False, process Sequence_total files
    Returns:
        Dictionary containing processing statistics
    """
    
    stats = {
        'processed': 0,
        'skipped': 0,
        'errors': 0,
        'circuit_types': {}
    }
    
    file_prefix = "Sequence_bipart" if use_bipart else "Sequence_total"
    print(f"\n{'='*80}")
    print(f"Circuit Type Token Injection")
    print(f"{'='*80}")
    print(f"Dataset range: {dataset_start} to {dataset_end}")
    print(f"Target files: {file_prefix}{{id}}.npy")
    print(f"Backup mode: {'Enabled' if backup else 'Disabled'}")
    print(f"Sequence length: T_max = 1024 (preserved)")
    print(f"{'='*80}\n")
    
    for i in tqdm(range(dataset_start, dataset_end + 1), desc="Processing datasets"):
        sequence_file = f"Dataset/{i}/{file_prefix}{i}.npy"
        
        # Check if file exists
        if not os.path.exists(sequence_file):
            stats['skipped'] += 1
            continue
        
        try:
            # Load existing sequences
            sequences = np.load(sequence_file, allow_pickle=True)
            original_shape = sequences.shape
            
            # Check if circuit type token already exists
            if len(sequences) > 0 and str(sequences[0][0]).startswith('CIRCUIT_'):
                current_type = str(sequences[0][0])
                expected_type = get_circuit_category(i)
                if current_type == expected_type:
                    stats['skipped'] += 1
                    continue
                else:
                    # Category mismatch - needs update
                    print(f"  Circuit {i}: Updating {current_type} -> {expected_type}")
            
            # Determine functional category
            circuit_type = get_circuit_category(i)
            stats['circuit_types'][circuit_type] = stats['circuit_types'].get(circuit_type, 0) + 1
            
            # Create backup of original file
            if backup:
                backup_file = f"Dataset/{i}/{file_prefix}{i}_VSS.npy"
                if not os.path.exists(backup_file):
                    np.save(backup_file, sequences)
            
            # Construct new sequences with circuit type tokens
            new_sequences = []
            
            for seq in sequences:
                # Locate TRUNCATE padding start
                truncate_pos = None
                for j, token in enumerate(seq):
                    if token == 'TRUNCATE':
                        truncate_pos = j
                        break
                
                if truncate_pos is not None and truncate_pos > 0:
                    # Extract actual sequence (exclude TRUNCATE padding)
                    actual_seq = seq[:truncate_pos].tolist()
                    
                    # Prepend circuit type token
                    new_seq = [circuit_type] + actual_seq
                    
                    # Re-pad to T_max = 1024
                    padded_seq = new_seq + ['TRUNCATE'] * (1024 - len(new_seq))
                    new_sequences.append(padded_seq[:1024])
                else:
                    # No padding found - entire sequence is content
                    actual_seq = seq.tolist()
                    new_seq = [circuit_type] + actual_seq
                    new_sequences.append(new_seq[:1024])
            
            # Convert to new array
            new_sequences_array = np.array(new_sequences, dtype=object)
            
            # Save file
            np.save(sequence_file, new_sequences_array)
            
            stats['processed'] += 1
            
            # Progress logging (every 100 circuits)
            if i % 100 == 0:
                print(f"  Circuit {i}: {original_shape} -> {new_sequences_array.shape}, Type: {circuit_type}")
        
        except Exception as e:
            print(f"  Error processing Circuit {i}: {e}")
            stats['errors'] += 1
            continue
    
    # Print final statistics
    print("\n" + "="*80)
    print("Circuit Type Injection Completed")
    print("="*80)
    print(f"Successfully processed: {stats['processed']} circuits")
    print(f"Skipped (already tagged): {stats['skipped']} circuits") 
    print(f"Errors encountered: {stats['errors']} circuits")
    
    print(f"\nCircuit Type Distribution:")
    total_categorized = sum(stats['circuit_types'].values())
    for circuit_type, count in sorted(stats['circuit_types'].items()):
        percentage = (count / total_categorized * 100) if total_categorized > 0 else 0
        print(f"  {circuit_type:30s}: {count:4d} ({percentage:5.1f}%)")
    print("="*80)
    
    return stats

if __name__ == "__main__":
    # Test mode: Process small range first
    print("\n" + "="*80)
    print("Test Mode: Processing Circuits 1-100")
    print("="*80)
    test_stats = add_circuit_type_to_sequences(1, 100, backup=True, use_bipart=True)
    
    # Prompt for full dataset processing
    if test_stats['processed'] > 0:
        response = input(f"\nTest successful. Process full dataset (1-3502)? (y/N): ")
        if response.lower() == 'y':
            print("\nInitiating full dataset processing...\n")
            full_stats = add_circuit_type_to_sequences(1, 3502, backup=True, use_bipart=True)
        else:
            print("\nTest completed. Full processing skipped.")
    else:
        print("\nTest failed: No files were processed. Please verify input files exist.")