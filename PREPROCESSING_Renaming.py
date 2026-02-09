"""
Device Renaming-Based Data Augmentation

This script implements device renaming augmentation to prevent overfitting by
randomizing device numbering while preserving circuit functionality and topology.

Renaming Strategy:
- Device tokens: Randomly permute numbers (e.g., NM1→NM5, PM2→PM15)
- Consistency: All occurrences of a device renamed identically
- Preservation: External pins (VDD, VSS, ports), net nodes (NET1-50), 
  edge types (M_D, M_G, etc.), and circuit types remain unchanged

Purpose:
Encourage the model to learn structural relationships rather than memorizing
specific device number patterns, improving generalization to novel topologies.

Supported Device Types:
- MOSFETs: NM1-NM35, PM1-PM35 (35 each)
- BJTs: NPN1-NPN27, PNP1-PNP27 (27 each)
- Passives: R1-R28 (28), C1-C16 (16), L1-L24 (24)
- Diodes: DIO1-DIO8 (8)
"""

import numpy as np
import random
import re
from tqdm import tqdm
import argparse

# =========================
# Device Type Configuration
# =========================
# Maximum device numbers for each type (aligned with vocabulary in GPT_Pretrain.py)
DEVICE_CONFIGS = {
    'NM': {'max': 35},   # NM1-NM35
    'PM': {'max': 35},   # PM1-PM35
    'NPN': {'max': 27},  # NPN1-NPN27
    'PNP': {'max': 27},  # PNP1-PNP27
    'R': {'max': 28},    # R1-R28
    'C': {'max': 16},    # C1-C16
    'L': {'max': 24},    # L1-L24
    'DIO': {'max': 8},   # DIO1-DIO8
}

# =========================
# Protected Tokens (Not Renamed)
# =========================
# External interface tokens that must remain unchanged
EXTERNAL_PINS = {
    'VDD', 'VSS', 'GND', 'TRUNCATE',
}

# Add numbered external pins
for i in range(1, 21):
    EXTERNAL_PINS.add(f'VIN{i}')
    EXTERNAL_PINS.add(f'VOUT{i}')
    EXTERNAL_PINS.add(f'VB{i}')
    EXTERNAL_PINS.add(f'IB{i}')
    EXTERNAL_PINS.add(f'IIN{i}')
    EXTERNAL_PINS.add(f'IOUT{i}')
    EXTERNAL_PINS.add(f'VCONT{i}')
    EXTERNAL_PINS.add(f'VCLK{i}')
    EXTERNAL_PINS.add(f'VCM{i}')
    EXTERNAL_PINS.add(f'VREF{i}')
    EXTERNAL_PINS.add(f'IREF{i}')
    EXTERNAL_PINS.add(f'VRF{i}')
    EXTERNAL_PINS.add(f'VLO{i}')
    EXTERNAL_PINS.add(f'VIF{i}')
    EXTERNAL_PINS.add(f'VBB{i}')
    EXTERNAL_PINS.add(f'LOGICA{i}')
    EXTERNAL_PINS.add(f'LOGICB{i}')
    EXTERNAL_PINS.add(f'LOGICD{i}')
    EXTERNAL_PINS.add(f'LOGICF{i}')
    EXTERNAL_PINS.add(f'LOGICG{i}')
    EXTERNAL_PINS.add(f'LOGICQ{i}')
    EXTERNAL_PINS.add(f'LOGICQA{i}')
    EXTERNAL_PINS.add(f'LOGICQB{i}')
    EXTERNAL_PINS.add(f'VLATCH{i}')
    EXTERNAL_PINS.add(f'VHOLD{i}')
    EXTERNAL_PINS.add(f'VTRACK{i}')

# Circuit functional category tokens
CIRCUIT_TYPES = {
    'CIRCUIT_Opamp', 'CIRCUIT_Mirror', 'CIRCUIT_Comparator',
    'CIRCUIT_Mixer', 'CIRCUIT_LDO', 'CIRCUIT_Oscillator',
    'CIRCUIT_Filter', 'CIRCUIT_Bandgap_Ref', 'CIRCUIT_Power_Amp',
    'CIRCUIT_Voltage_Regulator', 'CIRCUIT_Power_converter',
    'CIRCUIT_PLL', 'CIRCUIT_Switched_Cap', 'CIRCUIT_ADC_DAC',
    'CIRCUIT_General'
}

