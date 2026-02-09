#!/usr/bin/env python3
"""
GAT Circuit Classifier - Batch Analysis for All Inference Directories

This module performs batch classification across all Inference_CIRCUIT_* 
directories using a trained GAT classifier. It computes classification accuracy
for each circuit type by comparing predicted labels against ground truth labels
derived from directory names.

The module automatically:
    - Discovers all circuit-type inference directories
    - Classifies each circuit using the trained GAT model
    - Computes accuracy ("Right %") for each functional category
    - Generates detailed prediction distribution statistics
    - Saves comprehensive analysis results

Usage:
    python GAT_Inference_ALL.py

Output:
    Analysis_Results/gat_classification_summary.txt
"""

import os
import torch
import numpy as np
from torch_geometric.data import Data
from Models.GAT import GATClassifier
from collections import defaultdict, Counter

# Device
device = 'cuda' if torch.cuda.is_available() else 'cpu'
print(f"Using device: {device}")

# Model path
model_path = 'GAT_Classifier.pth'

# Circuit type mapping
circuit_types = [
    "CIRCUIT_Opamp", "CIRCUIT_Mirror", "CIRCUIT_Comparator",
    "CIRCUIT_Mixer", "CIRCUIT_LDO", "CIRCUIT_Oscillator",
    "CIRCUIT_Filter", "CIRCUIT_Bandgap_Ref", "CIRCUIT_Power_Amp",
    "CIRCUIT_Voltage_Regulator", "CIRCUIT_Power_converter",
    "CIRCUIT_PLL", "CIRCUIT_Switched_Cap", "CIRCUIT_ADC_DAC",
    "CIRCUIT_General"
]

# Build vocabulary (same as GPT_Pretrain.py - bipartite graph structure)
print("Building vocabulary...")

vocab_tokens = []

# 1. Edge types (connection types between nodes)
# MOSFET edges (M_ prefix)
vocab_tokens.extend([
    'M_B', 'M_D', 'M_G', 'M_S',  # Single pin
    'M_BD', 'M_BG', 'M_BS', 'M_DG', 'M_DS', 'M_GS',  # Two pins
    'M_BDG', 'M_BDS', 'M_BGS', 'M_DGS',  # Three pins
    'M_BDGS'  # Four pins
])
# BJT edges (B_ prefix)
vocab_tokens.extend([
    'B_B', 'B_C', 'B_E',  # Single pin
    'B_BC', 'B_BE', 'B_CE',  # Two pins
    'B_BCE'  # Three pins
])
# Passive device edges
vocab_tokens.extend(['R_C', 'C_C', 'L_C'])
# Diode edges (D_ prefix)
vocab_tokens.extend(['D_P', 'D_N', 'D_NP', 'D_PN'])

# 2. Power rails
vocab_tokens.extend(['VSS', 'VDD'])

# 3. Circuit type tokens
circuit_type_tokens = [
    'CIRCUIT_Opamp', 'CIRCUIT_LDO', 'CIRCUIT_Bandgap_Ref',
    'CIRCUIT_Power_converter', 'CIRCUIT_Oscillator', 'CIRCUIT_General',
    'CIRCUIT_Mirror', 'CIRCUIT_Mixer', 'CIRCUIT_Power_Amp',
    'CIRCUIT_PLL', 'CIRCUIT_Filter', 'CIRCUIT_Comparator',
    'CIRCUIT_Voltage_Regulator', 'CIRCUIT_Switched_Cap', 'CIRCUIT_ADC_DAC'
]
vocab_tokens.extend(circuit_type_tokens)

# 4. Device nodes
for i in range(1, 36): vocab_tokens.append(f'NM{i}')
for i in range(1, 36): vocab_tokens.append(f'PM{i}')
for i in range(1, 28): vocab_tokens.append(f'NPN{i}')
for i in range(1, 28): vocab_tokens.append(f'PNP{i}')
for i in range(1, 29): vocab_tokens.append(f'R{i}')
for i in range(1, 17): vocab_tokens.append(f'C{i}')
for i in range(1, 25): vocab_tokens.append(f'L{i}')
for i in range(1, 9): vocab_tokens.append(f'DIO{i}')

# 5. Net nodes
for i in range(1, 51): vocab_tokens.append(f'NET{i}')

