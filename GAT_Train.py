#!/usr/bin/env python3
"""
GAT Classifier Training for Circuit Type Classification

This module trains a Graph Attention Network (GAT) classifier to predict the 
functional type of analog circuits from their bipartite graph representations.
The classifier achieves 99.91% accuracy on circuit type classification.

Model Architecture:
    - 3 GAT layers with 4, 4, and 1 attention heads
    - Embedding dimension: 64
    - Hidden dimension: 128
    - Dropout: 0.3
    - Batch normalization after each GAT layer
    - Two-layer MLP classifier with mean+max pooling

Training Configuration:
    - 100 epochs with Adam optimizer
    - Learning rate: 5×10⁻⁴ with cosine annealing
    - Weight decay: 10⁻³
    - Label smoothing: 0.1
    - Gradient clipping: max norm 1.0

Usage:
    python GAT_Train.py
"""

import torch
import torch.nn as nn
from torch_geometric.data import Data, DataLoader
import numpy as np
import csv
import time
from datetime import datetime, timedelta
from Models.GAT import GATClassifier

# Hyperparameters
batch_size = 512 
learning_rate = 5e-4 
num_epochs = 100
label_smoothing = 0.1 
device = 'cuda' if torch.cuda.is_available() else 'cpu'
print(f"Using device: {device}")

if torch.cuda.is_available():
    print(f"GPU: {torch.cuda.get_device_name(0)}")
    print(f"VRAM: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")

# Model parameters
hidden_dim = 128
num_heads = 4
num_layers = 3
dropout = 0.3

# File paths
train_file = 'Training_renamed.npy'
val_file = 'Validation_renamed.npy'
model_save_path = 'GAT_Classifier.pth'
log_file = 'GAT_Train.csv'

# Circuit type mapping
circuit_types = [
    "CIRCUIT_Opamp", "CIRCUIT_Mirror", "CIRCUIT_Comparator",
    "CIRCUIT_Mixer", "CIRCUIT_LDO", "CIRCUIT_Oscillator",
    "CIRCUIT_Filter", "CIRCUIT_Bandgap_Ref", "CIRCUIT_Power_Amp",
    "CIRCUIT_Voltage_Regulator", "CIRCUIT_Power_converter",
    "CIRCUIT_PLL", "CIRCUIT_Switched_Cap", "CIRCUIT_ADC_DAC",
    "CIRCUIT_General"
]
num_classes = len(circuit_types)
label_to_idx = {label: idx for idx, label in enumerate(circuit_types)}
idx_to_label = {idx: label for idx, label in enumerate(circuit_types)}

# Build vocabulary (same as GPT_Pretrain.py)
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

# 4. Device nodes (transistors and passives)
# MOSFETs: NM1-NM35, PM1-PM35
for i in range(1, 36):
    vocab_tokens.append(f'NM{i}')
for i in range(1, 36):
    vocab_tokens.append(f'PM{i}')
# BJTs: NPN1-NPN27, PNP1-PNP27
for i in range(1, 28):
    vocab_tokens.append(f'NPN{i}')
for i in range(1, 28):
    vocab_tokens.append(f'PNP{i}')
# Resistors: R1-R28
for i in range(1, 29):
    vocab_tokens.append(f'R{i}')
# Capacitors: C1-C16
for i in range(1, 17):
    vocab_tokens.append(f'C{i}')
# Inductors: L1-L24
for i in range(1, 25):
    vocab_tokens.append(f'L{i}')
# Diodes: DIO1-DIO8
for i in range(1, 9):
    vocab_tokens.append(f'DIO{i}')

# 5. Net nodes: NET1-NET50
for i in range(1, 51):
    vocab_tokens.append(f'NET{i}')

# 6. Port nodes (inputs/outputs/biases/controls)
# Voltage/Current I/O
for i in range(1, 21):
    vocab_tokens.append(f'VIN{i}')
vocab_tokens.append('VOUT')  # Single VOUT token
for i in range(1, 8):
    vocab_tokens.append(f'VOUT{i}')
for i in range(1, 4):
    vocab_tokens.append(f'IIN{i}')
for i in range(1, 6):
    vocab_tokens.append(f'IOUT{i}')
# Bias voltages/currents
for i in range(1, 12):
    vocab_tokens.append(f'VB{i}')
for i in range(1, 8):
    vocab_tokens.append(f'IB{i}')
# Control/reference signals
for i in range(1, 22):
    vocab_tokens.append(f'VCONT{i}')
