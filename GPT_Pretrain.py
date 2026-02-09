#!/usr/bin/env python3
"""
GPT-based Circuit Pretraining

This script trains a GPT model to learn analog circuit topologies represented as
sequence data. The model learns to predict circuit tokens (devices, connections,
and circuit types) in an autoregressive manner.
"""

import os
import csv
import numpy as np
import torch
import torch.nn.functional as F
from torch import nn
from Models.GPT import GPTLanguageModel
import time
from datetime import datetime, timedelta

# =========================
# Hyperparameters
# =========================
batch_size   = 64
block_size   = 1024
max_iters    = 100_000
eval_interval= 500
eval_iters   = 200
learning_rate= 3e-4
n_embd       = 384
n_head       = 6
n_layer      = 6
dropout      = 0.2
filename     = 'Pretrain'
Trainingdata = 'Training_renamed.npy'
Validationdata = 'Validation_renamed.npy'
seed         = 1337

torch.manual_seed(seed)

# =========================
# Vocabulary Definition
# =========================
# Define all tokens used to represent analog circuit topologies.
# The vocabulary includes device nodes, edge types, power rails,
# circuit type identifiers, and special tokens.

print("Building vocabulary...")

vocab_tokens = []

# 1. Edge types - represent connections between circuit nodes
# MOSFET edges (M_ prefix) - various pin combinations
vocab_tokens.extend([
    'M_B', 'M_D', 'M_G', 'M_S',  # Single pin
    'M_BD', 'M_BG', 'M_BS', 'M_DG', 'M_DS', 'M_GS',  # Two pins
    'M_BDG', 'M_BDS', 'M_BGS', 'M_DGS',  # Three pins
    'M_BDGS'  # Four pins
])
# BJT edges (B_ prefix) - Base, Collector, Emitter combinations
vocab_tokens.extend([
    'B_B', 'B_C', 'B_E',  # Single pin
    'B_BC', 'B_BE', 'B_CE',  # Two pins
    'B_BCE'  # Three pins
])
# Passive device edges - Resistor, Capacitor, Inductor connections
vocab_tokens.extend(['R_C', 'C_C', 'L_C'])
# Diode edges (D_ prefix) - Positive/Negative terminal combinations
vocab_tokens.extend(['D_P', 'D_N', 'D_NP', 'D_PN'])

# 2. Power rails - Supply voltages
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

# 4. Device nodes - Circuit components
# MOSFETs: NMOS (NM1-NM35), PMOS (PM1-PM35)
for i in range(1, 36):
    vocab_tokens.append(f'NM{i}')
for i in range(1, 36):
    vocab_tokens.append(f'PM{i}')
# BJTs: NPN (NPN1-NPN27), PNP (PNP1-PNP27)
for i in range(1, 28):
    vocab_tokens.append(f'NPN{i}')
for i in range(1, 28):
    vocab_tokens.append(f'PNP{i}')
# Resistors (R1-R28)
for i in range(1, 29):
    vocab_tokens.append(f'R{i}')
# Capacitors (C1-C16)
for i in range(1, 17):
    vocab_tokens.append(f'C{i}')
# Inductors (L1-L24)
for i in range(1, 25):
    vocab_tokens.append(f'L{i}')
# Diodes (DIO1-DIO8)
for i in range(1, 9):
    vocab_tokens.append(f'DIO{i}')

# 5. Net nodes - Internal circuit connections (NET1-NET50)
for i in range(1, 51):
    vocab_tokens.append(f'NET{i}')

# 6. Port nodes - External interfaces and control signals
# Voltage/Current inputs and outputs
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
# Control and reference signals
for i in range(1, 22):
    vocab_tokens.append(f'VCONT{i}')
for i in range(1, 4):
    vocab_tokens.extend([f'VCM{i}', f'VREF{i}', f'IREF{i}', f'VRF{i}', f'VIF{i}'])
# RF/Mixer/PLL specific signals
for i in range(1, 6):
    vocab_tokens.extend([f'VLO{i}', f'VBB{i}'])

# 7. Special tokens - Sequence control
vocab_tokens.append('TRUNCATE')

# Build token-to-index and index-to-token mappings
devices = vocab_tokens
stoi = {d: i for i, d in enumerate(devices)}  # string to index
itos = {i: d for i, d in enumerate(devices)}  # index to string
vocab_size = len(devices)

print(f"\n{'='*60}")
print(f"Vocabulary Summary: {vocab_size} total tokens")
print(f"{'='*60}")
print(f"Device Tokens:")
print(f"  - MOSFETs: 70 (35 NMOS + 35 PMOS)")
print(f"  - BJTs: 54 (27 NPN + 27 PNP)")
print(f"  - Passives: 68 (28 Resistors + 16 Capacitors + 24 Inductors)")
print(f"  - Diodes: 8")
print(f"Net Tokens:")
print(f"  - Internal nets: 49 (NET1-NET50)")
print(f"  - Power rails: 2 (VDD, VSS)")
print(f"Port Tokens:")
print(f"  - Input/Output ports: ~67")
print(f"  - Bias and control signals: ~45")
print(f"Edge Types:")
print(f"  - MOSFET edges: 15 (single/compound pin combinations)")
print(f"  - BJT edges: 7 (single/compound pin combinations)")
print(f"  - Passive edges: 3 (R_C, C_C, L_C)")
print(f"  - Diode edges: 4 (single/compound pin combinations)")
print(f"Circuit Type Tokens: 15 functional categories")
print(f"Special Tokens: 1 (TRUNCATE)")
print(f"{'='*60}\n")