# 6. Port nodes
for i in range(1, 21): vocab_tokens.append(f'VIN{i}')
vocab_tokens.append('VOUT')
for i in range(1, 8): vocab_tokens.append(f'VOUT{i}')
for i in range(1, 4): vocab_tokens.append(f'IIN{i}')
for i in range(1, 6): vocab_tokens.append(f'IOUT{i}')
for i in range(1, 12): vocab_tokens.append(f'VB{i}')
for i in range(1, 8): vocab_tokens.append(f'IB{i}')
for i in range(1, 22): vocab_tokens.append(f'VCONT{i}')
for i in range(1, 4): vocab_tokens.extend([f'VCM{i}', f'VREF{i}', f'IREF{i}', f'VRF{i}', f'VIF{i}'])
for i in range(1, 6): vocab_tokens.extend([f'VLO{i}', f'VBB{i}'])

# 7. Special tokens
vocab_tokens.append('TRUNCATE')

devices = vocab_tokens

stoi = {device: i for i, device in enumerate(devices)}
itos = {i: device for i, device in enumerate(devices)}
vocab_size = len(devices)

print(f"Vocabulary size: {vocab_size}")

# Load model
print(f"Loading model from {model_path}...")
checkpoint = torch.load(model_path, map_location=device)

# Load label mappings
label_to_idx = checkpoint.get('label_to_idx', {ct: i for i, ct in enumerate(circuit_types)})
idx_to_label = checkpoint.get('idx_to_label', {i: ct for i, ct in enumerate(circuit_types)})

# Model parameters from checkpoint
embedding_dim = checkpoint.get('embedding_dim', 64)
hidden_dim = checkpoint.get('hidden_dim', 128)
num_heads = checkpoint.get('num_heads', 4)
num_layers = checkpoint.get('num_layers', 3)
dropout = checkpoint.get('dropout', 0.3)
model_vocab_size = checkpoint.get('vocab_size', vocab_size)

# Verify vocabulary compatibility
if model_vocab_size != vocab_size:
    print(f"WARNING: Vocab size mismatch! Model: {model_vocab_size}, Current: {vocab_size}")
    print(f"Using model's vocab size: {model_vocab_size}")
    vocab_size = model_vocab_size

model = GATClassifier(
    vocab_size=vocab_size,
    num_classes=len(circuit_types),
    embedding_dim=embedding_dim,
    hidden_dim=hidden_dim,
    num_heads=num_heads,
    num_layers=num_layers,
    dropout=dropout
).to(device)

model.load_state_dict(checkpoint['model_state_dict'])
model.eval()

print(f"Model loaded successfully!")
print(f"Model configuration:")
print(f"  - Embedding dim: {embedding_dim}")
print(f"  - Hidden dim: {hidden_dim}")
print(f"  - Num heads: {num_heads}")
print(f"  - Num layers: {num_layers}")
print(f"  - Dropout: {dropout}")
print(f"  - Vocab size: {vocab_size}")
if 'best_val_acc' in checkpoint:
    print(f"  - Best validation accuracy: {checkpoint['best_val_acc']:.2f}%")


