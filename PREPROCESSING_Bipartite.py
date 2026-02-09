"""
Bipartite Graph Preprocessing for Analog Circuits

This script converts SPICE netlist files (.cir) into bipartite graph representations
with typed edges, saved as adjacency matrices in CSV format.

Bipartite Graph Structure:
- Device nodes: MOSFETs (NM1, PM1), BJTs (NPN1, PNP1), passives (R1, C1, L1), diodes (DIO1)
- Net nodes: External ports (VIN1, VOUT, VDD, VSS) and internal nets (NET1, NET2, ...)
- Typed edges: Encode pin-level connections (e.g., M_D, M_G, M_SB for MOSFETs)

Example Transformation:
  Input netlist:  MM9 (VOUT1 net12 VSS VSS) nmos4
  Output graph:
    - Device node: NM9
    - Typed edges: NM9 -[M_D]-> VOUT1, NM9 -[M_G]-> NET1, NM9 -[M_SB]-> VSS
    - CSV entry: adj[NM9][VOUT1] = "M_D", adj[NM9][NET1] = "M_G", adj[NM9][VSS] = "M_SB"

Key Features:
- Filters out digital components (e.g., logic gates, clock signals)
- Normalizes internal net names to consistent NET1, NET2, ... format
- Validates electrical connectivity (e.g., MOSFETs must have G, D, S, B pins)
- Generates adjacency matrix with typed edges for each circuit
"""

import os
import re
import csv
import pandas as pd
from collections import defaultdict
from tqdm import tqdm

# =========================
# Configuration: Digital Component Filtering
# =========================
# Pin names indicating digital logic - circuits with these are excluded
DIGITAL_PINS = [
    'VCLK', 'LOGICA', 'LOGICB', 'LOGICD', 'LOGICF', 'LOGICG', 
    'LOGICQ', 'LOGICQA', 'LOGICQB', 'VLATCH', 'VHOLD', 'VTRACK'
]

# Device types indicating digital logic - circuits with these are excluded
DIGITAL_DEVICES = [
    'XOR', 'PFD', 'INVERTER', 'TRANSMISSION_GATE'
]

# =========================
# Device Type Mappings
# =========================
# Map SPICE device types to standardized prefixes
DEVICE_TYPES = {
    'nmos4': 'NM',
    'nmos': 'NM',
    'pmos4': 'PM',
    'pmos': 'PM',
    'npn': 'NPN',
    'pnp': 'PNP',
    'resistor': 'R',
    'capacitor': 'C',
    'inductor': 'L',
    'diode': 'DIO'
}

# Pin ordering for each device type (as specified in SPICE netlist)
DEVICE_PINS = {
    'nmos4': ['D', 'G', 'S', 'B'],
    'nmos': ['D', 'G', 'S', 'B'],
    'pmos4': ['D', 'G', 'S', 'B'],
    'pmos': ['D', 'G', 'S', 'B'],
    'npn': ['C', 'B', 'E'],
    'pnp': ['C', 'B', 'E'],
    'resistor': ['C', 'C'],
    'capacitor': ['C', 'C'],
    'inductor': ['C', 'C'],
    'diode': ['P', 'N']
}

# Prefix for typed edge generation (used to create M_D, B_C, R_C, etc.)
DEVICE_PIN_PREFIX = {
    'NM': 'M',  # MOSFET: M_D, M_G, M_S, M_B
    'PM': 'M',
    'NPN': 'B',  # BJT: B_C, B_B, B_E
    'PNP': 'B',
    'DIO': 'D',  # Diode: D_P, D_N
    'R': 'R',   # Resistor: R_C
    'C': 'C',   # Capacitor: C_C
    'L': 'L'    # Inductor: L_C
}


# =========================
# Parsing Functions
# =========================

def parse_cir_line(line):
    """Parse a single line from SPICE netlist (.cir file).
    
    Expected format: DEVICE_NAME (NET1 NET2 ...) DEVICE_TYPE
    
    Args:
        line: Single line from .cir file
    Returns:
        Tuple of (device_name, nets, device_type) or None if parsing fails
    Example:
        Input:  "MM9 (VOUT1 net12 VSS VSS) nmos4"
        Output: ('MM9', ['VOUT1', 'net12', 'VSS', 'VSS'], 'nmos4')
    """
    line = line.strip()
    if not line or line.startswith('*'):
        return None
    
    # Pattern: DEVICE_NAME (NET1 NET2 ...) DEVICE_TYPE
    match = re.match(r'(\S+)\s*\((.*?)\)\s*(\S+)', line)
    if not match:
        return None
    
    device_name = match.group(1)
    nets_str = match.group(2)
    device_type = match.group(3)
    
    # Parse nets
    nets = nets_str.split()
    
    return device_name, nets, device_type


