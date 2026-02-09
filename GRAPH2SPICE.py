"""
Bipartite Graph to SPICE Netlist Converter

Converts generated circuit sequences (bipartite graph representation) to SPICE netlists
with intelligent voltage biasing. Performs ERC validation without simulation.

Sequence Format:
    CIRCUIT_TYPE -> VSS -> edge -> device -> edge -> net -> ... -> VSS -> TRUNCATE

Biasing Strategy:
- VDD voltage: Determined by shortest conducting path from VDD to VSS
  (excludes non-conducting edges: M_B, M_G, M_BG, B_B)
- Input ports: Biased based on shortest conducting path to VSS
- Current ports (IIN/IB/IREF): Assigned current sources (±100uA by device type)
- DC operating point analysis setup

Validation:
- ERC checks: Pattern, required pins, pin-net, internal nets (4 levels)

Output:
- PySpice netlist files for valid circuits
- Statistics: Total, ERC-passed, biasing-failed
"""

import re
import os
import sys
import networkx as nx
from collections import defaultdict
from pathlib import Path

# Import ERC validation functions
from ERC import (
    parse_inference_file,
    run_rule_validation
)

# External pin patterns
EXTERNAL_PIN_PATTERNS = [
    r'^VDD$', r'^VSS$', r'^GND$',
    r'^VIN[0-9]*$', r'^VOUT[0-9]*$', r'^VB[0-9]*$',
    r'^VCM[0-9]*$', r'^VREF[0-9]*$', r'^IREF[0-9]*$', r'^VRF[0-9]*$', 
    r'^VLO[0-9]*$', r'^VCONT[0-9]*$', r'^VIF[0-9]*$', r'^VBB[0-9]*$',
    r'^IIN[0-9]*$', r'^IOUT[0-9]*$', r'^IB[0-9]*$',
]
EXTERNAL_PIN_REGEX = re.compile('|'.join(EXTERNAL_PIN_PATTERNS))

# Current port patterns (IIN, IB, IREF)
CURRENT_PORT_REGEX = re.compile(r'^(IIN|IB|IREF)[0-9]*$')

# Edge types (bipartite graph)
MOSFET_EDGES = {'M_B', 'M_D', 'M_G', 'M_S', 'M_BD', 'M_BG', 'M_BS', 'M_DG', 'M_DS', 'M_GS',
                'M_BDG', 'M_BDS', 'M_BGS', 'M_DGS', 'M_BDGS'}
BJT_EDGES = {'B_B', 'B_C', 'B_E', 'B_BC', 'B_BE', 'B_CE', 'B_BCE'}
PASSIVE_EDGES = {'R_C', 'C_C', 'L_C'}
DIODE_EDGES = {'D_P', 'D_N', 'D_NP', 'D_PN'}
ALL_EDGE_TYPES = MOSFET_EDGES | BJT_EDGES | PASSIVE_EDGES | DIODE_EDGES

# Pure non-conducting edges (only gate/body, no drain/source/collector/emitter)
# These edges cannot conduct current
PURE_NON_CONDUCTING = {'M_B', 'M_G', 'M_BG', 'B_B'}


def is_conducting_edge(edge_type):
    """
    Check if edge can conduct current
    
    Conducting edges contain drain/source/collector/emitter pins (D, S, C, E, P, N)
    Non-conducting edges are gate/body only (M_B, M_G, M_BG, B_B)
    """
    if edge_type in PURE_NON_CONDUCTING:
        return False
    # If edge contains D, S, C, E (conducting pins), it's conducting
    conducting_pins = {'D', 'S', 'C', 'E', 'P', 'N'}
    edge_pins = set(extract_pins_from_edge(edge_type))
    return bool(edge_pins & conducting_pins)

# Device patterns
DEVICE_PATTERN = re.compile(r'^(NM|PM|NPN|PNP|R|C|L|DIO)[0-9]+$')

# Device classes
class MOSFET:
    def __init__(self, name, is_pmos=False):
        self.name = name
        self.is_pmos = is_pmos
        self.D = None
        self.G = None
        self.S = None
        self.B = None

class BJT:
    def __init__(self, name, is_pnp=False):
        self.name = name
        self.is_pnp = is_pnp
        self.C = None
        self.B = None
        self.E = None