# Typed edge tokens (pin-level connection types)
EDGE_TYPES = {
    'M_B', 'M_D', 'M_G', 'M_S', 'M_BD', 'M_BG', 'M_BS', 'M_DG', 'M_DS', 'M_GS',
    'M_BDG', 'M_BDS', 'M_BGS', 'M_DGS', 'M_BDGS',
    'B_B', 'B_C', 'B_E', 'B_BC', 'B_BE', 'B_CE', 'B_BCE',
    'R_C', 'C_C', 'L_C',
    'D_P', 'D_N', 'D_NP', 'D_PN'
}

# Internal net node pattern (NET1, NET2, ..., NET50)
NET_PATTERN = re.compile(r'^NET\d+$')


# =========================
# Token Parsing Functions
# =========================

def parse_device_token(token):
    """Parse device token into type and number components.
    
    Extracts device type prefix and numeric suffix from device tokens.
    Returns None for non-device tokens.
    
    Args:
        token: String token (e.g., 'NM1', 'PM15', 'R3', 'VDD')
    Returns:
        Tuple of (device_type, device_num) or (None, None) if not a device
    Examples:
        'NM1' -> ('NM', 1)
        'PM15' -> ('PM', 15)
        'R3' -> ('R', 3)
        'VDD' -> (None, None)
    """
    for device_type in DEVICE_CONFIGS.keys():
        if token.startswith(device_type):
            remainder = token[len(device_type):]
            
            # Extract numeric suffix
            if remainder.isdigit():
                device_num = int(remainder)
                return (device_type, device_num)
    
    return (None, None)


# =========================
# Device Renaming Algorithm
# =========================

def randomize_device_numbers(sequence, seed=None):
    """Apply device renaming augmentation to a single circuit sequence.
    
    Two-pass algorithm:
    1. First pass: Identify all device tokens and their types
    2. Create random permutation mapping for each device type
    3. Second pass: Apply consistent renaming to all device occurrences
    
    Preserves:
    - Circuit topology (graph structure unchanged)
    - External pins (VDD, VSS, ports)
    - Net nodes (NET1-50)
    - Edge types (M_D, M_G, etc.)
    - Circuit type token
    
    Args:
        sequence: List of token strings representing a circuit
        seed: Random seed for reproducible renaming
    Returns:
        List of tokens with renamed device numbers
    """
    if seed is not None:
        random.seed(seed)
    
    # Build renaming mapping for each device type
    device_mappings = {}
    
    # First pass: Identify all unique devices in sequence
    devices_used = {dtype: set() for dtype in DEVICE_CONFIGS.keys()}
    
    for token in sequence:
        # Skip protected tokens (external pins, circuit types, edges, nets)
        if (token in EXTERNAL_PINS or 
            token in CIRCUIT_TYPES or 
            token in EDGE_TYPES or
            NET_PATTERN.match(token)):
            continue
        
        device_type, device_num = parse_device_token(token)
        if device_type is not None:
            devices_used[device_type].add(device_num)
    
    # Create random permutation mapping for each device type
    for device_type, nums_used in devices_used.items():
        if len(nums_used) > 0:
            max_num = DEVICE_CONFIGS[device_type]['max']
            # Handle sequences with more devices than vocabulary limit
            actual_max = max(max(nums_used), max_num)
            
            # Create shuffled permutation
            available = list(range(1, actual_max + 1))
            random.shuffle(available)
            
            # Map original numbers to shuffled numbers
            sorted_used = sorted(list(nums_used))
            device_mappings[device_type] = {
                old: available[i] for i, old in enumerate(sorted_used)
            }
    
    # Second pass: Apply renaming to all device tokens
    new_sequence = []
    for token in sequence:
        # Preserve protected tokens unchanged
        if (token in EXTERNAL_PINS or 
            token in CIRCUIT_TYPES or 
            token in EDGE_TYPES or
            NET_PATTERN.match(token)):
            new_sequence.append(token)
            continue
        
        # Apply renaming to device tokens
        device_type, device_num = parse_device_token(token)
        
        if device_type is not None and device_num is not None:
            # Rename device using mapping
            new_num = device_mappings[device_type][device_num]
            new_token = f"{device_type}{new_num}"
            new_sequence.append(new_token)
        else:
            # Keep as-is
            new_sequence.append(token)
    
    return new_sequence


