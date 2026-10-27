#!/usr/bin/env python3
"""
GPT pretraining.

The released checkpoint was trained with the defaults: 100k iterations of
batch 64 on Training_renamed.npy, AdamW at 3e-4, seed 1337, and the checkpoint
kept at the lowest validation loss.

Usage:
    python TRAIN_GPT.py --tag AnalogToBi --gpu 0

Outputs:
    Pretrain_<tag>.pth   best-validation checkpoint
    Pretrain_<tag>.csv   training log
    Pretrain_<tag>.json  config needed to rebuild the model for inference
"""

import argparse
import csv
import json
import os
import random
import time
from datetime import datetime, timedelta

import numpy as np
import torch
import torch.nn.functional as F

from Models.GPT import GPTLanguageModel

# =========================
# Hyperparameters
# =========================
batch_size    = 64
block_size    = 1024
eval_interval = 500
eval_iters    = 200
learning_rate = 3e-4
n_embd        = 384
n_head        = 6
n_layer       = 6
dropout       = 0.2


def resolve_device(requested):
    """Pick a CUDA device, tolerating CUDA_VISIBLE_DEVICES remapping.

    Under `CUDA_VISIBLE_DEVICES=6` the process sees that GPU as index 0, so a
    literal --gpu 6 would be an invalid ordinal. Fall back to index 0 and say so
    rather than aborting a run that was launched correctly.
    """
    if not torch.cuda.is_available():
        print("No CUDA detected, using CPU.")
        return 'cpu'
    visible = os.environ.get('CUDA_VISIBLE_DEVICES')
    index = requested
    if index >= torch.cuda.device_count():
        print(f"GPU {requested} is not among the {torch.cuda.device_count()} visible "
              f"device(s) (CUDA_VISIBLE_DEVICES={visible}); using local index 0.")
        index = 0
    torch.cuda.set_device(index)
    print(f"Device: cuda:{index} ({torch.cuda.get_device_name(index)}), "
          f"CUDA_VISIBLE_DEVICES={visible}")
    return f'cuda:{index}'


def parse_args():
    """Command-line arguments."""
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--tag', required=True, help='run name; outputs go to Pretrain_<tag>.*')
    p.add_argument('--gpu', type=int, default=0)
    p.add_argument('--cpu', action='store_true',
                   help='train on the CPU even when a GPU is present')
    p.add_argument('--iters', type=int, default=100_000)
    p.add_argument('--seed', type=int, default=1337)
    p.add_argument('--train', default='Training_renamed.npy')
    p.add_argument('--val', default='Validation_renamed.npy')
    return p.parse_args()


args = parse_args()

random.seed(args.seed)
np.random.seed(args.seed)
torch.manual_seed(args.seed)
torch.cuda.manual_seed_all(args.seed)

filename = f'Pretrain_{args.tag}'

# =========================
# Vocabulary
# =========================
# Imported from CORE_Grammar, which re-exports CORE_Vocab, so that training and
# grammar-guided decoding index the same 397 tokens.
from CORE_Grammar import vocab_tokens, stoi, itos, vocab_size

TRUNCATE_IDX = stoi['TRUNCATE']
print(f"Vocabulary: {vocab_size} tokens, TRUNCATE = {TRUNCATE_IDX}")

# =========================
# Device
# =========================
if args.cpu:
    print('Device: cpu (--cpu)')
    device = 'cpu'
else:
    device = resolve_device(args.gpu)

# =========================
# Data
# =========================


def to_index_tensor(arr):
    """(N, L) object array of token strings -> (N, L) int16 tensor of indices.

    int16 rather than int64 because the whole training set stays resident:
    397 tokens fit comfortably, and 366M positions cost 733MB instead of 2.9GB.
    get_batch casts the 64 rows it actually uses.
    """
    if arr.dtype == object:
        lookup = np.vectorize(lambda t: stoi[str(t)], otypes=[np.int16])
        return torch.from_numpy(lookup(arr))
    if np.issubdtype(arr.dtype, np.integer):
        return torch.tensor(arr, dtype=torch.int16)
    raise ValueError(f"Unsupported dtype: {arr.dtype}")


