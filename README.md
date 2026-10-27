# AnalogToBi

**[NeurIPS 2026 poster] AnalogToBi: Device-Level Analog Circuit Topology Generation via Bipartite Graph and Grammar Guided Decoding**

Seungmin Kim, Mingun Kim, Yuna Lee, Yulhwa Kim\
Sungkyunkwan University

Paper: [arXiv:2603.08720](https://arxiv.org/abs/2603.08720)

AnalogToBi generates device-level analog circuit topologies. It trains a compact
decoder-only Transformer (11.3M parameters) from scratch and produces
electrically valid, novel circuits.

This release contains the configuration reported in the paper - bipartite
representation, circuit type token, device renaming and grammar-guided
decoding - together with the trained weights and the exact training data. The
ablated variants and the analysis scripts used to produce the tables are not
included.

## Key Features

- **Bipartite graph representation**: devices and nets are separate node types, with the pin-level connection carried by the edge
- **Circuit type conditioning**: 15 categories (OpAmp, LDO, Comparator, ...)
- **Device renaming augmentation**: randomises device numbering while preserving topology, which is what keeps the model from reproducing training sequences verbatim
- **Grammar-guided decoding**: a state machine constrains every step so the sequence stays a well-formed circuit

## Simple run

The released generator runs on a CPU, so trying it needs neither a GPU nor
training.

```bash
git clone https://github.com/Seungmin0825/AnalogToBi.git
cd AnalogToBi
pip install torch numpy pandas networkx tqdm torch_geometric
```

For the exact environment the paper's results were produced in (Linux, CUDA
11.7, Python 3.8, PyTorch 2.0.1), use `conda env create -f environment.yml` and
`conda activate AnalogToBi` instead. The pip route was also tested with Python
3.12 and PyTorch 2.14.

Generate eight op-amp topologies with the released weights, look at one, and
check them all:

```bash
python GENERATE.py --weights checkpoints/AnalogToBi.pth --types Opamp --run 8 --cpu --outdir runs/demo
cat runs/demo/Inference_CIRCUIT_Opamp_masked/run0.txt
python METRIC_Valid_n_Novel.py runs/demo
```

Each sample is one file: a walk over the circuit's bipartite graph. It starts
with the circuit type token and `VSS`, alternates net, edge, device, edge, net,
and ends in `TRUNCATE`:

```
CIRCUIT_Opamp->VSS->M_B->NM34->M_S->NET1->M_D->NM6->M_G->VCONT1->M_G->NM6->...->TRUNCATE->
```

`METRIC_Valid_n_Novel.py` then reports how many samples pass the electrical rule
check (validity) and how many are topologies that do not occur among the 2,165
training circuits (novelty). On our CPU server, generation took about two
minutes and scoring under one; most of the scoring time is spent loading the
dataset graphs.

`--types` takes one or more of `Opamp`, `LDO`, `Bandgap_Ref`, `Power_converter`,
`Oscillator`, `General`, `Mirror`, `Mixer`, `Power_Amp`, `PLL`, `Filter`,
`Comparator`, `Voltage_Regulator`, `Switched_Cap` and `ADC_DAC`; without it, all
15 types are generated. On a GPU machine, replace `--cpu` with `--gpu 0`.

Run every script from the repository root: the metrics read `Dataset/` and the
training data relative to it.

## Bipartite Graph Representation

```
Node types
  device nodes : NM1, PM1, NPN1, R1, C1, L1, DIO1, ...
  net nodes    : VIN1, VOUT1, NET1, VDD, VSS, ...

Typed edges (pin-level connections)
  MOSFET  : M_G, M_D, M_S, M_B, M_DG, M_BS, M_BDGS, ...
  BJT     : B_B, B_C, B_E, B_BC, B_BCE, ...
  passive : R_C, C_C, L_C
  diode   : D_P, D_N, D_NP

Sequence
  CIRCUIT_Opamp -> VSS -> M_BS -> NM1 -> M_D -> VOUT1 -> ... -> TRUNCATE
```

A device and a net are joined by exactly one edge, whose type names every pin
involved: a MOSFET with drain and source on the same net is `M_DS`, one edge.

## Contents

