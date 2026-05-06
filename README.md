# AnalogToBi

**AnalogToBi: Device-Level Analog Circuit Topology Generation via Bipartite Graph and Grammar-Guided Decoding**

AnalogToBi is a framework for automatic generation of device-level analog circuit topologies. It trains a compact decoder-only Transformer (11.3M parameters) from scratch and generates electrically valid, novel circuit topologies.

## Key Features

- **Circuit type conditioning**: Divide datasets as 15 circuit categories (OpAmp, LDO, Comparator, etc.)
- **Device renaming augmentation**: Randomizes device numbering to prevent memorization while preserving topology
- **Bipartite graph representation**: Decouples devices and nets into distinct node types for compact structural description
- **Grammar-guided decoding**: State machine-based constrained decoding enforces electrical validity during generation


## Bipartite Graph Representation

```
Node Types:
  - Device nodes: NM1, PM1, NPN1, R1, C1, L1, DIO1, ...
  - Net nodes: VIN1, VOUT1, NET1, VDD, VSS, ...

Typed Edges (pin-level connections):
  - MOSFET: M_G, M_D, M_S, M_B, M_GD, M_SB, M_BDGS, ...
  - BJT:    B_B, B_C, B_E, B_BC, B_BCE, ...
  - Passive: R_C, C_C, L_C
  - Diode:  D_P, D_N, D_NP

Sequence: CIRCUIT_Opamp -> VSS -> M_SB -> NM1 -> M_D -> VOUT1 -> ... -> TRUNCATE
```

## Environment Setup

```bash
conda env create -f environment.yml
conda activate AnalogToBi
```

## Dataset

The `Dataset/` directory contains raw analog circuit samples. Each numbered folder includes:

| File | Description |
|------|-------------|
| `{ID}.cir` | SPICE netlist |
| `Book{ID}.png` | Textbook/paper screenshot |
| `Cadence{ID}.png` | Cadence schematic screenshot |
| `Pagenumber{ID}.txt` | Page number or paper reference |
| `Port{ID}.txt` | Netlist port information |

## Quick Start

### 1. Preprocessing

**Step 1: Convert SPICE netlists to bipartite graphs**

```bash
python PREPROCESSING_Bipartite.py
```
Parses `.cir` files and generates typed-edge adjacency matrices (`Graph_Bipart{ID}.csv`).

**Step 2: Convert graphs to sequences with augmentation**

```bash
python PREPROCESSING_Augmentation_Bipart.py
```
Converts bipartite graphs to token sequences via randomized graph traversal. Generates multiple valid sequences per circuit.

**Step 3: Add circuit type tokens**

```bash
python PREPROCESSING_Add_Circuit_Types.py
```
Prepends circuit type tokens (e.g., `CIRCUIT_Opamp`) to each sequence for conditional generation.

**Step 4: Prepare GPT training dataset**

```bash
python PREPROCESSING_GPT_dataset.py
```
Performs 90/10 stratified split preserving circuit type distribution for GPT training.

**Step 5: Device renaming augmentation**

```bash
python PREPROCESSING_Renaming.py --input Training.npy --output Training_renamed.npy
python PREPROCESSING_Renaming.py --input Validation.npy --output Validation_renamed.npy
```
Randomizes device numbering (e.g., NM1 -> NM5) while preserving topology to prevent memorization.

**Step 6: Prepare GAT training dataset**

```bash
python PREPROCESSING_GAT_dataset.py
```
Performs circuit-ID-based 90/10 split to prevent data leakage in GAT training.

**Step 7: Device renaming augmentation for GAT dataset**

```bash
python PREPROCESSING_Renaming.py --input Training_GAT.npy --output Training_GAT_renamed.npy
python PREPROCESSING_Renaming.py --input Validation_GAT.npy --output Validation_GAT_renamed.npy
```
Applies device renaming augmentation to the GAT dataset.

### 2. Training

**GPT Pretraining**

```bash
python GPT_Pretrain.py
```
Trains a decoder-only Transformer on circuit sequences with autoregressive token prediction.

**GAT Classifier Training**

```bash
python GAT_Train.py
```
Trains a Graph Attention Network classifier for circuit type classification.

### 3. Inference

**Grammar-guided circuit generation**

```bash
python GPT_Inference_Grammar.py CIRCUIT_Opamp
```
Generates circuit topologies using a 6-state grammar that enforces bipartite structure and electrical validity during decoding.

### 4. Evaluation Metrics

**GAT batch classification**

```bash
python GAT_Inference_ALL.py
```
Classifies all generated circuits and reports accuracy per circuit type.

**Validity + Novelty (combined)**

```bash
python METRIC_Valid_n_Novel.py
```
Reports combined ERC pass rate and novelty per circuit type.

**Exact sequence matching novelty**

```bash
python METRIC_ExactMatching.py
```
Measures novelty by checking whether generated sequences exactly match any sequence in the training set.


## Project Structure

```
AnalogToBi/
├── Dataset/                                  # Raw circuit dataset
├── Models/
│   ├── GPT.py                                # GPT model architecture
│   └── GAT.py                                # GAT classifier architecture
├── PREPROCESSING_Bipartite.py                # Step 1: Netlist to bipartite graph
├── PREPROCESSING_Augmentation_Bipart.py      # Step 2: Graph to sequence + augmentation
├── PREPROCESSING_Add_Circuit_Types.py        # Step 3: Circuit type token injection
├── PREPROCESSING_GPT_dataset.py              # Step 4: Stratified train/val split (GPT)
├── PREPROCESSING_Renaming.py                 # Step 5: Device renaming augmentation
├── PREPROCESSING_GAT_dataset.py              # Step 6: Circuit-ID-based split (GAT)
├── GPT_Pretrain.py                           # GPT training
├── GAT_Train.py                              # GAT classifier training
├── GPT_Inference_Grammar.py                  # Grammar-guided generation
├── GAT_Inference_ALL.py                      # Batch GAT classification
├── METRIC_Validity.py                        # ERC pass rate evaluation
├── METRIC_Novelty.py                         # Topology novelty evaluation
├── METRIC_Valid_n_Novel.py                   # Combined validity + novelty
├── METRIC_ExactMatching.py                   # Exact sequence matching novelty
├── ERC.py                                    # Electrical rule checker
└── environment.yml                           # Conda environment
```