print(f"Loading {args.train} ...")
train_data = to_index_tensor(np.load(args.train, allow_pickle=True))
print(f"Loading {args.val} ...")
val_data = to_index_tensor(np.load(args.val, allow_pickle=True))

assert train_data.dim() == 2 and val_data.dim() == 2, "Expected (N, L) tensors"
assert train_data.size(1) == val_data.size(1), "Train/val sequence length mismatch"
assert train_data.max().item() < vocab_size, "Token index outside the vocabulary"


# =========================
# Batching
# =========================


def get_batch(split):
    """Sample a batch of (input, target) pairs: whole rows, shifted by one token."""
    data = train_data if split == 'train' else val_data
    ix = torch.randint(data.size(0), (batch_size,))
    rows = data[ix].long()
    return rows[:, :-1].to(device), rows[:, 1:].to(device)


@torch.no_grad()
def estimate_loss():
    """Mean loss on both splits, plus the loss over the non-TRUNCATE targets only
    (the `filtered` columns of the training log)."""
    out = {}
    model.eval()
    for split in ['train', 'val']:
        ls = torch.zeros(eval_iters, device=device)
        fls = torch.zeros(eval_iters, device=device)
        for k in range(eval_iters):
            X, Y = get_batch(split)
            logits, loss = model(X, Y)
            ls[k] = loss

            flat_logits = logits.view(-1, logits.size(-1)) if logits.dim() == 3 else logits
            tgt = Y.reshape(-1)
            mask = tgt != TRUNCATE_IDX
            fls[k] = F.cross_entropy(flat_logits[mask], tgt[mask]) if mask.any() else torch.nan
        out[split] = torch.nanmean(ls).item()
        out[f'{split}_filtered'] = torch.nanmean(fls).item()
    model.train()
    return out


# =========================
# Model
# =========================
model = GPTLanguageModel(vocab_size, n_embd, block_size, n_head, n_layer,
                         dropout).to(device)
n_params = sum(p.numel() for p in model.parameters())
print(f"\n{n_params/1e6:.2f}M parameters")

with open(filename + '.json', 'w') as f:
    json.dump({'tag': args.tag, 'iters': args.iters, 'seed': args.seed, 'batch_size': batch_size,
               'block_size': block_size, 'n_embd': n_embd, 'n_head': n_head,
               'n_layer': n_layer, 'dropout': dropout, 'learning_rate': learning_rate,
               'vocab_size': vocab_size, 'train': args.train, 'val': args.val,
               'n_params': n_params}, f, indent=2)

optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate)
best_val = float('inf')

# =========================
# Training loop
# =========================
print("\n" + "=" * 80)
print(f"Training {filename}: iters={args.iters}")
print(f"Started:  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 80)
start = time.time()

with open(filename + '.csv', 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['Step', 'TrainLoss', 'TrainFilteredLoss',
                     'ValLoss', 'ValFilteredLoss', 'ElapsedTime'])

    for it in range(args.iters):
        if it % 1000 == 0 and torch.cuda.is_available():
            torch.cuda.empty_cache()

        if it % eval_interval == 0 or it == args.iters - 1:
            m = estimate_loss()
            elapsed = str(timedelta(seconds=int(time.time() - start)))
            print(f"step {it}: train {m['train']:.4f}/{m['train_filtered']:.4f}, "
                  f"val {m['val']:.4f}/{m['val_filtered']:.4f} | Time: {elapsed}", flush=True)
            writer.writerow([it, m['train'], m['train_filtered'],
                             m['val'], m['val_filtered'], elapsed])
            f.flush()

            if m['val'] < best_val:
                torch.save(model.state_dict(), filename + '.pth')
                best_val = m['val']

        xb, yb = get_batch('train')
        logits, loss = model(xb, yb)
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        optimizer.step()

print("\n" + "=" * 80)
print(f"Training completed in {timedelta(seconds=int(time.time() - start))}")
print(f"Best validation loss: {best_val:.4f}  ->  {filename}.pth")
print(f"Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 80)