for i in range(1, 4):
    vocab_tokens.extend([f'VCM{i}', f'VREF{i}', f'IREF{i}', f'VRF{i}', f'VIF{i}'])
# RF/mixer/PLL specific
for i in range(1, 6):
    vocab_tokens.extend([f'VLO{i}', f'VBB{i}'])

# 7. Special tokens
vocab_tokens.append('TRUNCATE')

# Build mappings
devices = vocab_tokens
stoi = {d: i for i, d in enumerate(devices)}
itos = {i: d for i, d in enumerate(devices)}
vocab_size = len(devices)

print(f"Vocabulary size: {vocab_size} tokens")
print(f"Number of circuit types: {num_classes}")


def sequence_to_graph(seq):
    """Convert circuit sequence to graph representation.
    
    Sequence format: CIRCUIT_TYPE -> node -> edge -> node -> edge -> ... -> TRUNCATE
    where nodes are devices/nets and edges are connection types.
    
    Args:
        seq: Circuit sequence array
    
    Returns:
        Tuple of (node_indices, edges, edge_attrs) where:
        - node_indices: List of unique node token indices (devices/nets only)
        - edges: List of (src_idx, dst_idx) tuples connecting nodes
        - edge_attrs: List of edge type indices corresponding to each edge
    """
    # Get first token to check for CIRCUIT_ prefix
    first_token_str = str(seq[0])
    
    # Remove CIRCUIT_ token if present
    start_idx = 1 if first_token_str.startswith('CIRCUIT_') else 0
    
    # Edge type tokens (these are NOT graph nodes, only connection info)
    # MOSFET edges (M_ prefix)
    edge_types = {'M_B', 'M_D', 'M_G', 'M_S', 'M_BD', 'M_BG', 'M_BS', 'M_DG', 'M_DS', 'M_GS',
                  'M_BDG', 'M_BDS', 'M_BGS', 'M_DGS', 'M_BDGS',
                  # BJT edges (B_ prefix)
                  'B_B', 'B_C', 'B_E', 'B_BC', 'B_BE', 'B_CE', 'B_BCE',
                  # Passive edges
                  'R_C', 'C_C', 'L_C',
                  # Diode edges (D_ prefix)
                  'D_P', 'D_N', 'D_NP', 'D_PN'}
    
    # Extract nodes (skip edge types and TRUNCATE)
    nodes_set = set()
    seq_len = len(seq)
    
    for i in range(start_idx, seq_len):
        token_str = str(seq[i])
        if token_str == 'TRUNCATE':
            break
        # Only add non-edge tokens as graph nodes
        if token_str not in edge_types:
            token_idx = stoi.get(token_str, stoi.get('VSS', 0))
            nodes_set.add(token_idx)
    
    # Create node list and mapping
    node_indices = sorted(list(nodes_set))
    node_to_graph_idx = {token_idx: graph_idx for graph_idx, token_idx in enumerate(node_indices)}
    
    # Build edges: node -> edge -> node pattern
    # i=0: node, i=1: edge, i=2: node, i=3: edge, ...
    edges = []
    edge_attrs = []  # Store edge type indices
    
    for i in range(start_idx, seq_len - 2, 2):  # Step by 2 to get node positions
        token_str1 = str(seq[i])      # First node
        edge_str = str(seq[i + 1])    # Edge type
        token_str2 = str(seq[i + 2])  # Second node
        
        if token_str1 == 'TRUNCATE' or token_str2 == 'TRUNCATE':
            break
        
        # Skip if either is an edge type (shouldn't happen but safety check)
        if token_str1 in edge_types or token_str2 in edge_types:
            continue
        
        token_idx1 = stoi.get(token_str1, stoi.get('VSS', 0))
        token_idx2 = stoi.get(token_str2, stoi.get('VSS', 0))
        edge_type_idx = stoi.get(edge_str, stoi.get('VSS', 0))
        
        if token_idx1 in node_to_graph_idx and token_idx2 in node_to_graph_idx:
            graph_idx1 = node_to_graph_idx[token_idx1]
            graph_idx2 = node_to_graph_idx[token_idx2]
            
            # Add forward edge
            edges.append((graph_idx1, graph_idx2))
            edge_attrs.append(edge_type_idx)
            
            # Add reverse edge for undirected graph
            edges.append((graph_idx2, graph_idx1))
            edge_attrs.append(edge_type_idx)  # Same edge type for reverse
    
    return node_indices, edges, edge_attrs