class Passive:
    def __init__(self, name, comp_type):
        self.name = name
        self.type = comp_type  # 'R', 'C', 'L'
        self.P = None
        self.N = None

class Diode:
    def __init__(self, name):
        self.name = name
        self.P = None  # Anode
        self.N = None  # Cathode


def extract_pins_from_edge(edge_type):
    """Extract pin letters from edge type (e.g., 'M_DG' -> ['D', 'G'])"""
    if edge_type.startswith('M_'):
        return list(edge_type[2:])
    elif edge_type.startswith('B_'):
        return list(edge_type[2:])
    elif edge_type.startswith('D_'):
        return list(edge_type[2:])
    elif edge_type in ['R_C', 'C_C', 'L_C']:
        return ['P', 'N']  # Passive components use P/N
    return []


def parse_bipartite_sequence(filepath):
    """
    Parse v13 bipartite graph sequence
    
    Returns:
        tokens: List of all tokens
        devices: Dict of device objects by type
        external_pins: Set of external pin names
        graph: NetworkX graph for path finding
    """
    with open(filepath, 'r') as f:
        content = f.read().strip()
    
    if not content or '->' not in content:
        return None, None, None, None
    
    tokens = [t.strip() for t in content.split('->') if t.strip()]
    
    # Remove all TRUNCATE tokens and stop at first occurrence
    cleaned_tokens = []
    for token in tokens:
        if token == 'TRUNCATE':
            break
        cleaned_tokens.append(token)
    tokens = cleaned_tokens
    
    # Remove CIRCUIT_ type if present
    if tokens and tokens[0].startswith('CIRCUIT_'):
        circuit_type = tokens[0]
        tokens = tokens[1:]
        print(f"Circuit type: {circuit_type}")
    
    # Initialize structures
    devices = {
        'NM': {}, 'PM': {}, 'NPN': {}, 'PNP': {},
        'R': {}, 'C': {}, 'L': {}, 'DIO': {}
    }
    external_pins = set()
    graph = nx.Graph()
    
    # Parse sequence: node - edge - node - edge - ...
    i = 0
    prev_node = None
    
    while i < len(tokens):
        token = tokens[i]
        
        # Check if it's an edge type
        if token in ALL_EDGE_TYPES:
            # Edge token - get next node
            if i + 1 < len(tokens):
                next_node = tokens[i + 1]
                
                # Identify and create device if next_node is a device
                if DEVICE_PATTERN.match(next_node):
                    dev_type = re.match(r'^[A-Z]+', next_node).group()
                    if dev_type in ['NM', 'PM'] and next_node not in devices[dev_type]:
                        devices[dev_type][next_node] = MOSFET(next_node, is_pmos=(dev_type == 'PM'))
                    elif dev_type in ['NPN', 'PNP'] and next_node not in devices[dev_type]:
                        devices[dev_type][next_node] = BJT(next_node, is_pnp=(dev_type == 'PNP'))
                    elif dev_type in ['R', 'C', 'L'] and next_node not in devices[dev_type]:
                        devices[dev_type][next_node] = Passive(next_node, dev_type)
                    elif dev_type == 'DIO' and next_node not in devices['DIO']:
                        devices['DIO'][next_node] = Diode(next_node)
                    
                    graph.add_node(next_node, node_type='device')
                
                # Check if next_node is external pin
                elif EXTERNAL_PIN_REGEX.match(next_node):
                    external_pins.add(next_node)
                    graph.add_node(next_node, node_type='port')
                
                # Otherwise it's a NET
                else:
                    graph.add_node(next_node, node_type='net')
                
                # Add edge to graph
                if prev_node and next_node:
                    # Check if edge can conduct current
                    is_conducting = is_conducting_edge(token)
                    graph.add_edge(prev_node, next_node, 
                                 edge_type=token, 
                                 conducting=is_conducting)
                
                prev_node = next_node
                i += 2
            else:
                break
        else:
            # Node token (device, net, or port)
            if DEVICE_PATTERN.match(token):
                # Device node - create device object
                dev_type = re.match(r'^[A-Z]+', token).group()
                if dev_type in ['NM', 'PM'] and token not in devices[dev_type]:
                    devices[dev_type][token] = MOSFET(token, is_pmos=(dev_type == 'PM'))
                elif dev_type in ['NPN', 'PNP'] and token not in devices[dev_type]:
                    devices[dev_type][token] = BJT(token, is_pnp=(dev_type == 'PNP'))
                elif dev_type in ['R', 'C', 'L'] and token not in devices[dev_type]:
                    devices[dev_type][token] = Passive(token, dev_type)
                elif dev_type == 'DIO' and token not in devices['DIO']:
                    devices['DIO'][token] = Diode(token)
                
                graph.add_node(token, node_type='device')
                
            elif EXTERNAL_PIN_REGEX.match(token):
                # External pin (port)
                external_pins.add(token)
                graph.add_node(token, node_type='port')
                
            else:
                # NET node
                graph.add_node(token, node_type='net')
            
            prev_node = token
            i += 1
    
    # Convert to lists for compatibility
    devices = {k: list(v.values()) for k, v in devices.items()}
    
    print(f"Parsed {len(tokens)} tokens")
    print(f"Devices: {sum(len(v) for v in devices.values())}")
    print(f"External pins: {len(external_pins)}")
    print(f"Graph nodes: {graph.number_of_nodes()}, edges: {graph.number_of_edges()}")
    
    return tokens, devices, sorted(external_pins), graph


