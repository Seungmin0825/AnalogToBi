#!/usr/bin/env python3
"""
Circuit-ID-Based Train-Validation Split for GAT Training

This module performs a train-validation split at the circuit ID level to prevent
data leakage in GAT (Graph Attention Network) training. Unlike sequence-level 
splitting, this ensures that all sequences from the same circuit ID appear in 
only one split (training OR validation), preventing the same graph topology 
from appearing in both sets.

Key Features:
- Split by circuit ID rather than individual sequences
- Stratified by circuit type to maintain distribution
- Circuit types with fewer than 5 unique IDs are excluded from validation
  (all sequences go to training to ensure sufficient data)
- Approximately 90/10 split ratio where possible

Input:
    Dataset/*/Sequence_bipart*.npy - Bipartite graph sequences

Output:
    Training_GAT.npy - Training set (circuit ID-based split)
    Validation_GAT.npy - Validation set (circuit ID-based split)
    split_statistics.txt - Detailed split statistics

Usage:
    python PREPROCESSING_Circuit_ID_Split.py
"""

import numpy as np
import os
from collections import defaultdict

# Directories to process
base_dirs = ["Dataset"]

# Specify the seed for reproducibility
seed = 42
np.random.seed(seed)

# Circuit type mapping
circuit_types = [
    "CIRCUIT_Opamp", "CIRCUIT_Mirror", "CIRCUIT_Comparator",
    "CIRCUIT_Mixer", "CIRCUIT_LDO", "CIRCUIT_Oscillator",
    "CIRCUIT_Filter", "CIRCUIT_Bandgap_Ref", "CIRCUIT_Power_Amp",
    "CIRCUIT_Voltage_Regulator", "CIRCUIT_Power_converter",
    "CIRCUIT_PLL", "CIRCUIT_Switched_Cap", "CIRCUIT_ADC_DAC",
    "CIRCUIT_General"
]

print("Loading sequences...")

# Data structure: {circuit_id: {'sequences': [...], 'circuit_type': str}}
circuits_data = defaultdict(lambda: {'sequences': [], 'circuit_type': None})

for base_dir in base_dirs:
    for i in range(1, 3503):
        circuit_id = str(i)
        dir_path = f"{base_dir}/{circuit_id}"
        if not os.path.isdir(dir_path):
            continue
        
        # Load bipartite sequence for this circuit
        sequence_bipart_path = os.path.join(base_dir, circuit_id, f'Sequence_bipart{circuit_id}.npy')
        if os.path.exists(sequence_bipart_path):
            data = np.load(sequence_bipart_path, allow_pickle=True)
            
            # Determine circuit type from first sequence's first token
            if len(data) > 0:
                first_token = str(data[0][0])
                circuit_type = "CIRCUIT_General"  # Default
                for ct in circuit_types:
                    if first_token.startswith(ct):
                        circuit_type = ct
                        break
                
                circuits_data[circuit_id]['sequences'] = data
                circuits_data[circuit_id]['circuit_type'] = circuit_type
            
            if len(circuits_data) % 100 == 0:
                print(f"  Loaded {len(circuits_data)} circuits...")

print(f"\nTotal circuits loaded: {len(circuits_data)}")

# Group circuit IDs by circuit type
circuit_ids_by_type = defaultdict(list)

for circuit_id, data in circuits_data.items():
    circuit_type = data['circuit_type']
    circuit_ids_by_type[circuit_type].append(circuit_id)

# Print distribution
print("\nCircuit type distribution (by circuit ID count):")
total_sequences = 0
for ct in circuit_types:
    circuit_ids = circuit_ids_by_type[ct]
    num_circuits = len(circuit_ids)
    num_sequences = sum(len(circuits_data[cid]['sequences']) for cid in circuit_ids)
    total_sequences += num_sequences
    print(f"  {ct}: {num_circuits} circuits, {num_sequences} sequences")

print(f"\nTotal sequences: {total_sequences}")

# Stratified split by circuit ID
print("\nSplitting by circuit ID (circuit types with < 5 IDs assigned entirely to training):")

training_circuit_ids = []
validation_circuit_ids = []
split_info = []

for ct in circuit_types:
    circuit_ids = circuit_ids_by_type[ct]
    num_circuits = len(circuit_ids)
    
    if num_circuits < 5:
        # Too few circuits - put all in training
        training_circuit_ids.extend(circuit_ids)
        split_info.append({
            'type': ct,
            'total_circuits': num_circuits,
            'train_circuits': num_circuits,
            'val_circuits': 0,
            'reason': 'insufficient_circuits'
        })
        print(f"  {ct}: {num_circuits} circuits → ALL to TRAINING (< 5 circuits)")
    else:
        # Sufficient circuits - perform 90/10 split
        circuit_ids_array = np.array(circuit_ids)
        np.random.shuffle(circuit_ids_array)
        
        split_idx = int(len(circuit_ids_array) * 0.9)
        train_ids = circuit_ids_array[:split_idx]
        val_ids = circuit_ids_array[split_idx:]
        
        training_circuit_ids.extend(train_ids.tolist())
        validation_circuit_ids.extend(val_ids.tolist())
        
        split_info.append({
            'type': ct,
            'total_circuits': num_circuits,
            'train_circuits': len(train_ids),
            'val_circuits': len(val_ids),
            'reason': 'stratified_split'
        })
        print(f"  {ct}: {num_circuits} circuits → {len(train_ids)} train, {len(val_ids)} val")

# Shuffle circuit IDs to avoid clustering
np.random.shuffle(training_circuit_ids)
np.random.shuffle(validation_circuit_ids)

print(f"\nTotal training circuits: {len(training_circuit_ids)}")
print(f"Total validation circuits: {len(validation_circuit_ids)}")