def has_digital_component(nets):
    """Check if any net name contains digital logic keywords.
    
    Args:
        nets: List of net names
    Returns:
        True if digital component detected, False otherwise
    """
    for net in nets:
        net_upper = net.upper()
        for digital_pin in DIGITAL_PINS:
            if digital_pin in net_upper:
                return True
    return False


# =========================
# Net Name Normalization
# =========================

def normalize_net_names(nets_set):
    """Normalize internal net names to consistent NET1, NET2, ... format.
    
    External ports (VDD, VSS, VIN, VOUT, etc.) are preserved as-is.
    Internal nets (e.g., net123, net_45) are renamed to NET1, NET2, ...
    
    Args:
        nets_set: Set of all net names in the circuit
    Returns:
        Dictionary mapping original net name to normalized name
    """
    external_pins = set()
    internal_nets = []
    
    for net in nets_set:
        net_upper = net.upper()
        
        # Check if external pin
        if net_upper in ['VDD', 'VSS']:
            external_pins.add(net)
        elif any(net_upper.startswith(prefix) for prefix in 
                ['VIN', 'VOUT', 'IIN', 'IOUT', 'VB', 'IB', 'VCONT', 
                 'VCM', 'IREF', 'VRF', 'VLO', 'VIF', 'VBB', 'VREF']):
            external_pins.add(net)
        else:
            # Internal net (net123, net_45, etc.)
            internal_nets.append(net)
    
    # Sort internal nets for consistent ordering
    internal_nets.sort()
    
    # Create mapping
    net_mapping = {}
    for net in external_pins:
        net_mapping[net] = net  # Keep external pins unchanged
    
    for i, net in enumerate(internal_nets, start=1):
        net_mapping[net] = f'NET{i}'
    
    return net_mapping


# =========================
# Validation Functions
# =========================

def validate_device_connections(devices, edges, net_mapping):
    """Validate electrical connectivity of all devices in the circuit.
    
    Ensures:
    - MOSFETs have all 4 pins (G, D, S, B) connected
    - BJTs have all 3 pins (B, E, C) connected
    - Diodes have both pins (P, N) connected
    - Passives connect to exactly 2 different nets
    
    Args:
        devices: List of (device_vertex, device_type_raw, nets) tuples
        edges: List of (device_vertex, net_vertex, pin_type) tuples
        net_mapping: Dictionary mapping original to normalized net names
    Returns:
        Tuple of (is_valid, error_message)
    """
    # Build connection map for validation
    device_connections = defaultdict(dict)
    
    for device_vertex, net_vertex, pin_type in edges:
        device_connections[device_vertex][net_vertex] = pin_type
    
    # Check each device for required pin connectivity
    for device_vertex, device_type_raw, nets in devices:
        device_type = DEVICE_TYPES[device_type_raw]
        connections = device_connections[device_vertex]
        
        if len(connections) == 0:
            return False, f"{device_vertex} has no connections"
        
        if device_type in ['NM', 'PM']:
            # MOSFET validation: must have all 4 pins (G, D, S, B)
            # Extract individual pins from typed edges (e.g., M_D -> D, M_SB -> S and B)
            all_pins = set()
            for pin_type in connections.values():
                if pin_type.startswith('M_'):
                    pins_part = pin_type[2:]  # Remove 'M_' prefix
                    all_pins.update(list(pins_part))
            
            required_pins = {'G', 'B', 'D', 'S'}
            if not required_pins.issubset(all_pins):
                missing = required_pins - all_pins
                return False, f"{device_vertex} missing MOSFET pins: {missing}, found: {all_pins}"
        
        elif device_type in ['NPN', 'PNP']:
            # BJT validation: must have all 3 pins (B, E, C)
            all_pins = set()
            for pin_type in connections.values():
                if pin_type.startswith('B_'):
                    pins_part = pin_type[2:]  # Remove 'B_' prefix
                    all_pins.update(list(pins_part))
            
            required_pins = {'B', 'E', 'C'}
            if not required_pins.issubset(all_pins):
                missing = required_pins - all_pins
                return False, f"{device_vertex} missing BJT pins: {missing}, found: {all_pins}"
        
        elif device_type == 'DIO':
            # Diode validation: must have both pins (P, N)
            all_pins = set()
            for pin_type in connections.values():
                if pin_type.startswith('D_'):
                    pins_part = pin_type[2:]  # Remove 'D_' prefix
                    all_pins.update(list(pins_part))
            
            required_pins = {'P', 'N'}
            if not required_pins.issubset(all_pins):
                missing = required_pins - all_pins
                return False, f"{device_vertex} missing diode pins: {missing}, found: {all_pins}"
        
        elif device_type in ['R', 'C', 'L']:
            # Passive device validation: must connect to exactly 2 different nets
            normalized_nets = [net_mapping[net] for net in nets]
            unique_nets = set(normalized_nets)
            
            if len(unique_nets) != 2:
                return False, f"{device_vertex} ({device_type}) must connect to exactly 2 different nets, found {len(unique_nets)}: {unique_nets}"
            
            # Check that all edges have correct passive edge type (R_C, C_C, or L_C)
            expected_edge_type = f'{device_type}_C'
            for pin_type in connections.values():
                if pin_type != expected_edge_type:
                    return False, f"{device_vertex} has invalid edge type '{pin_type}', expected '{expected_edge_type}'"
    
    return True, ""