def find_shortest_path_conducting(graph, source, target):
    """
    Find shortest path using only conducting edges
    
    Excludes non-conducting edges (M_B, M_G, M_BG, B_B) to find actual
    current-carrying paths for voltage bias calculations.
    
    Returns:
        Number of hops in shortest path, or None if no path exists
    """
    try:
        # Create subgraph with only conducting edges
        conducting_edges = [(u, v) for u, v, d in graph.edges(data=True) 
                          if d.get('conducting', True)]
        subgraph = graph.edge_subgraph(conducting_edges)
        
        path = nx.shortest_path(subgraph, source, target)
        return len(path) - 1  # Return number of hops
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return None


def assign_device_pins(tokens, devices, graph):
    """
    Assign nets to device pins from bipartite graph structure
    
    Pin assignment order for passives (R, C, L):
    - First connection -> P (positive/first terminal)
    - Second connection -> N (negative/second terminal)
    
    Args:
        tokens: Sequence tokens
        devices: Device dictionary by type
        graph: NetworkX graph
    """
    # Build device lookup for faster access
    device_lookup = {}
    for dev_type, dev_list in devices.items():
        for dev in dev_list:
            device_lookup[dev.name] = dev
    
    # Track device-edge-net connections
    i = 0
    while i < len(tokens) - 2:
        token1 = tokens[i]
        edge_type = tokens[i + 1]
        token2 = tokens[i + 2]
        
        # Skip if not valid edge type
        if edge_type not in ALL_EDGE_TYPES:
            i += 1
            continue
        
        # Check if token1 is device and token2 is net/port
        is_device1 = token1 in device_lookup
        is_device2 = token2 in device_lookup
        
        if is_device1 and not is_device2:
            # device -> edge -> net/port
            device_name = token1
            net_name = token2
            pins = extract_pins_from_edge(edge_type)
            
            dev = device_lookup[device_name]
            
            # For passive devices (R, C, L), assign in order: first connection = P, second = N
            # Skip if net_name is already assigned to prevent duplicates
            if isinstance(dev, Passive):
                if dev.P is None:
                    dev.P = net_name
                elif dev.N is None and net_name != dev.P:
                    dev.N = net_name
                # If both assigned or net already assigned, skip
            else:
                # For active devices, use pin names from edge type
                for pin in pins:
                    if hasattr(dev, pin):
                        current_val = getattr(dev, pin)
                        if current_val is None:
                            setattr(dev, pin, net_name)
            
            i += 2
        
        elif not is_device1 and is_device2:
            # net/port -> edge -> device
            net_name = token1
            device_name = token2
            pins = extract_pins_from_edge(edge_type)
            
            dev = device_lookup[device_name]
            
            # For passive devices (R, C, L), assign in order: first connection = P, second = N
            # Skip if net_name is already assigned to prevent duplicates
            if isinstance(dev, Passive):
                if dev.P is None:
                    dev.P = net_name
                elif dev.N is None and net_name != dev.P:
                    dev.N = net_name
                # If both assigned or net already assigned, skip
            else:
                # For active devices, use pin names from edge type
                for pin in pins:
                    if hasattr(dev, pin):
                        current_val = getattr(dev, pin)
                        if current_val is None:
                            setattr(dev, pin, net_name)
            
            i += 2
        else:
            i += 1