def sequence_to_graph(seq):
    """Convert circuit sequence to graph representation (Bipartite structure)"""
    first_token_str = str(seq[0])
    start_idx = 1 if first_token_str.startswith('CIRCUIT_') else 0
    
    # Edge type tokens (NOT graph nodes)
    # MOSFET edges (M_ prefix)
    edge_types = {'M_B', 'M_D', 'M_G', 'M_S', 'M_BD', 'M_BG', 'M_BS', 'M_DG', 'M_DS', 'M_GS',
                  'M_BDG', 'M_BDS', 'M_BGS', 'M_DGS', 'M_BDGS',
                  # BJT edges (B_ prefix)
                  'B_B', 'B_C', 'B_E', 'B_BC', 'B_BE', 'B_CE', 'B_BCE',
                  # Passive edges
                  'R_C', 'C_C', 'L_C',
                  # Diode edges (D_ prefix)
                  'D_P', 'D_N', 'D_NP', 'D_PN'}
    
    nodes_set = set()
    seq_len = len(seq)
    
    for i in range(start_idx, seq_len):
        token_str = str(seq[i])
        if token_str == 'TRUNCATE':
            break
        if token_str not in edge_types:
            token_idx = stoi.get(token_str, stoi.get('VSS', 0))
            nodes_set.add(token_idx)
    
    node_indices = sorted(list(nodes_set))
    node_to_graph_idx = {token_idx: graph_idx for graph_idx, token_idx in enumerate(node_indices)}
    
    edges = []
    edge_attrs = []
    
    for i in range(start_idx, seq_len - 2, 2):
        token_str1 = str(seq[i])
        edge_str = str(seq[i + 1])
        token_str2 = str(seq[i + 2])
        
        if token_str1 == 'TRUNCATE' or token_str2 == 'TRUNCATE':
            break
        if token_str1 in edge_types or token_str2 in edge_types:
            continue
        
        token_idx1 = stoi.get(token_str1, stoi.get('VSS', 0))
        token_idx2 = stoi.get(token_str2, stoi.get('VSS', 0))
        edge_type_idx = stoi.get(edge_str, stoi.get('VSS', 0))
        
        if token_idx1 in node_to_graph_idx and token_idx2 in node_to_graph_idx:
            graph_idx1 = node_to_graph_idx[token_idx1]
            graph_idx2 = node_to_graph_idx[token_idx2]
            edges.append((graph_idx1, graph_idx2))
            edge_attrs.append(edge_type_idx)
            edges.append((graph_idx2, graph_idx1))
            edge_attrs.append(edge_type_idx)
    
    return node_indices, edges, edge_attrs


def create_graph_data(seq):
    """Create PyTorch Geometric Data object from sequence"""
    node_indices, edges, edge_attrs = sequence_to_graph(seq)
    
    if len(node_indices) == 0:
        vss_idx = stoi.get('VSS', 0)
        node_indices = [vss_idx]
        edges = []
        edge_attrs = [vss_idx]
    
    x = torch.tensor(node_indices, dtype=torch.long)
    
    if len(edges) > 0:
        edge_index = torch.tensor(edges, dtype=torch.long).t().contiguous()
        edge_attr = torch.tensor(edge_attrs, dtype=torch.long)
    else:
        edge_index = torch.tensor([[0], [0]], dtype=torch.long)
        vss_idx = stoi.get('VSS', 0)
        edge_attr = torch.tensor([vss_idx], dtype=torch.long)
    
    batch = torch.zeros(x.size(0), dtype=torch.long)
    
    return x, edge_index, edge_attr, batch


def classify_circuit(circuit_sequence):
    """Classify a circuit sequence"""
    x, edge_index, edge_attr, batch = create_graph_data(circuit_sequence)
    
    x = x.to(device)
    edge_index = edge_index.to(device)
    edge_attr = edge_attr.to(device)
    batch = batch.to(device)
    
    with torch.no_grad():
        predictions, probs = model.predict(x, edge_index, edge_attr, batch)
    
    predicted_idx = predictions[0].item()
    predicted_class = idx_to_label[predicted_idx]
    
    prob_dict = {idx_to_label[i]: probs[0][i].item() for i in range(len(circuit_types))}
    
    return predicted_class, prob_dict


def parse_inference_file(file_path):
    """Parse inference file to extract token sequence.
    
    Args:
        file_path: Path to inference text file
        
    Returns:
        List of tokens
    """
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Parse the circuit sequence
    tokens = content.strip().split('->')
    tokens = [t.strip() for t in tokens if t.strip()]
    
    return tokens