# Collect sequences for training and validation

training_sequences = []
for circuit_id in training_circuit_ids:
    sequences = circuits_data[circuit_id]['sequences']
    training_sequences.append(sequences)
    
validation_sequences = []
for circuit_id in validation_circuit_ids:
    sequences = circuits_data[circuit_id]['sequences']
    validation_sequences.append(sequences)

# Concatenate all sequences
training_total_data = np.concatenate(training_sequences, axis=0)
validation_total_data = np.concatenate(validation_sequences, axis=0) if validation_sequences else np.array([])

print(f"Training sequences: {len(training_total_data)}")
print(f"Validation sequences: {len(validation_total_data)}")

# Verify no circuit ID overlap
train_set = set(training_circuit_ids)
val_set = set(validation_circuit_ids)
overlap = train_set & val_set

if overlap:
    print(f"  WARNING: Found {len(overlap)} overlapping circuit IDs!")
    print(f"  Overlapping IDs: {sorted(list(overlap))[:10]}...")
else:
    print(f"  No overlap detected - training and validation are properly separated")

# Print detailed statistics
print("\nTraining set distribution:")
train_type_counts = defaultdict(int)
train_type_circuits = defaultdict(set)
for circuit_id in training_circuit_ids:
    circuit_type = circuits_data[circuit_id]['circuit_type']
    num_sequences = len(circuits_data[circuit_id]['sequences'])
    train_type_counts[circuit_type] += num_sequences
    train_type_circuits[circuit_type].add(circuit_id)

for ct in circuit_types:
    count = train_type_counts[ct]
    num_circuits = len(train_type_circuits[ct])
    percentage = count / len(training_total_data) * 100 if len(training_total_data) > 0 else 0
    print(f"  {ct}: {count} sequences from {num_circuits} circuits ({percentage:.2f}%)")

if len(validation_total_data) > 0:
    print("\nValidation set distribution:")
    val_type_counts = defaultdict(int)
    val_type_circuits = defaultdict(set)
    for circuit_id in validation_circuit_ids:
        circuit_type = circuits_data[circuit_id]['circuit_type']
        num_sequences = len(circuits_data[circuit_id]['sequences'])
        val_type_counts[circuit_type] += num_sequences
        val_type_circuits[circuit_type].add(circuit_id)

    for ct in circuit_types:
        count = val_type_counts[ct]
        num_circuits = len(val_type_circuits[ct])
        percentage = count / len(validation_total_data) * 100 if len(validation_total_data) > 0 else 0
        print(f"  {ct}: {count} sequences from {num_circuits} circuits ({percentage:.2f}%)")

# Save the arrays
np.save('Training_GAT.npy', training_total_data)
if len(validation_total_data) > 0:
    np.save('Validation_GAT.npy', validation_total_data)
else:
    print("  Note: No validation data to save (all circuits in training)")

# Save detailed statistics to file
with open('split_statistics.txt', 'w') as f:
    f.write("="*80 + "\n")
    f.write("CIRCUIT-ID-BASED TRAIN-VALIDATION SPLIT STATISTICS\n")
    f.write("="*80 + "\n\n")
    
    f.write(f"Total circuits: {len(circuits_data)}\n")
    f.write(f"Training circuits: {len(training_circuit_ids)}\n")
    f.write(f"Validation circuits: {len(validation_circuit_ids)}\n")
    f.write(f"Training sequences: {len(training_total_data)}\n")
    f.write(f"Validation sequences: {len(validation_total_data)}\n\n")
    
    f.write("Split Strategy:\n")
    f.write("- Circuit types with >= 5 circuits: 90/10 train/val split\n")
    f.write("- Circuit types with < 5 circuits: all to training\n\n")
    
    f.write("Circuit Type Details:\n")
    f.write("-" * 80 + "\n")
    for info in split_info:
        f.write(f"{info['type']}:\n")
        f.write(f"  Total circuits: {info['total_circuits']}\n")
        f.write(f"  Training circuits: {info['train_circuits']}\n")
        f.write(f"  Validation circuits: {info['val_circuits']}\n")
        f.write(f"  Strategy: {info['reason']}\n\n")
    
    f.write("\nTraining Set by Circuit Type:\n")
    f.write("-" * 80 + "\n")
    for ct in circuit_types:
        count = train_type_counts[ct]
        num_circuits = len(train_type_circuits[ct])
        percentage = count / len(training_total_data) * 100 if len(training_total_data) > 0 else 0
        f.write(f"{ct}: {count} sequences from {num_circuits} circuits ({percentage:.2f}%)\n")
    
    if len(validation_total_data) > 0:
        f.write("\nValidation Set by Circuit Type:\n")
        f.write("-" * 80 + "\n")
        for ct in circuit_types:
            count = val_type_counts[ct]
            num_circuits = len(val_type_circuits[ct])
            percentage = count / len(validation_total_data) * 100 if len(validation_total_data) > 0 else 0
            f.write(f"{ct}: {count} sequences from {num_circuits} circuits ({percentage:.2f}%)\n")
    
    f.write("\nCircuit ID Lists:\n")
    f.write("-" * 80 + "\n")
    f.write(f"Training circuit IDs ({len(training_circuit_ids)}): {sorted(training_circuit_ids)}\n\n")
    f.write(f"Validation circuit IDs ({len(validation_circuit_ids)}): {sorted(validation_circuit_ids)}\n")

print(f"\nSaved: Training_GAT.npy {training_total_data.shape}")
if len(validation_total_data) > 0:
    print(f"Saved: Validation_GAT.npy {validation_total_data.shape}")
print("Saved: split_statistics.txt")