def calculate_bias_voltages(external_pins, graph, devices, vdd_voltage):
    """
    Calculate bias voltages for external pins based on connected device types
    - NMOS/NPN connected: Use VSS reference (path_to_VSS)
    - PMOS/PNP connected: Use VDD reference (VDD - path_to_VDD)
    - Mixed or no devices: Use VSS reference as default
    """
    bias_voltages = {}
    
    if 'VSS' not in graph:
        print("Warning: VSS not found in graph")
        return bias_voltages
    
    # Build device lookup
    device_lookup = {}
    for dev_type, dev_list in devices.items():
        for dev in dev_list:
            device_lookup[dev.name] = (dev, dev_type)
    
    for pin in external_pins:
        if pin in ['VSS', 'VDD']:
            continue
        
        if pin not in graph:
            bias_voltages[pin] = 2  # Default
            continue
        
        # Count connected device types (NMOS/NPN vs PMOS/PNP)
        nmos_count = 0
        pmos_count = 0
        
        for neighbor in graph.neighbors(pin):
            if neighbor in device_lookup:
                dev, dev_type = device_lookup[neighbor]
                edge_data = graph.get_edge_data(pin, neighbor)
                
                if edge_data:
                    edge_type = edge_data.get('edge_type', '')
                    
                    # Count all device connections (including gate/base)
                    if dev_type == 'NM':
                        # NMOS: Count D, S, G connections (exclude body-only connections)
                        if 'D' in edge_type or 'S' in edge_type or 'G' in edge_type:
                            nmos_count += 1
                    elif dev_type == 'PM':
                        # PMOS: Count D, S, G connections (exclude body-only connections)
                        if 'D' in edge_type or 'S' in edge_type or 'G' in edge_type:
                            pmos_count += 1
                    elif dev_type == 'NPN':
                        # NPN: Count C, E, B connections
                        if 'C' in edge_type or 'E' in edge_type or 'B' in edge_type:
                            nmos_count += 1
                    elif dev_type == 'PNP':
                        # PNP: Count C, E, B connections
                        if 'C' in edge_type or 'E' in edge_type or 'B' in edge_type:
                            pmos_count += 1
        
        # Determine bias voltage based on device type majority
        try:
            if pmos_count > nmos_count and vdd_voltage is not None and 'VDD' in graph:
                # PMOS/PNP dominant: Use VDD reference
                path_to_vdd = nx.shortest_path_length(graph, pin, 'VDD')
                bias_voltage = vdd_voltage - path_to_vdd
                print(f"  {pin}: {pmos_count} PMOS/PNP, path to VDD = {path_to_vdd} → {bias_voltage}V (VDD reference)")
                bias_voltages[pin] = bias_voltage
            else:
                # NMOS/NPN dominant or equal: Use VSS reference (default)
                path_to_vss = nx.shortest_path_length(graph, pin, 'VSS')
                bias_voltage = path_to_vss
                if pmos_count > nmos_count and (vdd_voltage is None or 'VDD' not in graph):
                    # Warning: PMOS dominant but no VDD available
                    print(f"  {pin}: {pmos_count} PMOS/PNP but NO VDD, using VSS = {path_to_vss} → {bias_voltage}V (VSS fallback)")
                elif nmos_count > 0 or pmos_count > 0:
                    print(f"  {pin}: {nmos_count} NMOS/NPN, path to VSS = {path_to_vss} → {bias_voltage}V (VSS reference)")
                bias_voltages[pin] = bias_voltage
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            # Default to 2V if no path
            bias_voltages[pin] = 2
            print(f"  {pin}: No path to VSS/VDD → 2V (default)")
    
    return bias_voltages


