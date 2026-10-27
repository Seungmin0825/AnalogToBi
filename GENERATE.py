"""
Grammar-guided generation for AnalogToBi.

For each circuit type, --run samples are written to
Inference_<TYPE>_masked/run<i>.txt, and manifest_<TYPE>.csv records how every
walk stopped and its length. The paper's configuration:

    python GENERATE.py --weights checkpoints/AnalogToBi.pth \
        --run 1000 --batch-size 16 --max-length 1020 --seed 1337 \
        --gpu 0 --outdir runs/AnalogToBi

`--grammar off` samples with no mask at all; ERC then decides validity
afterwards.
"""


import argparse
import csv
import json
import os

import torch
from tqdm import tqdm

import CORE_ERC as ERC
import CORE_Grammar as G
from CORE_Grammar import (
    vocab_tokens, vocab_size, decode, sample_walks,
    REASON_VALID,
    block_size, n_embd, n_head, n_layer, dropout)
from Models.GPT import GPTLanguageModel

def erc_verdict(seq, reason):
    """Re-label a free-sampled walk by what ERC says about it."""
    if reason != REASON_VALID:
        return reason
    # G.decode joins with '->' and returns a string, so index through itos
    # instead. ERC keeps the circuit type token, matching parse_inference_file.
    tokens = [G.itos[i] for i in seq if G.itos[i] != 'TRUNCATE']
    clean, *_ = ERC.run_rule_validation(tokens)
    return REASON_VALID if clean else G.REASON_ERC_FAIL


