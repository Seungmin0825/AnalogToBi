#!/usr/bin/env python3
import os
import csv
import numpy as np
import torch
import torch.nn.functional as F
from torch import nn
from Models.GPT import GPTLanguageModel

# =========================
# Hyperparameters
# =========================
batch_size   = 64
block_size   = 1024
max_iters    = 100_000
eval_interval= 500
eval_iters   = 500
learning_rate= 3e-4
n_embd       = 384
n_head       = 6
n_layer      = 6
dropout      = 0.2
filename     = 'Pretrain_multiGPU'
Trainingdata = 'Training.npy'
Validationdata = 'Validation.npy'
seed         = 1337

torch.manual_seed(seed)

# =========================
# Token space (devices/tokens)
# =========================
nm_np_bases = ["{}_D", "{}_G", "{}_S", "{}_B"]
npn_pnp_bases = ["{}_C", "{}_B", "{}_E"]
c_r_l_i_bases = ["{}_P", "{}_N"]
xor_bases = ["{}_A", "{}_B", "{}_VDD", "{}_VSS", "{}_Y"]
pfd_bases = ["{}_A", "{}_B", "{}_QA", "{}_QB", "{}_VDD", "{}_VSS"]
inverter_bases = ["{}_A", "{}_Q", "{}_VDD", "{}_VSS"]
transmission_gate_bases = ["{}_A", "{}_B", "{}_C", "{}_VDD", "{}_VSS"]

devices = []
for prefix in ["NM", "PM"]:
    for i in range(1, 35):
        devices.append(f"{prefix}{i}")
        for base in nm_np_bases:
            devices.append(base.format(f"{prefix}{i}"))

for prefix in ["NPN", "PNP"]:
    for i in range(1, 27):
        devices.append(f"{prefix}{i}")
        for base in npn_pnp_bases:
            devices.append(base.format(f"{prefix}{i}"))

for i in range(1, 28):
    devices.append(f"R{i}")
    for base in c_r_l_i_bases:
        devices.append(base.format(f"R{i}"))

for i in range(1, 16):
    devices.append(f"C{i}")
    for base in c_r_l_i_bases:
        devices.append(base.format(f"C{i}"))

for i in range(1, 24):
    devices.append(f"L{i}")
    for base in c_r_l_i_bases:
        devices.append(base.format(f"L{i}"))

for i in range(1, 8):
    devices.append(f"DIO{i}")
    for base in c_r_l_i_bases:
        devices.append(base.format(f"DIO{i}"))

for i in range(1, 2):
    devices.append(f"XOR{i}")
    for base in xor_bases:
        devices.append(base.format(f"XOR{i}"))

for i in range(1, 2):
    devices.append(f"PFD{i}")
    for base in pfd_bases:
        devices.append(base.format(f"PFD{i}"))

for i in range(1, 11):
    devices.append(f"INVERTER{i}")
    for base in inverter_bases:
        devices.append(base.format(f"INVERTER{i}"))

for i in range(1, 13):
    devices.append(f"TRANSMISSION_GATE{i}")
    for base in transmission_gate_bases:
        devices.append(base.format(f"TRANSMISSION_GATE{i}"))

for i in range(1, 11):
    devices.append(f"VIN{i}")
for i in range(1, 3):
    devices.append(f"IIN{i}")
for i in range(1, 7):
    devices.append(f"VOUT{i}")
for i in range(1, 5):
    devices.append(f"IOUT{i}")
for i in range(1, 11):
    devices.append(f"VB{i}")
for i in range(1, 7):
    devices.append(f"IB{i}")
for i in range(1, 21):
    devices.append(f"VCONT{i}")
for i in range(1, 9):
    devices.append(f"VCLK{i}")
for i in range(1, 3):
    devices.append(f"VCM{i}")
for i in range(1, 3):
    devices.append(f"VREF{i}")
for i in range(1, 3):
    devices.append(f"IREF{i}")
for i in range(1, 3):
    devices.append(f"VRF{i}")
for i in range(1, 5):
    devices.append(f"VLO{i}")
for i in range(1, 3):
    devices.append(f"VIF{i}")
for i in range(1, 5):
    devices.append(f"VBB{i}")
for i in range(1, 3):
    devices.append(f"LOGICA{i}")
for i in range(1, 3):
    devices.append(f"LOGICB{i}")