def determine_vdd_voltage(graph):
    """
    Determine VDD voltage based on shortest conducting path from VDD to VSS
    """
    if 'VDD' not in graph or 'VSS' not in graph:
        return None
    
    path_length = find_shortest_path_conducting(graph, 'VDD', 'VSS')
    
    if path_length is None:
        print("Warning: No conducting path from VDD to VSS")
        return None
    
    vdd_voltage = path_length
    print(f"VDD voltage set to {vdd_voltage}V (shortest path: {path_length} hops)")
    
    return vdd_voltage


def count_conducting_paths_to_vss(port_name, graph, max_paths=10):
    """
    Count number of conducting paths from port to VSS
    Uses DFS to find all simple paths through conducting edges only
    
    Args:
        port_name: Starting port (e.g., IIN1, IB1)
        graph: NetworkX graph
        max_paths: Maximum number of paths to count (to avoid exponential explosion)
    
    Returns:
        Number of conducting paths (capped at max_paths)
    """
    if port_name not in graph or 'VSS' not in graph:
        return 1  # Default to 1 path
    
    try:
        # Create subgraph with only conducting edges
        conducting_edges = [(u, v) for u, v, d in graph.edges(data=True) 
                          if d.get('conducting', True)]
        subgraph = graph.edge_subgraph(conducting_edges)
        
        # Find all simple paths from port to VSS
        paths = list(nx.all_simple_paths(subgraph, port_name, 'VSS', cutoff=20))
        
        # Count paths (cap at max_paths to avoid huge numbers)
        path_count = min(len(paths), max_paths)
        
        return max(path_count, 1)  # At least 1 path
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return 1  # Default to 1 path


def determine_current_source_value(port_name, graph, devices):
    """
    Determine current source value for input current ports
    
    All input current ports (IIN, IB, IREF) use uniform 100uA value.
    
    Returns:
        100e-6 (100uA)
    """
    return 100e-6


