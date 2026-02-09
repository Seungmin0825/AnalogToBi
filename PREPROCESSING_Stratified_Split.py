#!/usr/bin/env python3
"""
Stratified Train-Validation Split for Circuit Datasets

This module loads bipartite graph sequences from the Dataset directory and 
performs a stratified 90/10 train-validation split. Stratification ensures 
that each circuit type maintains the same distribution in both training and 
validation sets.

The split preserves the relative proportions of 15 functional circuit 
categories (Opamp, LDO, Mirror, etc.) to ensure balanced evaluation and 
training across all circuit types.

Input:
    Dataset/*/Sequence_bipart*.npy - Bipartite graph sequences

Output:
    Training.npy - 90% of data, stratified by circuit type
    Validation.npy - 10% of data, stratified by circuit type

Usage:
    python PREPROCESSING_Stratified_Split.py
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

print("Step 1: Loading all sequences and extracting circuit types...")

# Load all sequences at once
all_sequences = []
sequence_total_data_paths = []

for base_dir in base_dirs:
    for i in range(1, 3503):
        number = str(i)
        dir_path = f"{base_dir}/{number}"
        if not os.path.isdir(dir_path):
            continue
        
        # Use Sequence_bipart instead of Sequence_total
        sequence_bipart_path = os.path.join(base_dir, number, f'Sequence_bipart{number}.npy')
        if os.path.exists(sequence_bipart_path):
            data = np.load(sequence_bipart_path, allow_pickle=True)
            all_sequences.append(data)
            sequence_total_data_paths.append(sequence_bipart_path)
            if len(all_sequences) % 500 == 0:
                print(f"  Loaded {len(all_sequences)} files...")

# Concatenate all sequences
print("\nStep 2: Concatenating all sequences...")
all_sequences = np.concatenate(all_sequences, axis=0)
print(f"Total sequences: {len(all_sequences)}")

# Group sequences by circuit type
print("\nStep 3: Grouping sequences by circuit type...")
sequences_by_type = defaultdict(list)

for idx, seq in enumerate(all_sequences):
    # Extract circuit type from first token
    first_token = str(seq[0])
    circuit_type = None
    for ct in circuit_types:
        if first_token.startswith(ct):
            circuit_type = ct
            break
    if circuit_type is None:
        circuit_type = "CIRCUIT_General"  # Fallback
    
    sequences_by_type[circuit_type].append(idx)
    
    if (idx + 1) % 50000 == 0:
        print(f"  Processed {idx + 1}/{len(all_sequences)} sequences...")

# Print distribution
print("\nCircuit type distribution:")
for ct in circuit_types:
    count = len(sequences_by_type[ct])
    percentage = count / len(all_sequences) * 100
    print(f"  {ct}: {count} ({percentage:.2f}%)")

# Stratified split: 90/10 for each circuit type
print("\nStep 4: Performing stratified split (90/10)...")
training_indices = []
validation_indices = []

for ct in circuit_types:
    indices = np.array(sequences_by_type[ct])
    np.random.shuffle(indices)
    
    split_idx = int(len(indices) * 0.9)
    training_indices.extend(indices[:split_idx].tolist())
    validation_indices.extend(indices[split_idx:].tolist())

# Shuffle the indices to avoid clustering
training_indices = np.array(training_indices)
validation_indices = np.array(validation_indices)
np.random.shuffle(training_indices)
np.random.shuffle(validation_indices)

print(f"Training sequences: {len(training_indices)}")
print(f"Validation sequences: {len(validation_indices)}")

# Create training and validation datasets
print("\nStep 5: Creating training and validation datasets...")
training_total_data = all_sequences[training_indices]
validation_total_data = all_sequences[validation_indices]

# Verify stratification
print("\nTraining set distribution:")
train_type_counts = defaultdict(int)
for seq in training_total_data:
    first_token = str(seq[0])
    for ct in circuit_types:
        if first_token.startswith(ct):
            train_type_counts[ct] += 1
            break

for ct in circuit_types:
    count = train_type_counts[ct]
    percentage = count / len(training_total_data) * 100
    print(f"  {ct}: {count} ({percentage:.2f}%)")

print("\nValidation set distribution:")
val_type_counts = defaultdict(int)
for seq in validation_total_data:
    first_token = str(seq[0])
    for ct in circuit_types:
        if first_token.startswith(ct):
            val_type_counts[ct] += 1
            break

for ct in circuit_types:
    count = val_type_counts[ct]
    percentage = count / len(validation_total_data) * 100
    print(f"  {ct}: {count} ({percentage:.2f}%)")

# Save the arrays
print("\nStep 6: Saving datasets...")
np.save('Training.npy', training_total_data)
np.save('Validation.npy', validation_total_data)

# Print the shapes of the training and validation data
print("\nTraining total data shape:", training_total_data.shape)
print("Validation total data shape:", validation_total_data.shape)
print("\nStratified split completed successfully!")