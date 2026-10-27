#!/usr/bin/env python3
"""
Expand the released dataset files.

`data/` ships the exact token sequences the released checkpoints were trained on, stored as
compressed int16 token indices (about 30x smaller than the `.npy` files the scripts read). This
script turns them back into the `.npy` files every other script expects, in the package root:

    Training.npy                 walks with the circuit type token, 90% split
    Validation.npy               the remaining 10%
    Training_renamed.npy         the same walks after device renaming - what TRAIN_GPT.py
    Validation_renamed.npy       and TRAIN_GAT.py read

Each archive carries a SHA-256 of its token array, which is checked while unpacking.

Usage:
    python UNPACK_DATASET.py                        # all four files
    python UNPACK_DATASET.py Training_renamed       # one of them
    python UNPACK_DATASET.py --list                 # what is available, and its size
    python UNPACK_DATASET.py --force                # overwrite files that already exist

Running PREPROCESSING_* again draws an equivalent but different set of walks, because the
traversal order and the device renaming are randomised. Use these files to reproduce the paper's
numbers exactly.
"""

import argparse
import hashlib
import sys
from pathlib import Path

import numpy as np

from CORE_Vocab import itos, vocab_size

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / 'data'


def available():
    """Names of the packed dataset files, in a stable order."""
    order = ['Training', 'Validation', 'Training_renamed', 'Validation_renamed']
    present = {p.stem for p in DATA_DIR.glob('*.npz')}
    return [n for n in order if n in present] + sorted(present - set(order))


def unpack(name, force=False):
    """Write <name>.npy next to the scripts, from data/<name>.npz. Returns the row count."""
    src = DATA_DIR / f'{name}.npz'
    dst = BASE_DIR / f'{name}.npy'
    if not src.exists():
        raise SystemExit(f'No packed file for {name}: {src} is missing')
    if dst.exists() and not force:
        print(f'  [skip] {dst.name} exists (pass --force to overwrite)')
        return None

    with np.load(src, allow_pickle=False) as archive:
        tokens = archive['tokens']
        expected = str(archive['sha256'])
        packed_vocab = int(archive['vocab_size'])

    if packed_vocab != vocab_size:
        raise SystemExit(f'{name}: packed against a {packed_vocab}-token vocabulary, '
                         f'CORE_Vocab has {vocab_size}')
    digest = hashlib.sha256(tokens.tobytes()).hexdigest()
    if digest != expected:
        raise SystemExit(f'{name}: checksum mismatch, the archive is corrupt\n'
                         f'  expected {expected}\n  found    {digest}')

    lookup = np.array([itos[i] for i in range(vocab_size)], dtype=object)
    np.save(dst, lookup[tokens])
    print(f'  {dst.name:34s} {tokens.shape[0]:7d} x {tokens.shape[1]}  '
          f'{dst.stat().st_size / 1e6:8.1f} MB')
    return tokens.shape[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('names', nargs='*', help='files to unpack (default: all of them)')
    parser.add_argument('--list', action='store_true', help='list the packed files and exit')
    parser.add_argument('--force', action='store_true', help='overwrite existing .npy files')
    args = parser.parse_args()

    if not DATA_DIR.is_dir():
        raise SystemExit(f'No data directory at {DATA_DIR}')

    names = available()
    if args.list:
        print(f'{len(names)} packed files in {DATA_DIR}:')
        for n in names:
            print(f'  {n:34s} {(DATA_DIR / f"{n}.npz").stat().st_size / 1e6:8.1f} MB')
        return

    wanted = args.names or names
    unknown = [n for n in wanted if n not in names]
    if unknown:
        raise SystemExit(f'Unknown dataset file(s): {", ".join(unknown)}\n'
                         f'Available: {", ".join(names)}')

    print(f'Unpacking {len(wanted)} file(s) from {DATA_DIR}')
    for name in wanted:
        unpack(name, force=args.force)
    print('Done.')


if __name__ == '__main__':
    main()