def generate_pyspice_code(output_path, devices, external_pins, bias_voltages, vdd_voltage, graph, circuit_name):
    """
    Generate PySpice netlist with intelligent voltage biasing
    
    Args:
        output_path: Output file path
        devices: Dictionary of device objects by type
        external_pins: List of external port names
        bias_voltages: Dictionary of calculated bias voltages
        vdd_voltage: VDD supply voltage (or None)
        graph: NetworkX graph
        circuit_name: Circuit identifier
    """
    lines = []
    lines.append("from PySpice.Spice.Netlist import Circuit")
    lines.append("from PySpice.Unit import *")
    lines.append("")
    lines.append(f"# Generated circuit: {circuit_name}")
    lines.append(f"circuit = Circuit('{circuit_name}')")
    lines.append("")
    
    # Add device models first
    lines.append("# Device models")
    if devices['NM'] or devices['PM']:
        lines.append("circuit.model('nmos', 'nmos', level=1, kp=120e-6, vto=0.4)")
        lines.append("circuit.model('pmos', 'pmos', level=1, kp=40e-6, vto=-0.4)")
    if devices['NPN'] or devices['PNP']:
        lines.append("circuit.model('npn', 'npn', bf=100, is_=1e-14, vaf=100)")
        lines.append("circuit.model('pnp', 'pnp', bf=50, is_=1e-14, vaf=50)")
    if devices['DIO']:
        lines.append("circuit.model('diode', 'diode', is_=1e-14, n=1.0)")
    lines.append("")
    
    # Add VDD and VSS
    lines.append("# Power supplies")
    if vdd_voltage and 'VDD' in external_pins:
        lines.append(f"circuit.V('dd', 'VDD', circuit.gnd, {vdd_voltage}@u_V)")
    lines.append("circuit.V('ss', 'VSS', circuit.gnd, 0@u_V)")
    lines.append("")
    
    # Separate voltage pins, current pins, and output current pins
    output_current_ports = [pin for pin in external_pins if pin.startswith('IOUT')]
    current_ports = [pin for pin in external_pins if CURRENT_PORT_REGEX.match(pin)]  # IIN, IB, IREF
    voltage_pins = [pin for pin in bias_voltages.keys() 
                   if not pin.startswith('VOUT') and not pin.startswith('IOUT') 
                   and pin not in current_ports]
    
    # Add voltage sources for input voltage pins
    if voltage_pins:
        lines.append("# Input voltage sources")
        for pin in sorted(voltage_pins):
            voltage = bias_voltages[pin]
            lines.append(f"circuit.V('{pin.lower()}', '{pin}', circuit.gnd, {voltage}@u_V)")
        lines.append("")
    
    # Add current sources for input current pins (IIN, IB, IREF) - uniform 100uA
    if current_ports:
        lines.append("# Input current sources (100uA uniform)")
        for pin in sorted(current_ports):
            lines.append(f"circuit.I('{pin.lower()}', circuit.gnd, '{pin}', 100@u_uA)")
        lines.append("")
    
    # Add load resistors for output current ports (IOUT) - 10kΩ to VSS
    if output_current_ports:
        lines.append("# Output current port load resistors (10kΩ to VSS)")
        for pin in sorted(output_current_ports):
            lines.append(f"circuit.R('{pin.lower()}_load', '{pin}', 'VSS', 10@u_kOhm)")
        lines.append("")
    
    # Add MOSFETs
    if devices['NM'] or devices['PM']:
        lines.append("# MOSFETs")
        for dev in devices['NM']:
            if all([dev.D, dev.G, dev.S, dev.B]):
                lines.append(f"circuit.MOSFET('{dev.name}', '{dev.D}', '{dev.G}', '{dev.S}', '{dev.B}', model='nmos', w=10@u_um, l=1@u_um)")
        for dev in devices['PM']:
            if all([dev.D, dev.G, dev.S, dev.B]):
                lines.append(f"circuit.MOSFET('{dev.name}', '{dev.D}', '{dev.G}', '{dev.S}', '{dev.B}', model='pmos', w=15@u_um, l=1@u_um)")
        lines.append("")
    
    # Add BJTs
    if devices['NPN'] or devices['PNP']:
        lines.append("# BJTs")
        for dev in devices['NPN']:
            if all([dev.C, dev.B, dev.E]):
                lines.append(f"circuit.BJT('{dev.name}', '{dev.C}', '{dev.B}', '{dev.E}', model='npn')")
        for dev in devices['PNP']:
            if all([dev.C, dev.B, dev.E]):
                lines.append(f"circuit.BJT('{dev.name}', '{dev.C}', '{dev.B}', '{dev.E}', model='pnp')")
        lines.append("")
    
    # Add resistors
    if devices['R']:
        lines.append("# Resistors")
        for dev in devices['R']:
            if dev.P and dev.N:
                lines.append(f"circuit.R('{dev.name}', '{dev.P}', '{dev.N}', 10@u_kΩ)")
        lines.append("")
    
    # Add load resistors for IOUT pins
    if output_current_ports:
        if not devices['R']:  # Add header if not already added
            lines.append("# Resistors")
        for pin in sorted(output_current_ports):
            load_name = f"R_load_{pin.lower()}"
            lines.append(f"circuit.R('{load_name}', '{pin}', 'VSS', 10@u_kΩ)")
        lines.append("")
    
    # Add capacitors
    if devices['C']:
        lines.append("# Capacitors")
        for dev in devices['C']:
            if dev.P and dev.N:
                lines.append(f"circuit.C('{dev.name}', '{dev.P}', '{dev.N}', 1@u_pF)")
        lines.append("")
    
    # Add inductors
    if devices['L']:
        lines.append("# Inductors")
        for dev in devices['L']:
            if dev.P and dev.N:
                lines.append(f"circuit.L('{dev.name}', '{dev.P}', '{dev.N}', 1@u_uH)")
        lines.append("")
    
    # Add diodes
    if devices['DIO']:
        lines.append("# Diodes")
        for dev in devices['DIO']:
            if dev.P and dev.N:
                lines.append(f"circuit.Diode('{dev.name}', '{dev.P}', '{dev.N}', model='diode')")
        lines.append("")
    
    # Add simulation
    lines.append("# DC Operating Point Analysis")
    lines.append("simulator = circuit.simulator(temperature=25, nominal_temperature=25)")
    lines.append("analysis = simulator.operating_point()")
    lines.append("")
    lines.append("# Print results")
    lines.append("for node in analysis.nodes.values():")
    lines.append("    print(f'{str(node)}: {float(node):.3f}V')")
    
    # Write to file
    with open(output_path, 'w') as f:
        f.write('\n'.join(lines))
    
    print(f"Generated PySpice code: {output_path}")
    
    # Adjust MOSFET widths based on parallel connections
    adjust_mosfet_widths(output_path, devices, graph)