def encode(seq):
    """Convert sequence of tokens to integer indices.
    
    Args:
        seq: List of token strings
    Returns:
        List of integer indices
    Raises:
        ValueError: If unknown token encountered
    """
    result = []
    for s in seq:
        token_str = str(s)
        if token_str not in stoi:
            raise ValueError(f"Unknown token: '{token_str}' not in vocabulary")
        result.append(stoi[token_str])
    return result

def decode(idxs):
    """Convert sequence of indices back to token string.
    
    Args:
        idxs: List of integer indices
    Returns:
        String with tokens joined by '->'
    """
    return '->'.join([itos[i] for i in idxs]) + '->'

# =========================
# Device Configuration
# =========================
# Configure GPU/CPU usage and enable multi-GPU training if available
if torch.cuda.is_available():
    visible = torch.cuda.device_count()
    print(f"Visible GPUs: {visible}")
else:
    visible = 0
    print("No CUDA detected, using CPU.")

use_multi_gpu = torch.cuda.is_available() and visible >= 2
primary_index = 0
if torch.cuda.is_available():
    torch.cuda.set_device(primary_index)
device = f"cuda:{primary_index}" if torch.cuda.is_available() else "cpu"
print(f"Primary device: {device}")

# =========================
# Data Loading and Encoding
# =========================

def to_index_tensor(arr):
    """Convert numpy array of token sequences to PyTorch tensor of indices.
    
    Handles both object arrays (containing token strings) and integer arrays.
    Supports 1D and 2D array structures.
    
    Args:
        arr: Numpy array of token sequences or integer indices
    Returns:
        torch.LongTensor of token indices
    """
    if arr.dtype == object:
        # Handle 2D array of sequences (each element is a sequence)
        if arr.ndim == 2:
            # Each row is already a sequence
            encoded_seqs = []
            for seq in arr:
                encoded = encode(seq)
                encoded_seqs.append(encoded)
            return torch.tensor(encoded_seqs, dtype=torch.long)
        else:
            # Flatten all sequences then encode then reconstruct
            all_tokens = []
            lengths = []
            for seq in arr:
                all_tokens.extend(seq)
                lengths.append(len(seq))
            encoded = encode(all_tokens)
            out = []
            start = 0
            for L in lengths:
                out.append(encoded[start:start+L])
                start += L
            return torch.tensor(out, dtype=torch.long)
    elif np.issubdtype(arr.dtype, np.integer):
        return torch.tensor(arr, dtype=torch.long)
    else:
        # assume array of strings/tokens with uniform shape
        flat = [encode([str(s)])[0] for s in arr.flatten()]
        return torch.tensor(flat, dtype=torch.long).view(arr.shape)

print("Loading training data...")
train_np = np.load(Trainingdata, allow_pickle=True)
print("Training npy shape:", train_np.shape, "dtype:", train_np.dtype)
train_data = to_index_tensor(train_np)

print("Loading validation data...")
val_np = np.load(Validationdata, allow_pickle=True)
print("Validation npy shape:", val_np.shape, "dtype:", val_np.dtype)
val_data = to_index_tensor(val_np)

print("Train tensor shape:", tuple(train_data.shape))
print("Val   tensor shape:", tuple(val_data.shape))

# Validate data format: expect (N, L) fixed-length sequences
assert train_data.dim()==2 and val_data.dim()==2, "Expected (N, L) tensors"
assert train_data.size(1) == val_data.size(1), "Train/val sequence length mismatch"
assert train_data.size(1) >= 2, "Sequence length must be >= 2"

# Verify all token indices are valid
max_idx = max(train_data.max().item(), val_data.max().item())
min_idx = min(train_data.min().item(), val_data.min().item())
print(f"Token index range: [{min_idx}, {max_idx}], vocab_size: {vocab_size}")
assert max_idx < vocab_size, f"Found token index {max_idx} >= vocab_size {vocab_size}"
assert min_idx >= 0, f"Found negative token index {min_idx}"

# Count TRUNCATE token occurrences
truncate_idx = stoi['TRUNCATE']
truncate_count = (train_data == truncate_idx).sum().item() + (val_data == truncate_idx).sum().item()
print(f"TRUNCATE token (idx={truncate_idx}) appears {truncate_count} times")

# =========================
# Batch Generation
# =========================

