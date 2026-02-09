# AnalogToBi

**AnalogToBi: Device-Level Analog Circuit Topology Generation via Bipartite Graph and Grammar-Guided Decoding**

AnalogToBi is a framework for automatic generation of device-level analog circuit topologies. It trains a compact decoder-only Transformer (11.3M parameters) from scratch and generates electrically valid, novel circuit topologies with explicit functional control.

## Key Features

- **Circuit type token**: Explicit control over 15 functional circuit categories (OpAmp, LDO, Comparator, etc.)
- **Bipartite graph representation**: Decouples devices and nets into distinct node types for compact structural description
- **Grammar-guided decoding**: State machine-based constrained decoding enforces electrical validity during generation
- **Device renaming augmentation**: Randomizes device numbering to prevent memorization while preserving topology

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

The `Dataset/` directory contains 3,350 raw analog circuit samples. Each numbered folder includes:

| File | Description |
|------|-------------|
| `{ID}.cir` | SPICE netlist |
| `Book{ID}.png` | Textbook/paper screenshot |
| `Cadence{ID}.png` | Cadence schematic screenshot |
| `Pagenumber{ID}.txt` | Page number or paper reference |
| `Port{ID}.txt` | Netlist port information |

See [Dataset/data_categorization.md](Dataset/data_categorization.md) for detailed categorization by source textbook and circuit type.

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

**Step 4: Stratified train/validation split**

```bash
python PREPROCESSING_Stratified_Split.py
```
Performs 90/10 stratified split preserving circuit type distribution.

**Step 5: Device renaming augmentation**

```bash
python PREPROCESSING_Renaming.py
```
Randomizes device numbering (e.g., NM1 -> NM5) while preserving topology to prevent memorization.

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
python GPT_Inference_Grammar.py
```
Generates circuit topologies using a 6-state grammar that enforces bipartite structure and electrical validity during decoding.

### 4. Evaluation Metrics

**GAT batch classification**

```bash
python GAT_Inference_ALL.py
```
Classifies all generated circuits and reports accuracy per circuit type.

**Validity (ERC)**

```bash
python METRIC_Validity.py
```
Batch electrical rule checking across all generated circuits.

**Novelty**

```bash
python METRIC_Novelty.py
```
Measures topology novelty via graph isomorphism against the training dataset.

**Validity + Novelty (combined)**

```bash
python METRIC_Valid_n_Novel.py
```
Reports combined ERC pass rate and novelty per circuit type.

**N-gram memorization analysis**

```bash
python METRIC_N_Gram.py
```
Measures training data memorization using 10-gram matching.

### 5. Utilities

**SPICE netlist conversion**

```bash
python GRAPH2SPICE.py
```
Converts generated sequences to SPICE netlists with automatic voltage biasing.

## Project Structure

```
AnalogToBi/
├── Dataset/                              # Raw circuit dataset (3,350 samples)
├── Models/
│   ├── GPT.py                            # GPT model architecture
│   └── GAT.py                            # GAT classifier architecture
├── PREPROCESSING_Bipartite.py            # Step 1: Netlist to bipartite graph
├── PREPROCESSING_Augmentation_Bipart.py  # Step 2: Graph to sequence + augmentation
├── PREPROCESSING_Add_Circuit_Types.py    # Step 3: Circuit type token injection
├── PREPROCESSING_Stratified_Split.py     # Step 4: Stratified train/val split
├── PREPROCESSING_Renaming.py            # Step 5: Device renaming augmentation
├── GPT_Pretrain.py                       # GPT training
├── GAT_Train.py                          # GAT classifier training
├── GPT_Inference_Grammar.py              # Grammar-guided generation
├── GAT_Inference_ALL.py                  # Batch GAT classification
├── METRIC_Validity.py                    # ERC pass rate evaluation
├── METRIC_Novelty.py                     # Topology novelty evaluation
├── METRIC_Valid_n_Novel.py               # Combined validity + novelty
├── METRIC_N_Gram.py                      # Memorization analysis
├── ERC.py                                # Electrical rule checker
├── GRAPH2SPICE.py                        # Sequence to SPICE converter
└── environment.yml                       # Conda environment
```

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