for i in range(1, 3):
    devices.append(f"LOGICD{i}")
for i in range(1, 3):
    devices.append(f"LOGICF{i}")
for i in range(1, 3):
    devices.append(f"LOGICG{i}")
for i in range(1, 3):
    devices.append(f"LOGICQ{i}")
for i in range(1, 2):
    devices.append(f"LOGICQA{i}")
for i in range(1, 2):
    devices.append(f"LOGICQB{i}")
for i in range(1, 3):
    devices.append(f"VLATCH{i}")
for i in range(1, 2):
    devices.append(f"VHOLD{i}")
for i in range(1, 3):
    devices.append(f"VTRACK{i}")

additional_entries = ["VDD", "VSS", "TRUNCATE"]
circuit_type_tokens = [
    "CIRCUIT_Opamp", "CIRCUIT_Comparator", "CIRCUIT_Oscillator",
    "CIRCUIT_Current_Mirror", "CIRCUIT_Differential_Amp", "CIRCUIT_LNA",
    "CIRCUIT_Mixer", "CIRCUIT_LDO", "CIRCUIT_Bandgap_Ref",
    "CIRCUIT_Single_Stage_Amp", "CIRCUIT_Power_Amp",
    "CIRCUIT_Voltage_Regulator", "CIRCUIT_Filter",
    "CIRCUIT_Switched_Cap", "CIRCUIT_General"
]
devices.extend(additional_entries)
devices.extend(circuit_type_tokens)

stoi = { d:i for i,d in enumerate(devices) }
itos = { i:d for i,d in enumerate(devices) }
vocab_size = len(devices)

print("Devices sample:", devices[:5], "...", devices[-10:])
print("Vocab size:", vocab_size)

encode = lambda seq: [stoi[s] for s in seq]
decode = lambda idxs: '->'.join([itos[i] for i in idxs]) + '->'

# =========================
# Device / Multi-GPU setup
# =========================
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
# Data loading & encoding
# =========================
def to_index_tensor(arr):
    """Convert np array (object/list of tokens, or already integer) into LongTensor."""
    if arr.dtype == object:
        # flatten all sequences then encode then reconstruct
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
        flat = [stoi[s] for s in arr.flatten()]
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

# Sanity: assume (N, L) fixed-length sequences for simple batching
assert train_data.dim()==2 and val_data.dim()==2, "Expected (N, L) tensors"
assert train_data.size(1) == val_data.size(1), "Train/val sequence length mismatch"
assert train_data.size(1) >= 2, "Sequence length must be >= 2"

# =========================
# Batching
# =========================
def get_batch(split):
    data = train_data if split == 'train' else val_data
    N, L = data.shape
    # Here we sample entire sequences and shift by 1; ensure fixed length
    ix = torch.randint(N, (batch_size,))
    x = torch.stack([data[i, :-1] for i in ix])
    y = torch.stack([data[i, 1: ] for i in ix])
    return x.to(device), y.to(device)

# =========================
# Helpers
# =========================
def flatten_bt(logits, targets):
    """
    Supports logits of shape (B,T,C) or (B*T, C).
    Returns logits_2d: (B*T,C), targets_1d: (B*T,)
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
# Model / DP wrapper
# =========================
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
# Training
# =========================
with open(filename+'.csv', 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['Step', 'TrainLoss', 'TrainFilteredLoss', 'ValLoss', 'ValFilteredLoss'])

    for it in range(max_iters):
        if it % 1000 == 0 and torch.cuda.is_available():
            torch.cuda.empty_cache()

        # eval
        if it % eval_interval == 0 or it == max_iters - 1:
            metrics = estimate_loss()
            tr  = float(metrics['train'])
            trf = float(metrics['train_filtered_loss'])
            vl  = float(metrics['val'])
            vlf = float(metrics['val_filtered_loss'])
            print(f"step {it}: train {tr:.4f}/{trf:.4f}, val {vl:.4f}/{vlf:.4f}")
            writer.writerow([it, tr, trf, vl, vlf])

            if vl < best_val:
                ckpt = filename + '.pth'
                torch.save((model.module if hasattr(model,'module') else model).state_dict(), ckpt)
                best_val = vl

        # batch
        xb, yb = get_batch('train')
        logits, loss = model(xb, yb)
        if torch.is_tensor(loss) and loss.numel() > 1:
            loss = loss.mean()
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        optimizer.step()