def create_graph_data(seq, label):
    """Create PyTorch Geometric Data object from sequence.
    
    Uses token indices directly (not one-hot encoding) to save memory.
    Includes edge attributes for edge types.
    
    Args:
        seq: Circuit sequence array
        label: Circuit type label index
        
    Returns:
        PyTorch Geometric Data object with node features, edges, and label
    """
    node_indices, edges, edge_attrs = sequence_to_graph(seq)
    
    if len(node_indices) == 0:
        # Empty graph, create dummy with VSS token
        vss_idx = stoi.get('VSS', 0)
        node_indices = [vss_idx]
        edges = []
        edge_attrs = [vss_idx]
    
    # Node features: just token indices (will be embedded in model)
    # This saves MASSIVE memory: 1020 floats → 1 int per node
    x = torch.tensor(node_indices, dtype=torch.long)
    
    # Edge index and edge attributes
    if len(edges) > 0:
        edge_index = torch.tensor(edges, dtype=torch.long).t().contiguous()
        edge_attr = torch.tensor(edge_attrs, dtype=torch.long)
    else:
        # No edges, create self-loop
        edge_index = torch.tensor([[0], [0]], dtype=torch.long)
        vss_idx = stoi.get('VSS', 0)
        edge_attr = torch.tensor([vss_idx], dtype=torch.long)
    
    # Create Data object with edge attributes
    data = Data(x=x, edge_index=edge_index, edge_attr=edge_attr, y=torch.tensor([label], dtype=torch.long))
    
    return data


# Load and process datasets
print(f"\nLoading training data from {train_file}...")
train_data_raw = np.load(train_file, allow_pickle=True)
print(f"Loaded {len(train_data_raw)} training sequences")

print(f"Loading validation data from {val_file}...")
val_data_raw = np.load(val_file, allow_pickle=True)
print(f"Loaded {len(val_data_raw)} validation sequences")

print("\nConverting sequences to graphs...")
train_graphs = []
for idx, seq in enumerate(train_data_raw):
    if idx % 10000 == 0 and idx > 0:
        print(f"  Training: {idx}/{len(train_data_raw)}")
    
    # Extract label from first token (already string in .npy)
    first_token_str = str(seq[0])
    
    if first_token_str.startswith('CIRCUIT_'):
        label = label_to_idx.get(first_token_str, label_to_idx["CIRCUIT_General"])
    else:
        label = label_to_idx["CIRCUIT_General"]
    
    graph = create_graph_data(seq, label)
    train_graphs.append(graph)

val_graphs = []
for idx, seq in enumerate(val_data_raw):
    if idx % 5000 == 0 and idx > 0:
        print(f"  Validation: {idx}/{len(val_data_raw)}")
    
    # Extract label from first token (already string in .npy)
    first_token_str = str(seq[0])
    
    if first_token_str.startswith('CIRCUIT_'):
        label = label_to_idx.get(first_token_str, label_to_idx["CIRCUIT_General"])
    else:
        label = label_to_idx["CIRCUIT_General"]
    
    graph = create_graph_data(seq, label)
    val_graphs.append(graph)

print(f"Created {len(train_graphs)} training graphs and {len(val_graphs)} validation graphs")

# Create data loaders
train_loader = DataLoader(train_graphs, batch_size=batch_size, shuffle=True, num_workers=0)
val_loader = DataLoader(val_graphs, batch_size=batch_size, shuffle=False, num_workers=0)

# Create model
embedding_dim = 64  # Token embedding dimension (much smaller than one-hot)
model = GATClassifier(
    vocab_size=vocab_size,
    num_classes=num_classes,
    embedding_dim=embedding_dim,
    hidden_dim=hidden_dim,
    num_heads=num_heads,
    num_layers=num_layers,
    dropout=dropout
).to(device)

# Initialize embedding layers for better training stability
nn.init.xavier_uniform_(model.node_embedding.weight)
nn.init.xavier_uniform_(model.edge_embedding.weight)

num_params = sum(p.numel() for p in model.parameters())
print(f"\nModel parameters: {num_params/1e6:.2f}M")

# Loss and optimizer
criterion = nn.CrossEntropyLoss(label_smoothing=label_smoothing)
optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate, weight_decay=1e-3)  # Increased from 5e-4
scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=num_epochs)

