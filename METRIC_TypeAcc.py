"""
GAT type-classification accuracy for one or more generation runs.

Reuses INFER_GAT's model, vocabulary and graph construction verbatim -
importing it loads GAT_Classifier.pth and defines sequence_to_graph() - and adds
two things that batch analysis over whole generation runs needs:

  * run directories as arguments instead of the current working directory
  * graphs batched through the network instead of one forward pass per circuit

Scope is every sample in the run, which is what INFER_GAT.py also reports, so
the two agree on the same run. A walk stopped at the length cap is an unfinished
circuit rather than a wrong one, and it still carries the devices its type token
asked for, so it is scored like any other. `--valid-only` restricts the count to
the samples that terminated validly (manifest_<TYPE>.csv, when present) and pass
all four ERC tests, which is how validity is defined. That is also the scope of
the valid & novel figure of METRIC_Valid_n_Novel.py, so the two can be read side
by side.

Usage:
    python METRIC_TypeAcc.py runs/AnalogToBi --csv gat_acc.csv
    python METRIC_TypeAcc.py runs/* --valid-only
"""

import argparse
import csv
import os
from collections import Counter, defaultdict
from pathlib import Path

import torch

from CORE_ERC import parse_inference_file, passes_erc

# importing runs INFER_GAT's module level: builds the vocab and loads
# GAT_Classifier.pth onto `device`
import INFER_GAT as G


def selected_files(run_dir, valid_only=False):
    """(circuit_type, path) pairs for one run, every sample by default."""
    run_dir = Path(run_dir)
    for subdir in sorted(run_dir.glob('Inference_*_masked')):
        circuit = subdir.name[len('Inference_'):-len('_masked')]
        manifest = run_dir / f'manifest_{circuit}.csv'

        names = None
        if manifest.exists():
            with open(manifest) as f:
                reader = csv.DictReader(f)
                if 'reason' in (reader.fieldnames or []):
                    names = [r['file'] for r in reader
                             if not valid_only or r['reason'] == 'valid']
        if names is None:
            names = [p.name for p in sorted(subdir.glob('run*.txt'))]

        for name in names:
            path = subdir / name
            if not path.exists():
                continue
            if valid_only and not passes_erc(parse_inference_file(str(path))[0]):
                continue
            yield circuit, path


def batch_graphs(sequences):
    """Collate per-sequence graphs into one disconnected graph for the GAT."""
    xs, edges, attrs, batch = [], [], [], []
    offset = 0
    for gi, seq in enumerate(sequences):
        x, edge_index, edge_attr, _ = G.create_graph_data(seq)
        xs.append(x)
        edges.append(edge_index + offset)
        attrs.append(edge_attr)
        batch.append(torch.full((x.size(0),), gi, dtype=torch.long))
        offset += x.size(0)
    return (torch.cat(xs), torch.cat(edges, dim=1),
            torch.cat(attrs), torch.cat(batch))


def classify_run(run_dir, batch_size=256, valid_only=False):
    """{circuit: Counter(total, correct)} plus a confusion tally."""
    per_type = defaultdict(Counter)
    confusion = defaultdict(Counter)

    pending_seqs, pending_types = [], []

    def flush():
        """Classify the pending batch of sequences and record the predictions."""
        if not pending_seqs:
            return
        x, edge_index, edge_attr, batch = batch_graphs(pending_seqs)
        with torch.no_grad():
            preds, _ = G.model.predict(x.to(G.device), edge_index.to(G.device),
                                       edge_attr.to(G.device), batch.to(G.device))
        for truth, p in zip(pending_types, preds.tolist()):
            predicted = G.idx_to_label[p]
            per_type[truth]['total'] += 1
            per_type[truth]['correct'] += int(predicted == truth)
            confusion[truth][predicted] += 1
        pending_seqs.clear()
        pending_types.clear()

    for circuit, path in selected_files(run_dir, valid_only):
        pending_seqs.append(G.parse_inference_file(path))
        pending_types.append(circuit)
        if len(pending_seqs) >= batch_size:
            flush()
    flush()

    return per_type, confusion


def main():
    """Command-line entry point."""
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('dirs', nargs='+')
    p.add_argument('--valid-only', action='store_true',
                   help='score only the samples that pass ERC, instead of '
                        'every sample')
    p.add_argument('--batch-size', type=int, default=256)
    p.add_argument('--csv', help='write per-type results here')
    p.add_argument('--confusion', action='store_true',
                   help='print the top mispredictions per run')
    args = p.parse_args()

    scope = 'ERC-valid samples only' if args.valid_only else 'every sample'
    print(f"\n{'='*78}\nGAT type accuracy over {scope}\n{'='*78}")

    rows = []
    overall = {}
    for run_dir in args.dirs:
        if not os.path.isdir(run_dir):
            raise SystemExit(f"Not a directory: {run_dir}")
        per_type, confusion = classify_run(run_dir, args.batch_size,
                                           args.valid_only)
        tot = sum(per_type.values(), Counter())
        acc = tot['correct'] / tot['total'] if tot['total'] else float('nan')

        overall[run_dir] = (acc, tot['correct'], tot['total'])
        print(f"{run_dir}\n  {'OVERALL':24s} {acc:.4f}  "
              f"({tot['correct']}/{tot['total']})", flush=True)

        rows.append({'run': run_dir, 'circuit': 'OVERALL',
                     'n': tot['total'], 'correct': tot['correct'],
                     'type_acc': f'{acc:.4f}'})

        # Macro average over the named types, General excluded. General is a
        # catch-all class - "does it look General" is not a type judgement - so
        # the paper's per-type table leaves it out of its average. Unweighted, so
        # rare types count as much as Opamp; with uniform 1,000-per-type pools
        # this and OVERALL differ mainly by how General scores.
        named = [c for c in per_type if c != 'CIRCUIT_General' and per_type[c]['total']]
        if named:
            macro = sum(per_type[c]['correct'] / per_type[c]['total'] for c in named) / len(named)
            print(f"  {'MACRO (excl. General)':24s} {macro:.4f}  "
                  f"(unweighted mean over {len(named)} types)", flush=True)
            rows.append({'run': run_dir, 'circuit': 'MACRO_excl_General',
                         'n': len(named), 'correct': '', 'type_acc': f'{macro:.4f}'})
        for circuit in sorted(per_type):
            c = per_type[circuit]
            rows.append({'run': run_dir, 'circuit': circuit,
                         'n': c['total'], 'correct': c['correct'],
                         'type_acc': f"{c['correct']/c['total']:.4f}" if c['total'] else ''})

        if args.confusion:
            print("   most common confusions:")
            worst = sorted(per_type, key=lambda c: per_type[c]['correct'] / max(per_type[c]['total'], 1))[:3]
            for circuit in worst:
                top = confusion[circuit].most_common(3)
                shown = ', '.join(f"{k.replace('CIRCUIT_','')} {v}" for k, v in top)
                print(f"     {circuit.replace('CIRCUIT_',''):20s} -> {shown}")

    if args.csv and rows:
        with open(args.csv, 'w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print(f"\nPer-type results written to {args.csv}")


if __name__ == '__main__':
    main()