# =========================
# Dataset Processing
# =========================

def rename_dataset(input_file, output_file):
    """Apply device renaming augmentation to entire dataset.
    
    Processes all circuits in the dataset, applying consistent but randomized
    device renaming to each circuit independently.
    
    Args:
        input_file: Path to input .npy file (e.g., Training.npy)
        output_file: Path to output .npy file (e.g., Training_renamed.npy)
    """
    print(f"\n{'='*80}")
    print(f"Device Renaming Augmentation")
    print(f"{'='*80}")
    print(f"Input file: {input_file}")
    print(f"Output file: {output_file}")
    print(f"Loading data...")
    
    data = np.load(input_file, allow_pickle=True)
    print(f"Dataset shape: {data.shape}")
    print(f"Applying device renaming to all circuits...")
    
    renamed_data = []
    
    for i, circuit in enumerate(tqdm(data, desc="Processing circuits")):
        # Generate deterministic seed based on circuit content and index
        seed = hash((tuple(circuit), i)) % (2**31)
        renamed = randomize_device_numbers(circuit.tolist(), seed=seed)
        renamed_data.append(renamed)
    
    # Convert to numpy array
    renamed_data = np.array(renamed_data, dtype=object)
    
    print(f"\nRenaming complete")
    print(f"Output shape: {renamed_data.shape}")
    print(f"Saving to {output_file}...")
    np.save(output_file, renamed_data)
    print(f"Successfully saved\n")
    
    # Display example transformation
    print("="*80)
    print("Example Transformation (first circuit, first 40 tokens)")
    print("="*80)
    print("\nOriginal:")
    print(' -> '.join([str(t) for t in data[0][:40]]))
    print("\nRenamed:")
    print(' -> '.join([str(t) for t in renamed_data[0][:40]]))
    print("\n" + "="*80)


def main():
    parser = argparse.ArgumentParser(
        description='Rename devices with randomized numbers'
    )
    
    parser.add_argument('--input', type=str, default='Training.npy',
                       help='Input .npy file (default: Training.npy)')
    parser.add_argument('--output', type=str, default='Training_renamed.npy',
                       help='Output .npy file (default: Training_renamed.npy)')
    parser.add_argument('--test', action='store_true',
                       help='Test mode: show example without saving')
    
    args = parser.parse_args()
    
    if args.test:
        # Test mode: Demonstrate renaming on sample circuits
        print("\n" + "="*80)
        print("Test Mode: Device Renaming Demonstration")
        print("="*80)
        data = np.load(args.input, allow_pickle=True)
        
        print(f"\nOriginal Circuit 0 (first 50 tokens):")
        print("="*80)
        tokens = data[0][:50]
        for i, t in enumerate(tokens):
            print(f"{i:3d}: {t}")
        
        for version in range(2):
            print(f"\n" + "="*80)
            print(f"Renamed Version {version+1} (different random seed):")
            print("="*80)
            seed = hash((tuple(data[0]), version)) % (2**31)
            renamed = randomize_device_numbers(data[0].tolist(), seed=seed)
            for i, t in enumerate(renamed[:50]):
                print(f"{i:3d}: {t}")
        
        # Display device renaming mapping
        print("\n" + "="*80)
        print("Device Renaming Mapping Example:")
        print("="*80)
        original_devices = {}
        renamed_devices = {}
        
        seed = 0
        renamed = randomize_device_numbers(data[0].tolist(), seed=seed)
        
        for orig, ren in zip(data[0], renamed):
            dtype_orig, num_orig = parse_device_token(orig)
            dtype_ren, num_ren = parse_device_token(ren)
            if dtype_orig and dtype_orig == dtype_ren:
                if orig not in original_devices:
                    original_devices[orig] = ren
        
        for orig in sorted(original_devices.keys()):
            print(f"{orig} → {original_devices[orig]}")
            
    else:
        # Full renaming
        rename_dataset(args.input, args.output)
        
        # Also process Validation set if default args are used
        if args.input == 'Training.npy' and args.output == 'Training_renamed.npy':
            val_input = 'Validation.npy'
            val_output = 'Validation_renamed.npy'
            import os
            if os.path.exists(val_input):
                print(f"\nProcessing validation set...")
                rename_dataset(val_input, val_output)
            else:
                print(f"\nWarning: {val_input} not found, skipping validation set.")


if __name__ == '__main__':
    main()