# =========================
# Bipartite Graph Construction
# =========================

def create_bipartite_graph(cir_file):
    """Convert SPICE netlist to bipartite graph with typed edges.
    
    Two-pass algorithm:
    1. First pass: Check for digital components (skip if found)
    2. Second pass: Build bipartite graph and validate connectivity
    
    Args:
        cir_file: Path to .cir SPICE netlist file
    Returns:
        Tuple of (vertices, edges, device_counter) or None if circuit should be skipped
        - vertices: List of all node names (device and net nodes)
        - edges: List of (device_vertex, net_vertex, pin_type) tuples
        - device_counter: Dictionary of device counts by type
    """
    if not os.path.exists(cir_file):
        return None
    
    # First pass: Detect and filter digital circuits
    with open(cir_file, 'r') as f:
        for line in f:
            parsed = parse_cir_line(line)
            if parsed is None:
                continue
            
            device_name, nets, device_type_raw = parsed
            
            # Skip if digital pins detected
            if has_digital_component(nets):
                return None
            
            # Skip if digital device detected
            if device_type_raw in DIGITAL_DEVICES:
                return None
    
    # Second pass: Build bipartite graph structure
    devices = []  # List of (device_vertex, device_type_raw, nets)
    device_counter = defaultdict(int)
    all_nets = set()
    
    with open(cir_file, 'r') as f:
        for line in f:
            parsed = parse_cir_line(line)
            if parsed is None:
                continue
            
            device_name, nets, device_type_raw = parsed
            
            # Check device type
            if device_type_raw not in DEVICE_TYPES:
                continue
            
            device_type = DEVICE_TYPES[device_type_raw]
            
            # Assign device number
            device_counter[device_type] += 1
            device_num = device_counter[device_type]
            device_vertex = f'{device_type}{device_num}'
            
            # Store device info
            devices.append((device_vertex, device_type_raw, nets))
            
            # Collect all nets
            all_nets.update(nets)
    
    if len(devices) == 0:
        return None
    
    # Normalize net names
    net_mapping = normalize_net_names(all_nets)
    
    # Construct bipartite graph with typed edges
    vertices = set()
    edges = []
    
    for device_vertex, device_type_raw, nets in devices:
        pins = DEVICE_PINS[device_type_raw]
        device_type = DEVICE_TYPES[device_type_raw]
        
        vertices.add(device_vertex)
        
        # Group pins by net to create typed edges (e.g., M_GD if G and D connect to same net)
        net_to_pins = defaultdict(list)
        for pin, net in zip(pins, nets):
            normalized_net = net_mapping[net]
            net_to_pins[normalized_net].append(pin)
        
        # Create typed edges based on device type and pin configuration
        for normalized_net, pin_list in net_to_pins.items():
            prefix = DEVICE_PIN_PREFIX[device_type]
            
            if device_type in ['R', 'C', 'L']:
                # Passive devices: R_C, C_C, L_C
                pin_type = f'{prefix}_C'
            elif device_type == 'DIO':
                # Diode: D_P, D_N, or D_PN (if both pins connect to same net)
                pin_list_sorted = sorted(pin_list)
                pin_suffix = ''.join(pin_list_sorted)
                pin_type = f'{prefix}_{pin_suffix}'
            else:
                # Active devices (MOSFET, BJT): M_D, M_G, M_SB, B_C, B_BE, etc.
                # Sort for consistent naming (e.g., always "BS" not "SB")
                pin_list_sorted = sorted(pin_list)
                pin_suffix = ''.join(pin_list_sorted)
                pin_type = f'{prefix}_{pin_suffix}'
            
            # Add net vertex
            vertices.add(normalized_net)
            
            # Add typed edge: (device, net, pin_type)
            edges.append((device_vertex, normalized_net, pin_type))
    
    # Validate device connections
    is_valid, error_msg = validate_device_connections(devices, edges, net_mapping)
    if not is_valid:
        print(f"Validation failed: {error_msg}")
        return None
    
    vertices = sorted(list(vertices))
    
    return vertices, edges, device_counter