def resolve_device(requested):
    """Pick a CUDA device, tolerating CUDA_VISIBLE_DEVICES remapping.

    Under `CUDA_VISIBLE_DEVICES=6` the process sees that GPU as index 0, so a
    literal --gpu 6 would be an invalid ordinal.
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


def load_model(weights_path, device):
    """Rebuild the trained architecture and load its weights strictly.

    strict=True on purpose: a key mismatch must raise rather than leave part of
    the model randomly initialised.
    """
    model = GPTLanguageModel(vocab_size, n_embd, block_size, n_head, n_layer,
                             dropout).to(device)
    state = torch.load(weights_path, map_location=device)
    # older checkpoints also stored the causal mask of every head; the model
    # rebuilds it, so those entries are dropped rather than loaded
    state = {k: v for k, v in state.items() if not k.endswith('.tril')}
    model.load_state_dict(state, strict=True)
    model.eval()
    print(f"Loaded {weights_path} "
          f"({sum(p.numel() for p in model.parameters())/1e6:.2f}M parameters)")
    return model


def generate_samples(model, circuit, n, args, device, on_batch=None):
    """Return (seqs, reasons) for n samples of one circuit type.

    With the grammar on, every sample is a walk that terminated validly. With
    it off, every walk is kept and ERC labels it. on_batch is passed through
    to sample_walks.
    """
    seqs = [None] * n
    reasons = [None] * n
    pending = list(range(n))
    while pending:
        new_seqs, new_reasons = sample_walks(
            model, circuit, len(pending), args.batch_size, device,
            # the decoder stops at max_length; the step budget only has to be
            # large enough to reach it
            max_new_tokens=args.max_length + 4,
            max_length=args.max_length, temperature=args.temperature,
            grammar=(args.grammar == 'on'), on_batch=on_batch)
        if args.grammar == 'off':
            # Nothing enforced the rules, so the provisional 'valid' only means
            # the model chose to stop. ERC is the arbiter here.
            new_reasons = [erc_verdict(s, r) for s, r in zip(new_seqs, new_reasons)]
        for i, s, r in zip(pending, new_seqs, new_reasons):
            seqs[i], reasons[i] = s, r
        if args.grammar == 'off':
            break
        pending = [i for i in pending if reasons[i] != REASON_VALID]
    return seqs, reasons


def main():
    """Command-line entry point."""
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--weights', required=True)
    p.add_argument('--grammar', choices=['on', 'off'], default='on',
                   help="'off' samples with no mask at all. Validity is then "
                        "decided post hoc by ERC rather than enforced during "
                        "decoding.")
    p.add_argument('--gpu', type=int, default=0)
    p.add_argument('--cpu', action='store_true',
                   help='run on the CPU even when a GPU is present')
    p.add_argument('--run', type=int, default=1000, help='samples per circuit type')
    p.add_argument('--batch-size', type=int, default=16)
    p.add_argument('--temperature', type=float, default=0.7)
    p.add_argument('--max-length', type=int, default=1020,
                   help='length at which a walk that has not closed is declared '
                        'max_length; it must stay below the 1024-token context, '
                        'which is the size of the position table')
    p.add_argument('--seed', type=int, default=1337)
    p.add_argument('--outdir', required=True)
    p.add_argument('--types', nargs='*', default=None,
                   help='subset of circuit types, e.g. Opamp LDO (default: all 15)')
    args = p.parse_args()

    if args.max_length > block_size:
        raise SystemExit(f"--max-length {args.max_length} exceeds the model's "
                         f"{block_size}-token context")
    if args.grammar == 'off':
        print("Grammar: OFF (free sampling; ERC decides validity afterwards)")

    torch.manual_seed(args.seed)
    if args.cpu:
        print('Device: cpu (--cpu)')
        device = 'cpu'
    else:
        device = resolve_device(args.gpu)
    model = load_model(args.weights, device)

    all_types = [t for t in vocab_tokens if t.startswith('CIRCUIT_')]
    if args.types:
        selected = []
        for t in args.types:
            full = t if t.startswith('CIRCUIT_') else f'CIRCUIT_{t}'
            if full not in all_types:
                raise SystemExit(f"Unknown circuit type: {t}")
            selected.append(full)
        all_types = selected

    os.makedirs(args.outdir, exist_ok=True)
    with open(os.path.join(args.outdir, 'run_config.json'), 'w') as f:
        json.dump({'weights': args.weights, 'run': args.run,
                   'batch_size': args.batch_size, 'temperature': args.temperature,
                   'max_length': args.max_length, 'seed': args.seed,
                   'grammar': args.grammar}, f, indent=2)

    print(f"\n{args.run} samples x {len(all_types)} circuit types -> {args.outdir}")

    n_types = len(all_types)
    name_width = max(len(c) for c in all_types) - len('CIRCUIT_')
    for ci, circuit in enumerate(all_types, 1):
        cdir = os.path.join(args.outdir, f'Inference_{circuit}_masked')
        os.makedirs(cdir, exist_ok=True)

        # one bar per type, counting finished samples: walks that terminated
        # validly, or every walk when the grammar is off
        desc = f"[{ci:>{len(str(n_types))}}/{n_types}] {circuit[len('CIRCUIT_'):]:<{name_width}}"
        with tqdm(total=args.run, desc=desc, ncols=100,
                  bar_format='{desc} {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} '
                             '[{elapsed}<{remaining}]') as bar:
            seqs, reasons = generate_samples(
                model, circuit, args.run, args, device,
                on_batch=lambda rs: bar.update(
                    len(rs) if args.grammar == 'off'
                    else sum(r == REASON_VALID for r in rs)))

        manifest = []
        for i, (seq, r) in enumerate(zip(seqs, reasons)):
            fname = f'run{i}.txt'
            with open(os.path.join(cdir, fname), 'w') as f:
                f.write(decode(seq))
            manifest.append([fname, r, len(seq)])

        with open(os.path.join(args.outdir, f'manifest_{circuit}.csv'), 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(['file', 'reason', 'length'])
            w.writerows(manifest)

    print(f"\n{'='*70}")
    print(f"Wrote {args.run * len(all_types)} sequences to {args.outdir}")
    print("Score them with METRIC_Valid_n_Novel.py, METRIC_ExactMatching.py and "
          "METRIC_TypeAcc.py.")
    print('='*70)


if __name__ == '__main__':
    main()