# Training function
def train_epoch():
    """Train for one epoch.
    
    Returns:
        Tuple of (average_loss, accuracy)
    """
    model.train()
    total_loss = 0
    correct = 0
    total = 0
    
    for batch in train_loader:
        batch = batch.to(device)
        
        optimizer.zero_grad()
        outputs = model(batch.x, batch.edge_index, batch.edge_attr, batch.batch)
        
        # Ensure batch.y has correct shape [batch_size]
        labels = batch.y.squeeze() if batch.y.dim() > 1 else batch.y
        
        loss = criterion(outputs, labels)
        loss.backward()
        
        # Gradient clipping for training stability
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
        
        optimizer.step()
        
        total_loss += loss.item()
        _, predicted = outputs.max(1)
        total += labels.size(0)
        correct += predicted.eq(labels).sum().item()
    
    return total_loss / len(train_loader), 100. * correct / total

# Validation function
def validate():
    """Validate on validation set.
    
    Returns:
        Tuple of (average_loss, accuracy)
    """
    model.eval()
    total_loss = 0
    correct = 0
    total = 0
    
    with torch.no_grad():
        for batch in val_loader:
            batch = batch.to(device)
            outputs = model(batch.x, batch.edge_index, batch.edge_attr, batch.batch)
            
            # Ensure batch.y has correct shape [batch_size]
            labels = batch.y.squeeze() if batch.y.dim() > 1 else batch.y
            
            loss = criterion(outputs, labels)
            
            total_loss += loss.item()
            _, predicted = outputs.max(1)
            total += labels.size(0)
            correct += predicted.eq(labels).sum().item()
    
    return total_loss / len(val_loader), 100. * correct / total

# Training loop
print("\n" + "="*70)
print("GAT CLASSIFIER TRAINING")
print("="*70)
print(f"Batch size: {batch_size}")
print(f"Learning rate: {learning_rate}")
print(f"Dropout: {dropout}")
print(f"Weight decay: 1e-3")
print(f"Label smoothing: {label_smoothing}")
print(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("="*70)

best_val_acc = 0
training_start_time = time.time()

with open(log_file, 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['Epoch', 'Train_Loss', 'Train_Acc', 'Val_Loss', 'Val_Acc', 'LR', 'Best_Val_Acc', 'EpochTime', 'TotalTime'])
    
    for epoch in range(num_epochs):
        epoch_start_time = time.time()
        
        train_loss, train_acc = train_epoch()
        val_loss, val_acc = validate()
        current_lr = optimizer.param_groups[0]['lr']
        
        epoch_time = time.time() - epoch_start_time
        total_time = time.time() - training_start_time
        epoch_time_str = str(timedelta(seconds=int(epoch_time)))
        total_time_str = str(timedelta(seconds=int(total_time)))
        
        # Save best model
        is_best = False
        if val_acc > best_val_acc:
            best_val_acc = val_acc
            is_best = True
            torch.save({
                'epoch': epoch + 1,
                'model_state_dict': model.state_dict(),
                'optimizer_state_dict': optimizer.state_dict(),
                'scheduler_state_dict': scheduler.state_dict(),
                'train_loss': train_loss,
                'train_acc': train_acc,
                'val_loss': val_loss,
                'val_acc': val_acc,
                'best_val_acc': best_val_acc,
                'label_to_idx': label_to_idx,
                'idx_to_label': idx_to_label,
                'vocab_size': vocab_size,
                'embedding_dim': embedding_dim,
                'hidden_dim': hidden_dim,
                'num_heads': num_heads,
                'num_layers': num_layers,
                'dropout': dropout,
            }, model_save_path)
        
        # Print progress
        print(f"\nEpoch {epoch+1}/{num_epochs}")
        print(f"  Train Loss: {train_loss:.6f}  |  Train Acc: {train_acc:.2f}%")
        print(f"  Val Loss: {val_loss:.6f}  |  Val Acc: {val_acc:.2f}%")
        print(f"  LR: {current_lr:.6e}  |  Best: {best_val_acc:.2f}%  |  Time: {epoch_time_str}")
        if is_best:
            print(f"  * Best model saved")
        
        # Save to CSV
        writer.writerow([epoch+1, f"{train_loss:.6f}", f"{train_acc:.2f}", 
                        f"{val_loss:.6f}", f"{val_acc:.2f}", f"{current_lr:.6e}", 
                        f"{best_val_acc:.2f}", epoch_time_str, total_time_str])
        f.flush()
        
        scheduler.step()

total_training_time = time.time() - training_start_time

print(f"\n{'='*70}")
print(f"Training completed")
print(f"Total time: {timedelta(seconds=int(total_training_time))}")
print(f"Best validation accuracy: {best_val_acc:.2f}%")
print(f"Model saved: {model_save_path}")
print(f"{'='*70}")