def classify_all_inference_folders():
    """Classify all circuits in inference folders and compute accuracy.
    
    Processes all Inference_CIRCUIT_* directories, classifies each circuit,
    and computes the percentage of correctly classified circuits per type.
    """
    
    print("\n" + "="*80)
    print("GAT CIRCUIT CLASSIFICATION - ALL FOLDERS")
    print("="*80)
    
    # Find all inference folders (Inference_*)
    inference_folders = []
    for item in os.listdir('.'):
        if os.path.isdir(item) and item.startswith('Inference_'):
            inference_folders.append(item)
    
    inference_folders.sort()
    print(f"\nFound {len(inference_folders)} inference folders\n")
    
    # Results storage
    results = {}
    
    # Process each folder
    for folder in inference_folders:
        # Extract circuit type from folder name
        # Handle patterns: Inference_CIRCUIT_X, Inference_finetuned_CIRCUIT_X, Inference_original
        folder_name = folder.replace('Inference_', '')
        
        # Find the actual circuit type (CIRCUIT_*)
        circuit_type = None
        for ct in circuit_types:
            if ct in folder_name:
                circuit_type = ct
                break
        
        # Skip folders without recognizable circuit type
        if circuit_type is None:
            print(f"Skipping {folder_name} (no circuit type found)")
            continue
        
        print(f"Processing {folder_name}...", end=' ', flush=True)
        
        files = [f for f in os.listdir(folder) if f.endswith('.txt')]
        
        right_count = 0
        total_count = 0
        prediction_counts = Counter()
        
        for filename in files:
            file_path = os.path.join(folder, filename)
            
            try:
                tokens = parse_inference_file(file_path)
                predicted_class, probs = classify_circuit(tokens)
                
                prediction_counts[predicted_class] += 1
                
                # Check if prediction matches the expected circuit type
                if predicted_class == circuit_type:
                    right_count += 1
                total_count += 1
                
            except Exception as e:
                print(f"\n  Error processing {filename}: {e}")
                continue
        
        right_percentage = (right_count / total_count * 100) if total_count > 0 else 0
        results[folder_name] = {
            'right': right_count,
            'total': total_count,
            'percentage': right_percentage,
            'predictions': prediction_counts,
            'circuit_type': circuit_type
        }
        
        print(f"{right_percentage:.2f}% right ({right_count}/{total_count})")
    
    # Create Analysis_Results directory if it doesn't exist
    os.makedirs('Analysis_Results', exist_ok=True)
    
    # Save detailed results
    output_file = 'Analysis_Results/gat_classification_summary.txt'
    
    with open(output_file, 'w') as f:
        f.write("="*80 + "\n")
        f.write("GAT CIRCUIT CLASSIFICATION SUMMARY\n")
        f.write("="*80 + "\n\n")
        
        f.write(f"{'Circuit Type':<35} {'Right %':<12} {'Right/Total':<15}\n")
        f.write("-"*80 + "\n")
        
        overall_right = 0
        overall_total = 0
        
        for folder_name in sorted(results.keys()):
            right = results[folder_name]['right']
            total = results[folder_name]['total']
            percentage = results[folder_name]['percentage']
            
            f.write(f"{folder_name:<35} {percentage:>6.2f}%      {right}/{total}\n")
            
            overall_right += right
            overall_total += total
        
        f.write("-"*80 + "\n")
        
        overall_percentage = (overall_right / overall_total * 100) if overall_total > 0 else 0
        f.write(f"{'OVERALL':<35} {overall_percentage:>6.2f}%      {overall_right}/{overall_total}\n")
        
        f.write("\n" + "="*80 + "\n")
        f.write("DETAILED PREDICTION DISTRIBUTION\n")
        f.write("="*80 + "\n\n")
        
        for folder_name in sorted(results.keys()):
            circuit_type = results[folder_name]['circuit_type']
            f.write(f"\n{folder_name}:\n")
            f.write("-" * 40 + "\n")
            
            pred_counts = results[folder_name]['predictions']
            total = results[folder_name]['total']
            
            for pred_class, count in pred_counts.most_common():
                pred_short = pred_class.replace('CIRCUIT_', '')
                pred_pct = count / total * 100
                marker = "*" if pred_class == circuit_type else " "
                f.write(f"  {marker} {pred_short:<30} {count:>4} ({pred_pct:>5.2f}%)\n")
        
        f.write("\n" + "="*80 + "\n")
        f.write(f"Total Circuits Classified: {overall_total}\n")
        f.write(f"Correctly Classified: {overall_right}\n")
        f.write(f"Overall Accuracy: {overall_percentage:.2f}%\n")
    
    # Print summary
    print("\n" + "="*80)
    print("CLASSIFICATION COMPLETE!")
    print("="*80)
    print(f"\nOverall Accuracy: {overall_percentage:.2f}% ({overall_right}/{overall_total})")
    print(f"\nResults saved to: {output_file}")
    print("="*80 + "\n")


if __name__ == "__main__":
    classify_all_inference_folders()