def adjust_mosfet_widths(py_file, devices, graph):
    """
    Adjust MOSFET widths based on parallel connections at drain nets.
    
    Algorithm:
    1. For each MOSFET, find its drain net
    2. Find all other MOSFETs of the same type connected to that drain net via their source
    3. Sum the widths of those parallel MOSFETs
    4. Set this MOSFET's width to that sum
    
    This is done iteratively until widths stabilize.
    """
    print("Adjusting MOSFET widths based on parallel connections...")
    
    # Read the generated Python file
    with open(py_file, 'r') as f:
        lines = f.readlines()
    
    # Initialize width dictionary with default values
    widths = {}
    for dev in devices['NM']:
        widths[dev.name] = 10  # NMOS default
    for dev in devices['PM']:
        widths[dev.name] = 15  # PMOS default
    
    # Iteratively adjust widths (max 10 iterations)
    max_iterations = 10
    for iteration in range(max_iterations):
        old_widths = widths.copy()
        
        # Process NMOS devices
        for dev in devices['NM']:
            if not all([dev.D, dev.S]):
                continue
            
            drain_net = dev.D
            
            # Find other NMOS devices with source connected to this drain net
            parallel_widths = []
            for other_dev in devices['NM']:
                if other_dev.name == dev.name:
                    continue  # Skip self
                if other_dev.S == drain_net:
                    parallel_widths.append(widths[other_dev.name])
            
            # Set width to sum of parallel widths (or keep default if no parallel devices)
            if parallel_widths:
                widths[dev.name] = sum(parallel_widths)
        
        # Process PMOS devices
        for dev in devices['PM']:
            if not all([dev.D, dev.S]):
                continue
            
            drain_net = dev.D
            
            # Find other PMOS devices with source connected to this drain net
            parallel_widths = []
            for other_dev in devices['PM']:
                if other_dev.name == dev.name:
                    continue  # Skip self
                if other_dev.S == drain_net:
                    parallel_widths.append(widths[other_dev.name])
            
            # Set width to sum of parallel widths (or keep default if no parallel devices)
            if parallel_widths:
                widths[dev.name] = sum(parallel_widths)
        
        # Check if widths have stabilized
        if widths == old_widths:
            print(f"  Widths stabilized after {iteration + 1} iteration(s)")
            break
    
    # Update the Python file with new widths
    updated_lines = []
    for line in lines:
        updated_line = line
        
        # Check if this is a MOSFET line
        if 'circuit.MOSFET(' in line:
            # Extract device name
            match = re.search(r"'([NP]M\d+)'", line)
            if match:
                dev_name = match.group(1)
                if dev_name in widths:
                    # Replace width value
                    new_width = widths[dev_name]
                    updated_line = re.sub(r'w=\d+@u_um', f'w={new_width}@u_um', line)
        
        updated_lines.append(updated_line)
    
    # Write updated file
    with open(py_file, 'w') as f:
        f.writelines(updated_lines)
    
    # Print width changes
    changed_count = 0
    for dev_name, width in sorted(widths.items()):
        default_width = 10 if dev_name.startswith('NM') else 15
        if width != default_width:
            print(f"  {dev_name}: {default_width}um → {width}um")
            changed_count += 1
    
    if changed_count == 0:
        print("  No width adjustments needed")
    else:
        print(f"  Adjusted {changed_count} MOSFET(s)")