```
AnalogToBi/
|-- Dataset/                          raw circuits + bipartite graphs
|-- data/                             the training and validation sets, packed
|-- Models/
|   |-- GPT.py                        decoder, learned absolute position embeddings
|   `-- GAT.py                        circuit type classifier
|-- checkpoints/
|   |-- AnalogToBi.pth                the released generator (11.3M params)
|   |-- GAT_Classifier.pth            type classifier, for Type Accuracy
|   `-- GAT_Classifier_train_log.csv  its training log (loss / accuracy per epoch)
|
|-- CORE_ERC.py                       electrical rule checks
|-- CORE_Grammar.py                   vocabulary + grammar state machine + decoding
|-- CORE_Graph.py                     walk -> graph, topology comparison
|-- CORE_Vocab.py                     the token list, imported by everything above
|
|-- UNPACK_DATASET.py                 expand data/ into the .npy files the scripts read
|
|-- PREPROCESSING_Bipartite.py        1. netlist  -> bipartite graph
|-- PREPROCESSING_Augmentation.py     2. graph    -> walks
|-- PREPROCESSING_CircuitTypes.py     3. prepend the circuit type token
|-- PREPROCESSING_GPT_Dataset.py      4. stratified 90/10 split
|-- PREPROCESSING_Renaming.py         5. device renaming augmentation
|
|-- TRAIN_GPT.py                      generator training
|-- TRAIN_GAT.py                      classifier training
|-- GENERATE.py                       grammar-guided generation
|-- INFER_GAT.py                      batch classification of a run
|
|-- METRIC_Validity.py                ERC pass rate
|-- METRIC_Novelty.py                 topology novelty
|-- METRIC_Valid_n_Novel.py           validity + novelty together
|-- METRIC_ExactMatching.py           verbatim-copy rate
|-- METRIC_TypeAcc.py                 type accuracy
|
`-- SPICE_translation/                Cadence Spectre evaluation of generated circuits
    |-- GRAPH2CADENCE_subckt_general.py   valid & novel walks -> Spectre subcircuits (.scs)
    |-- tb_common.py                      shared testbench code
    `-- run_tb_<type>.py                  batch testbenches: opamp, ldo, comparator,
                                          filter, mixer, oscillator
```

Files are named by role, so `ls` groups them: `CORE_` for the modules
everything else imports, then the pipeline in order, then `METRIC_`.
`SPICE_translation/` holds the simulation side, which needs a Cadence Spectre
installation. Only the `CORE_` modules and `tb_common.py` are libraries; every
other file is a script you run.

`Dataset/` holds the 2,165 circuits the released checkpoints were trained on, one
folder each: the raw circuit (`{ID}.cir`, the two reference screenshots,
`Pagenumber{ID}.txt`, `Port{ID}.txt`) and the bipartite graph `Graph_Bipart{ID}.csv`
that step 1 produces. Folder names are the original circuit ids and are therefore
not contiguous. The per-circuit walk files are not shipped; `data/` carries the
same walks already split into training and validation sets, which is what the
training scripts read.

## Reproducing the paper's results

```bash
python GENERATE.py --weights checkpoints/AnalogToBi.pth \
    --run 1000 --batch-size 16 --max-length 1020 --seed 1337 \
    --gpu 0 --outdir runs/AnalogToBi
```

That is the paper's configuration: 1,000 samples for each of the 15 circuit
types, which takes several hours on a single GPU. Each sample is written to
`Inference_CIRCUIT_<Type>_masked/run<i>.txt`, and `manifest_CIRCUIT_<Type>.csv`
records how each walk stopped and its length. `--grammar off` samples without
any mask; ERC then decides validity afterwards.

Without a GPU, pass `--cpu` instead of `--gpu`; `TRAIN_GPT.py` takes the same
flag. The grammar itself is single-threaded Python, so the CPU is slower but not
prohibitively. `INFER_GAT.py`, `TRAIN_GAT.py` and `METRIC_TypeAcc.py` use a GPU
when one is visible and fall back to the CPU otherwise; `CUDA_VISIBLE_DEVICES=`
in front of the command forces the fallback.

Then score the run:

```bash
python METRIC_Valid_n_Novel.py runs/AnalogToBi   # validity and novelty
python METRIC_ExactMatching.py runs/AnalogToBi   # verbatim-copy rate
python INFER_GAT.py runs/AnalogToBi              # type accuracy
python METRIC_TypeAcc.py runs/AnalogToBi         # type accuracy, per type
```

The paper reports:

| Metric | Paper |
|---|---|
| Validity | 97.8% |
| Novelty | 92.1% |
| Valid & novel | 89.9% |
| Type accuracy (macro, excl. General) | 91.3% |

Run on the samples behind the paper, the same code reproduces these figures
exactly. A fresh run draws new samples, so its figures differ by sampling noise.

Validity is the fraction of samples that pass all four ERC tests (`CORE_ERC.py`).
The grammar allows `TRUNCATE` only once every device pin is connected and every
internal net joins two devices; validity is then judged on all four tests, so a
walk that terminated validly can still count as invalid.

Both type-accuracy scripts score every sample in the run, so they agree on the
same run; `METRIC_TypeAcc.py --valid-only` restricts the count to the
samples the ERC accepted. It reports two aggregates. `OVERALL` is
correct/total over the scored circuits. `MACRO (excl. General)` is the
unweighted mean over the 14 named types, leaving out `General`, which is a
catch-all class and is not scored as a type - that is the figure the paper
reports as type accuracy.

Every walk ends in `TRUNCATE`, the token that also pads each training row to
1,024 positions. The metrics also accept `End` as another name for it.