# =========================
# Output Generation
# =========================

def save_adjacency_matrix(vertices, edges, output_file):
    """Save bipartite graph as adjacency matrix in CSV format.
    
    Matrix structure:
    - Rows/columns: All vertices (devices and nets)
    - Entries: '0' for no connection, or typed edge label (e.g., M_D, B_C, R_C)
    - Symmetric matrix (undirected graph)
    
    Args:
        vertices: List of all vertex names
        edges: List of (device_vertex, net_vertex, pin_type) tuples
        output_file: Path to output CSV file
    """
    n = len(vertices)
    vertex_to_idx = {v: i for i, v in enumerate(vertices)}
    
    # Initialize adjacency matrix
    adj_matrix = [['0' for _ in range(n)] for _ in range(n)]
    
    # Populate with typed edge labels
    for device_vertex, net_vertex, pin_type in edges:
        i = vertex_to_idx[device_vertex]
        j = vertex_to_idx[net_vertex]
        adj_matrix[i][j] = pin_type
        adj_matrix[j][i] = pin_type  # Undirected graph
    
    # Save as CSV
    df = pd.DataFrame(adj_matrix, index=vertices, columns=vertices)
    df.to_csv(output_file)


# =========================
# Main Processing Pipeline
# =========================

def process_dataset(dataset_dir='Dataset'):
    """Process entire dataset and convert all circuits to bipartite graphs.
    
    Processes circuit folders numbered 1 to 3502, generating CSV adjacency
    matrices for each valid analog circuit. Digital circuits are automatically
    filtered out.
    
    Args:
        dataset_dir: Root directory containing numbered circuit folders
    """
    print(f"Processing circuits from {dataset_dir}...")
    
    success_count = 0
    skip_count = 0
    error_count = 0
    
    # Process all circuit folders
    for circuit_id in tqdm(range(1, 3503), desc="Converting to bipartite graphs"):
        folder = str(circuit_id)
        folder_path = os.path.join(dataset_dir, folder)
        
        # Skip if folder doesn't exist (some numbers are missing)
        if not os.path.isdir(folder_path):
            continue
        
        cir_file = os.path.join(folder_path, f'{circuit_id}.cir')
        output_file = os.path.join(folder_path, f'Graph_Bipart{circuit_id}.csv')
        
        try:
            result = create_bipartite_graph(cir_file)
            
            if result is None:
                skip_count += 1
                continue
            
            vertices, edges, device_counter = result
            
            # Save adjacency matrix
            save_adjacency_matrix(vertices, edges, output_file)
            
            success_count += 1
            
        except Exception as e:
            error_count += 1
            print(f"\nError processing {circuit_id}: {e}")
    
    print("\n" + "="*60)
    print(f"Processing complete!")
    print(f"  Success: {success_count}")
    print(f"  Skipped: {skip_count}")
    print(f"  Errors: {error_count}")
    print("="*60)


if __name__ == '__main__':
    process_dataset('Dataset')