def get_batch(split):
    """Generate a batch of training/validation data.
    
    Samples random sequences and creates input-target pairs by shifting by 1.
    For autoregressive training: input = sequence[:-1], target = sequence[1:]
    
    Args:
        split: 'train' or 'val'
    Returns:
        Tuple of (input_batch, target_batch) tensors on device
    """
    data = train_data if split == 'train' else val_data
    N, L = data.shape
    ix = torch.randint(N, (batch_size,))
    x = torch.stack([data[i, :-1] for i in ix])
    y = torch.stack([data[i, 1: ] for i in ix])
    return x.to(device), y.to(device)

# =========================
# Helper Functions
# =========================

def flatten_bt(logits, targets):
    """Flatten batch and time dimensions for loss computation.
    
    Converts 3D tensors (B, T, C) to 2D (B*T, C) format required by cross-entropy loss.
    
    Args:
        logits: Model predictions, shape (B,T,C) or (B*T,C)
        targets: Target indices, shape (B,T) or (B*T,)
    Returns:
        Tuple of (flattened_logits, flattened_targets)
    """
    if logits.dim() == 3:  # (B,T,C)
        B, T, C = logits.shape
        return logits.reshape(B*T, C), targets.reshape(B*T)
    elif logits.dim() == 2:  # (B*T,C)
        return logits, targets.view(-1)
    else:
        raise ValueError(f"Unexpected logits shape: {tuple(logits.shape)}")

@torch.no_grad()
def estimate_loss():
    """Evaluate model on train and validation sets.
    
    Computes two types of losses:
    1. Standard loss (including TRUNCATE tokens)
    2. Filtered loss (excluding TRUNCATE tokens for cleaner metrics)
    
    Returns:
        Dictionary with train/val losses and filtered losses
    """
    out = {}
    model.eval()
    for split in ['train', 'val']:
        ls = torch.zeros(eval_iters, device=device)
        fls = torch.zeros(eval_iters, device=device)
        for k in range(eval_iters):
            X, Y = get_batch(split)
            logits, loss = model(X, Y)
            if torch.is_tensor(loss) and loss.numel() > 1:
                loss = loss.mean()
            ls[k] = loss

            logits2, tgt1d = flatten_bt(logits, Y)
            mask = (tgt1d != stoi["TRUNCATE"])
            if mask.any():
                f_loss = F.cross_entropy(logits2[mask], tgt1d[mask])
                fls[k] = f_loss
            else:
                fls[k] = torch.nan
        out[split] = torch.nanmean(ls).detach().cpu()
        out[f'{split}_filtered_loss'] = torch.nanmean(fls).detach().cpu()
    model.train()
    return out

# =========================
# Model Initialization
# =========================
# Create GPT model and wrap with DataParallel for multi-GPU training
model = GPTLanguageModel(vocab_size, n_embd, block_size, n_head, n_layer, dropout)

if use_multi_gpu:
    print(f"Using {visible} GPUs via DataParallel (all visible).")
    model = nn.DataParallel(model)  # use all visible GPUs
else:
    print(f"Using single device: {device}")

model = model.to(device)
param_src = model.module if hasattr(model, "module") else model
n_params = sum(p.numel() for p in param_src.parameters())/1e6
print(f"{n_params:.1f}M parameters")

optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate)
best_val = float('inf')

# =========================
# Training Loop
# =========================
# Main training loop with periodic evaluation and checkpointing
print("\n" + "="*80)
print("Starting training...")
print(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("="*80)
training_start_time = time.time()

with open(filename+'.csv', 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['Step', 'TrainLoss', 'TrainFilteredLoss', 'ValLoss', 'ValFilteredLoss', 'ElapsedTime'])

    for it in range(max_iters):
        # Periodic memory cleanup
        if it % 1000 == 0 and torch.cuda.is_available():
            torch.cuda.empty_cache()

        # Periodic evaluation and checkpointing
        if it % eval_interval == 0 or it == max_iters - 1:
            metrics = estimate_loss()
            tr  = float(metrics['train'])
            trf = float(metrics['train_filtered_loss'])
            vl  = float(metrics['val'])
            vlf = float(metrics['val_filtered_loss'])
            
            elapsed_time = time.time() - training_start_time
            elapsed_str = str(timedelta(seconds=int(elapsed_time)))
            print(f"step {it}: train {tr:.4f}/{trf:.4f}, val {vl:.4f}/{vlf:.4f} | Time: {elapsed_str}")
            writer.writerow([it, tr, trf, vl, vlf, elapsed_str])

            # Save checkpoint if validation loss improved
            if vl < best_val:
                ckpt = filename + '.pth'
                torch.save((model.module if hasattr(model,'module') else model).state_dict(), ckpt)
                best_val = vl

        # Training step
        xb, yb = get_batch('train')
        logits, loss = model(xb, yb)
        if torch.is_tensor(loss) and loss.numel() > 1:
            loss = loss.mean()
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        optimizer.step()

total_training_time = time.time() - training_start_time
print("\n" + "="*80)
print("Training completed!")
print(f"Total training time: {timedelta(seconds=int(total_training_time))}")
print(f"End time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("="*80)
