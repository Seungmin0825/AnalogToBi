#!/usr/bin/env python3
"""
Analyze generated sequences in Inference/*.txt
For each file produce: first_token, second_token, last_token (excluding TRUNCATE), token_count (excluding TRUNCATE)
Writes per-file summary to Inference/analysis_summary.csv and prints aggregated stats.
"""
import glob
import os
import csv
from collections import Counter

INFERENCE_DIR = 'Inference'
OUT_CSV = os.path.join(INFERENCE_DIR, 'analysis_summary.csv')
PATTERN = os.path.join(INFERENCE_DIR, 'run*.txt')

files = sorted(glob.glob(PATTERN))
if not files:
    print('No run*.txt files found in', INFERENCE_DIR)
    raise SystemExit(0)

rows = []
first_pairs = Counter()
last_tokens = Counter()
token_counts = []
all_tokens = Counter()

for p in files:
    with open(p, 'r', encoding='utf-8') as f:
        txt = f.read().strip()
    # tokens are joined like: TOK1->TOK2->...-> (decode used '->' and appended a trailing '->')
    parts = [t for t in txt.split('->') if t != '' and t is not None]
    # filter out any stray whitespace
    parts = [t.strip() for t in parts if (t and t.strip()!='')]
    # compute first two tokens (pad with empty string if missing)
    first = parts[0] if len(parts) >= 1 else ''
    second = parts[1] if len(parts) >= 2 else ''
    # last token excluding 'TRUNCATE'
    last = ''
    for tok in reversed(parts):
        if tok != 'TRUNCATE':
            last = tok
            break
    # token count excluding 'TRUNCATE'
    count = sum(1 for t in parts if t != 'TRUNCATE')

    rows.append({'file': os.path.basename(p), 'first_token': first, 'second_token': second, 'last_token': last, 'token_count': count})
    first_pairs[(first, second)] += 1
    if last:
        last_tokens[last] += 1
    token_counts.append(count)
    # accumulate token frequencies excluding TRUNCATE
    for t in parts:
        if t != 'TRUNCATE':
            all_tokens[t] += 1

# write CSV
with open(OUT_CSV, 'w', newline='', encoding='utf-8') as csvfile:
    fieldnames = ['file', 'first_token', 'second_token', 'last_token', 'token_count']
    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
    writer.writeheader()
    for r in rows:
        writer.writerow(r)

# print summary
print('Wrote per-file summary to', OUT_CSV)
print('Files processed:', len(rows))
print('\nTop 20 start pairs (first,second):')
for (a,b), c in first_pairs.most_common(20):
    print(f'{a} -> {b}: {c}')

print('\nTop 20 last tokens:')
for tok, c in last_tokens.most_common(20):
    print(f'{tok}: {c}')

print('\nToken counts summary (per-file, excluding TRUNCATE):')
if token_counts:
    import statistics
    print('min', min(token_counts), 'max', max(token_counts), 'mean', statistics.mean(token_counts), 'median', statistics.median(token_counts))

print('\nTop 30 most common tokens (excluding TRUNCATE):')
for tok, c in all_tokens.most_common(30):
    print(f'{tok}: {c}')

print('\nDone.')