## SPICE evaluation of generated circuits (Cadence Spectre)

The valid and topology-novel walks of a run can be converted to netlists and
simulated with category-specific testbenches. Conversion and testbench
generation run anywhere; the simulation itself needs Cadence Spectre and the
GPDK045 models.

```bash
# 1. select the valid & novel walks: writes valid_novel_ids_<Type>.json into the run
python METRIC_Valid_n_Novel.py runs/AnalogToBi --write-ids

# 2. convert them to Spectre subcircuits: runs/AnalogToBi/SPICE_Inference_<Type>/*.scs
python SPICE_translation/GRAPH2CADENCE_subckt_general.py --run-dir runs/AnalogToBi

# 3. simulate one category (set GPDK045_LIB, SPECTRE_BIN and LM_LICENSE_FILE first)
export GPDK045_LIB=/path/to/gpdk045.scs
export SPECTRE_BIN=/path/to/spectre
export LM_LICENSE_FILE=port@your-license-server
python SPICE_translation/run_tb_opamp.py \
    --subckt-dir runs/AnalogToBi/SPICE_Inference_Opamp \
    --out-dir    runs/AnalogToBi/batch_results/Opamp
```

Each `run_tb_<type>.py` selects the subcircuits that expose the ports its
testbench needs. It decides bias sources for the remaining ports from the
netlist (current direction of `IB*`, bias level of `VB*`/`VBB*`), simulates every
DUT, and writes `run<id>/` plus an incrementally updated `summary.csv` with the
measured figures and a PASS flag. `--dry-run` writes the testbenches without
simulating, and `--run-ids 0,9,18` and `--limit N` restrict the batch. The pass
criteria are stated in each script's docstring (for example, op-amps pass at DC
gain >= 20 dB in an open-loop AC analysis with a 100 pF load).

Before netlisting, the converter checks every walk again with the four ERC tests
of `CORE_ERC.py`. It uses default GPDK045 device sizes (`w=10u l=1u` NMOS,
`w=15u l=1u` PMOS, 1 pF, 10 kOhm, 1 nH) and orders subcircuit ports as rails,
inputs, outputs, others.

## Training from scratch

### 1. The dataset

The sequences the released checkpoints were trained on ship with this package, in `data/`, as
compressed token indices (127 MB for what is about 4 GB expanded). Expand them before training:

```bash
python UNPACK_DATASET.py            # writes Training*.npy and Validation*.npy into this folder
python UNPACK_DATASET.py --list     # what is in data/, and how large
```

That gives the stratified 90/10 split of the walks (`Training.npy`,
`Validation.npy` and their `_renamed` counterparts, 357,759 / 39,756 walks). Each archive carries a SHA-256 of its token
array, checked while unpacking.

### 2. Rebuilding the dataset from the circuits instead

```bash
python PREPROCESSING_Bipartite.py                # .cir -> Graph_Bipart{ID}.csv
python PREPROCESSING_Augmentation.py             # graph -> walks (see the note below)
python PREPROCESSING_CircuitTypes.py             # prepend CIRCUIT_<type>
python PREPROCESSING_GPT_Dataset.py              # stratified 90/10 split (numpy seed 42)
python PREPROCESSING_Renaming.py --input Training.npy   --output Training_renamed.npy
python PREPROCESSING_Renaming.py --input Validation.npy --output Validation_renamed.npy
```

These are the scripts that produced the dataset behind the released
checkpoints. The traversal order and the device renaming are randomised, so a
rerun draws an equivalent but different set of walks over the same circuits.
To reproduce the paper's numbers, use the walks in `data/`.

The first two scripts validate on a small range and then ask before processing
the full dataset, so they expect an interactive terminal.

### 3. Training

```bash
python TRAIN_GPT.py --tag AnalogToBi \
    --train Training_renamed.npy --val Validation_renamed.npy \
    --iters 100000 --seed 1337 --gpu 0
```

These are the settings of the released generator: batch 64, AdamW at 3e-4. The
checkpoint is written at minimum validation loss to `Pretrain_AnalogToBi.pth`.

```bash
python TRAIN_GAT.py
```

The type classifier is trained on the same split as the generator
(`Training_renamed.npy` / `Validation_renamed.npy`): Adam at 5e-4 with cosine
annealing, weight decay 1e-3, label smoothing 0.1, 100 epochs, kept at the
highest validation accuracy. The released `GAT_Classifier.pth` reached 99.86%
validation accuracy at its saved epoch (93).

## Vocabulary

`CORE_Vocab.py` holds the single definition of the 397-token vocabulary: the
edge types, the power rails, the 15 circuit type tokens, the device, net and
port tokens, and `TRUNCATE`. Every other module imports it, so training,
grammar-guided decoding and each metric index the same tokens. `CORE_Grammar.py`
re-exports it for the scripts that already import the grammar.

## License

See `LICENSE`.