def process_file(filepath, output_dir):
    """
    Process single inference file with ERC validation (no simulation)
    
    Workflow:
    1. Run ERC validation (4 tests)
    2. Parse sequence to graph
    3. Calculate VDD and bias voltages
    4. Generate PySpice netlist
    
    Returns:
        True if ERC passed and file saved, False otherwise
    """
    print(f"\n{'='*70}")
    print(f"Processing: {filepath}")
    print(f"{'='*70}")
    
    # Step 1: Run ERC validation first
    print("Running ERC validation...")
    try:
        erc_tokens, circuit_type = parse_inference_file(str(filepath))
        is_clean, violations_1, violations_2, violations_3, violations_4 = run_rule_validation(
            erc_tokens, verbose=False, debug=False
        )
        
        if not is_clean:
            total_violations = len(violations_1) + len(violations_2) + len(violations_3) + len(violations_4)
            print(f"ERC FAILED: {total_violations} violations")
            print(f"  Test 1 (Pattern): {len(violations_1)} violations")
            print(f"  Test 2 (Pin Completion): {len(violations_2)} violations")
            print(f"  Test 3 (Unique Nets): {len(violations_3)} violations")
            print(f"  Test 4 (Net Connections): {len(violations_4)} violations")
            return False
        
        print("ERC PASSED - All tests passed")
    except Exception as e:
        print(f"ERC validation error: {e}")
        return False
    
    # Step 2: Parse sequence for SPICE conversion
    tokens, devices, external_pins, graph = parse_bipartite_sequence(filepath)
    
    if tokens is None or not devices or not graph:
        print("Failed to parse file")
        return False
    
    # Assign device pins
    assign_device_pins(tokens, devices, graph)
    
    # Calculate VDD voltage
    vdd_voltage = determine_vdd_voltage(graph)
    
    # Check if circuit has current sources (IIN, IB, etc.)
    current_ports = [pin for pin in external_pins if CURRENT_PORT_REGEX.match(pin)]
    
    # If no VDD voltage AND no current sources, skip
    if vdd_voltage is None and not current_ports:
        print("No VDD path to VSS and no current sources, skipping...")
        return False
    
    # If no VDD, set to None (circuit will work with current sources only)
    if vdd_voltage is None:
        print("Warning: No VDD path, but has current sources - proceeding...")
    
    # Calculate bias voltages (for both voltage and current ports)
    print("Calculating bias voltages...")
    bias_voltages = calculate_bias_voltages(external_pins, graph, devices, vdd_voltage)
    
    # Generate PySpice code
    filename = Path(filepath).stem
    output_path = output_dir / f"{filename}.py"
    circuit_name = filename
    
    generate_pyspice_code(output_path, devices, external_pins, bias_voltages, 
                         vdd_voltage, graph, circuit_name)
    
    # No simulation test - just save the file
    print("PySpice code generated (no simulation test)")
    return True


def main():
    if len(sys.argv) < 2:
        print("Usage: python GRAPH2SPICE_no_sim.py <input_folder>")
        print("Example: python GRAPH2SPICE_no_sim.py Inference_CIRCUIT_Opamp_masked")
        sys.exit(1)
    
    input_folder = Path(sys.argv[1])
    
    if not input_folder.exists():
        print(f"Error: Folder '{input_folder}' does not exist")
        sys.exit(1)
    
    # Create output directory
    folder_name = input_folder.name
    output_dir = input_folder.parent / f"SPICE_{folder_name}"
    output_dir.mkdir(exist_ok=True)
    
    # Get all .txt files
    txt_files = sorted(input_folder.glob("run*.txt"))
    
    if not txt_files:
        print(f"Error: No run*.txt files found in '{input_folder}'")
        sys.exit(1)
    
    print(f"Found {len(txt_files)} files to process")
    print(f"Output directory: {output_dir}\n")
    
    erc_pass_count = 0
    total_fail_count = 0
    
    for txt_file in txt_files:
        try:
            if process_file(txt_file, output_dir):
                erc_pass_count += 1
                print(f"[SAVED] {txt_file.name}")
            else:
                total_fail_count += 1
                print(f"[SKIPPED] {txt_file.name}")
        except Exception as e:
            total_fail_count += 1
            print(f"[ERROR] {txt_file.name}: {e}")
    
    print(f"\n{'='*70}")
    print(f"Conversion Results (No Simulation Test)")
    print(f"{'='*70}")
    print(f"Total files:              {len(txt_files)}")
    print(f"ERC Passed & Saved:       {erc_pass_count} ({erc_pass_count/len(txt_files)*100:.1f}%)")
    print(f"Failed (ERC):             {total_fail_count} ({total_fail_count/len(txt_files)*100:.1f}%)")
    print(f"\nSaved circuits:           {erc_pass_count}")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
