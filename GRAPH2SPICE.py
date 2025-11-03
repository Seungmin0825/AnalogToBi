import re
from collections import defaultdict
from pathlib import Path
import os

"""
Sequence-to-Netlist converter and PySpice code generator.

Reads a single-line sequence (e.g. VSS->NM1_B->NM1->NM1_D->NET1->...)
Parses device list and external pins (printed to terminal), assigns nets to pins.
When two pins appear consecutively (pin -> pin), a new net x1, x2, ... is allocated
and assigned to both pins.

Generates PySpice code saved as SPICE/run{i}.py and preserves terminal output of
devices and external pins.
"""

# Define external pin patterns based on Pretrain.py
EXTERNAL_PIN_PATTERNS = [
    r'^VDD$', r'^VSS$', r'^GND$', r'^VCC$',
    r'^VIN[0-9]*$', r'^VOUT[0-9]*$', r'^VB[0-9]*$', r'^VCLK[0-9]*$', r'^CLK[0-9]*$',
    r'^VCM[0-9]*$', r'^VREF[0-9]*$', r'^IREF[0-9]*$', r'^VRF[0-9]*$', r'^VLO[0-9]*$',
    r'^VIF[0-9]*$', r'^VBB[0-9]*$', r'^LOGICA[0-9]*$', r'^LOGICB[0-9]*$', r'^LOGICD[0-9]*$',
    r'^LOGICF[0-9]*$', r'^LOGICG[0-9]*$', r'^LOGICQ[0-9]*$', r'^LOGICQA[0-9]*$', r'^LOGICQB[0-9]*$',
    r'^LOGICE[0-9]*$', r'^LOGICH[0-9]*$',
    r'^VLATCH[0-9]*$', r'^VHOLD[0-9]*$', r'^VTRACK[0-9]*$',
    r'^IIN[0-9]*$', r'^IOUT[0-9]*$', r'^IB[0-9]*$',
    r'^RESET[0-9]*$', r'^ENABLE[0-9]*$', r'^TEST[0-9]*$',
    r'^ANALOG[0-9]*$', r'^DIGITAL[0-9]*$'
]
EXTERNAL_PIN_REGEX = re.compile('|'.join(EXTERNAL_PIN_PATTERNS))

# Patterns
device_pattern = re.compile(r'^(NM|PM|NPN|PNP|R|C|L|DIO|XOR|PFD|INVERTER|TRANSMISSION_GATE)[0-9]+$')
pin_pattern = re.compile(r'^([A-Za-z0-9]+)_([A-Za-z]+)$')  # captures device and pin letter
# treat other bare uppercase tokens (not devices) as nets as well
bare_token_pattern = re.compile(r'^[A-Z][A-Z0-9]*$')

# Define a global variable to store skipped files
skipped_files = []

# Define classes for each device type
class NM:
    def __init__(self, name):
        self.name = name
        self.D = None
        self.G = None
        self.S = None
        self.B = None

class PM:
    def __init__(self, name):
        self.name = name
        self.D = None
        self.G = None
        self.S = None
        self.B = None

class NPN:
    def __init__(self, name):
        self.name = name
        self.C = None  # Collector
        self.B = None  # Base
        self.E = None  # Emitter

class PNP:
    def __init__(self, name):
        self.name = name
        self.C = None
        self.B = None
        self.E = None

class R:
    def __init__(self, name):
        self.name = name
        self.P = None  # Positive terminal
        self.N = None  # Negative terminal

class C:
    def __init__(self, name):
        self.name = name
        self.P = None
        self.N = None

class L:
    def __init__(self, name):
        self.name = name
        self.P = None
        self.N = None

class DIO:
    def __init__(self, name):
        self.name = name
        self.P = None  # Anode
        self.N = None  # Cathode

def contains_digital_circuit(filepath):
    """Check if the file contains digital circuit components."""
    digital_keywords = ["LOGIC", "XOR", "PFD", "INVERTER", "TRANSMISSION_GATE"]
    with open(filepath, 'r') as f:
        content = f.read()
    return any(keyword in content for keyword in digital_keywords)

def file_open_and_list_up(filepath):
    """Read file, extract sequence line, parse tokens, and collect devices/external pins."""
    if contains_digital_circuit(filepath):
        print(f"File {filepath} contains digital circuits. Skipping...")
        skipped_files.append(filepath)
        return None, None, None

    with open(filepath, 'r') as f:
        lines = f.readlines()

    sequence = None
    for line in lines:
        if "->" in line:
            sequence = line.strip()
            break
    if not sequence:
        return None, None

    tokens = [t.strip() for t in sequence.split("->") if t.strip()]
    devices = defaultdict(dict)  # Use a dictionary to avoid duplicates
    external_pins = set()

    # Handle optional style token at the first position (e.g., CIRCUIT_Opamp)
    style_token = None
    if len(tokens) > 0 and tokens[0].startswith('CIRCUIT_'):
        style_token = tokens[0]
        tokens_to_process = tokens[1:]
    else:
        tokens_to_process = tokens

    # If a style token appears in the middle of the sequence, treat as error and skip
    for mid_tok in tokens_to_process:
        if isinstance(mid_tok, str) and mid_tok.startswith('CIRCUIT_'):
            print(f"File {filepath} contains a style token in the middle of the sequence ({mid_tok}). Skipping...")
            skipped_files.append(filepath)
            return None, None, None

    # Parse tokens to identify devices and external pins
    for token in tokens_to_process:
        if "_" in token:  # Pin token (e.g., NM1_D)
            device, _ = token.split("_")
            if device_pattern.match(device):
                dev_type = re.match(r'^[A-Z]+', device).group()
                if dev_type == "NM" and device not in devices["NM"]:
                    devices["NM"][device] = NM(device)
                elif dev_type == "PM" and device not in devices["PM"]:
                    devices["PM"][device] = PM(device)
                elif dev_type == "NPN" and device not in devices["NPN"]:
                    devices["NPN"][device] = NPN(device)
                elif dev_type == "PNP" and device not in devices["PNP"]:
                    devices["PNP"][device] = PNP(device)
                elif dev_type == "R" and device not in devices["R"]:
                    devices["R"][device] = R(device)
                elif dev_type == "C" and device not in devices["C"]:
                    devices["C"][device] = C(device)
                elif dev_type == "L" and device not in devices["L"]:
                    devices["L"][device] = L(device)
                elif dev_type == "DIO" and device not in devices["DIO"]:
                    devices["DIO"][device] = DIO(device)
        elif device_pattern.match(token):  # Device token
            dev_type = re.match(r'^[A-Z]+', token).group()
            if dev_type == "NM" and token not in devices["NM"]:
                devices["NM"][token] = NM(token)
            elif dev_type == "PM" and token not in devices["PM"]:
                devices["PM"][token] = PM(token)
            elif dev_type == "NPN" and token not in devices["NPN"]:
                devices["NPN"][token] = NPN(token)
            elif dev_type == "PNP" and token not in devices["PNP"]:
                devices["PNP"][token] = PNP(token)
            elif dev_type == "R" and token not in devices["R"]:
                devices["R"][token] = R(token)
            elif dev_type == "C" and token not in devices["C"]:
                devices["C"][token] = C(token)
            elif dev_type == "L" and token not in devices["L"]:
                devices["L"][token] = L(token)
            elif dev_type == "DIO" and token not in devices["DIO"]:
                devices["DIO"][token] = DIO(token)
        elif EXTERNAL_PIN_REGEX.match(token):  # External pin
            external_pins.add(token)

    # Convert external pins to a sorted list for deterministic output
    external_pins = sorted(list(external_pins))

    # Convert devices back to lists for compatibility
    devices = {k: list(v.values()) for k, v in devices.items()}

    # Debug prints
    print("Style token:", style_token)
    print("Devices: ", {k: [d.name for d in v] for k, v in devices.items()})
    print("External Pins: ", external_pins)
    print("tokens: ", tokens)  # Debug print
    return tokens, devices, external_pins

def assign_pins_to_nets(tokens, devices, external_pins):
    """Assign nets to each device's pins based on the sequence."""
    pin_to_net = {}  # Maps pins (e.g., NM1_D) to their net (e.g., x1, x2, ...)
    nets = {pin: [pin] for pin in external_pins}  # External pins are their own nets
    pin_to_net = {pin: pin for pin in external_pins}  # Map external pins to themselves

    print("Initial nets: ", nets)  # Debug print
    print("Initial pin_to_net: ", pin_to_net)  # Debug print

    net_counter = 1  # Counter for generating new net names
    prev_token = None  # Tracks the previous token in the sequence

    def new_net():
        """Generate a new net name."""
        nonlocal net_counter
        net_name = f"x{net_counter}"
        net_counter += 1
        return net_name

    def merge_nets(net1, net2):
        """Merge two nets into one by combining their pin lists."""
        if net1 == net2:
            return  # Already the same net, no need to merge

        # Ensure external pins remain as their own nets
        if net1 in external_pins and net2 in external_pins:
            # Both are external pins, no need to merge
            return
        elif net1 in external_pins:
            # Keep net1 as the primary net
            pass
        elif net2 in external_pins:
            # Keep net2 as the primary net
            net1, net2 = net2, net1
        elif net1 > net2:
            # Ensure the smaller net name is kept as the primary net
            net1, net2 = net2, net1

        # Merge net2 into net1
        nets[net1].extend(nets[net2])
        for pin in nets[net2]:
            pin_to_net[pin] = net1  # Update all pins in net2 to point to net1
        del nets[net2]  # Remove net2 from the nets dictionary

    for token in tokens:
        if token in external_pins:  # External pin (e.g., VSS, VDD, VIN1, VOUT1)
            if token not in pin_to_net:
                # Treat external pin as its own net
                pin_to_net[token] = token
                nets[token] = [token]

            # If the previous token is a pin, merge the external pin's net
            if prev_token and "_" in prev_token:
                prev_device, prev_pin = prev_token.split("_")
                prev_full_pin = f"{prev_device}_{prev_pin}"

                if prev_full_pin in pin_to_net:
                    # Merge the external pin's net with the previous pin's net
                    merge_nets(pin_to_net[prev_full_pin], pin_to_net[token])

        elif "_" in token:  # Pin token (e.g., NM1_D)
            device, pin = token.split("_")
            full_pin = f"{device}_{pin}"

            # Case 1: Previous token was a net or external pin
            if prev_token is not None and prev_token in pin_to_net:
                prev_net = pin_to_net[prev_token]
                if full_pin in pin_to_net:
                    # Merge nets if both pins already have nets
                    merge_nets(prev_net, pin_to_net[full_pin])
                else:
                    # Assign the previous net to the current pin
                    pin_to_net[full_pin] = prev_net
                    nets[prev_net].append(full_pin)

            # Case 2: Previous token was another pin -> create or reuse a net
            elif prev_token is not None and "_" in prev_token:
                prev_device, prev_pin = prev_token.split("_")
                prev_full_pin = f"{prev_device}_{prev_pin}"

                if prev_full_pin in pin_to_net:
                    if full_pin in pin_to_net:
                        # Merge nets if both pins already have nets
                        merge_nets(pin_to_net[prev_full_pin], pin_to_net[full_pin])
                    else:
                        # Assign the previous pin's net to the current pin
                        net_name = pin_to_net[prev_full_pin]
                        pin_to_net[full_pin] = net_name
                        nets[net_name].append(full_pin)
                else:
                    # Create a new net and assign it to both pins
                    net_name = new_net()
                    pin_to_net[prev_full_pin] = net_name
                    pin_to_net[full_pin] = net_name
                    nets[net_name] = [prev_full_pin, full_pin]

            # Case 3: Isolated pin -> assign a new net
            else:
                net_name = new_net()
                pin_to_net[full_pin] = net_name
                nets[net_name] = [full_pin]

        prev_token = token

    # Remove duplicates and self-references from nets
    for net, pins in nets.items():
        nets[net] = list(set(pins))  # Remove duplicates
        if net in nets[net]:
            nets[net].remove(net)  # Remove self-reference

    # Assign nets to device objects
    for dev_type, dev_list in devices.items():
        for dev in dev_list:
            for pin in ['D', 'G', 'S', 'B', 'P', 'N', 'C', 'E']:  # Check all possible pins
                full_pin = f"{dev.name}_{pin}"
                if full_pin in pin_to_net:
                    setattr(dev, pin, pin_to_net[full_pin])  # Assign the net to the pin

    print("nets: ", nets)  # Debug print
    return pin_to_net, nets

def generate_pyspice_code(devices, external_pins, nets, output_path):
    """Generate PySpice code representing the circuit."""
    lines = []
    lines.append("from PySpice.Spice.Netlist import Circuit")
    lines.append("from PySpice.Unit import *")
    lines.append("from PySpice.Probe.Plot import plot")
    lines.append("import PySpice.Logging.Logging as Logging")
    lines.append("import matplotlib.pyplot as plt")
    lines.append("logger = Logging.setup_logging()")
    lines.append("circuit = Circuit('Generated Circuit')\n")

    # Define NMOS, PMOS, NPN, and PNP models
    lines.append("# Define NMOS and PMOS models")
    lines.append("circuit.model('nmos_model', 'NMOS', kp=50e-6, vto=1.0, lambda_=0.02)")
    lines.append("circuit.model('pmos_model', 'PMOS', kp=25e-6, vto=-1.0, lambda_=0.02)")
    lines.append("# Define NPN and PNP models")
    lines.append("circuit.model('npn_model', 'NPN', is_=1e-16, bf=100, br=1, cje=1e-12, cjc=1e-12)")
    lines.append("circuit.model('pnp_model', 'PNP', is_=1e-16, bf=50, br=1, cje=1e-12, cjc=1e-12)")

    # Helper function to render node arguments
    def node_repr(node):
        if node is None or node == "0":
            return "0"
        return f"'{node}'"

    # Add external pins as voltage or current sources
    lines.append(f"\n# External Pins")
    for pin in external_pins:
        label = pin.lower()
        if pin.startswith("VDD"):
            lines.append(f"circuit.V('{label}', {node_repr(pin)}, circuit.gnd, 1.8@u_V)")
        elif pin.startswith("VSS"):
            lines.append(f"circuit.V('{label}', {node_repr(pin)}, circuit.gnd, 0.0@u_V)")
        elif pin.startswith("I"):
            lines.append(f"circuit.I('{label}', {node_repr(pin)}, circuit.gnd, 100@u_uA)")  # Default 100 µA
        elif pin.startswith("V"):
            lines.append(f"circuit.V('{label}', {node_repr(pin)}, circuit.gnd, 0.9@u_V)")  # Default 0.9 V
        else:
            lines.append(f"# Unsupported external pin type for {pin}")

    lines.append(f"\n# Nets")
    # Add devices
    for dev_type, dev_list in sorted(devices.items()):
        for dev in dev_list:
            if dev_type == "NM":
                lines.append(
                    f"circuit.MOSFET('{dev.name}', {node_repr(dev.D)}, {node_repr(dev.G)}, "
                    f"{node_repr(dev.S)}, {node_repr(dev.B)}, model='nmos_model', w=50e-6, l=1e-6)"
                )
            elif dev_type == "PM":
                lines.append(
                    f"circuit.MOSFET('{dev.name}', {node_repr(dev.D)}, {node_repr(dev.G)}, "
                    f"{node_repr(dev.S)}, {node_repr(dev.B)}, model='pmos_model', w=50e-6, l=1e-6)"
                )
            elif dev_type == "R":
                lines.append(
                    f"circuit.R('{dev.name}', {node_repr(dev.P)}, {node_repr(dev.N)}, 1@u_kΩ)"
                )
            elif dev_type == "C":
                lines.append(
                    f"circuit.C('{dev.name}', {node_repr(dev.P)}, {node_repr(dev.N)}, 1@u_pF)"
                )
            elif dev_type == "L":
                lines.append(
                    f"circuit.L('{dev.name}', {node_repr(dev.P)}, {node_repr(dev.N)}, 1@u_uH)"
                )
            elif dev_type == "DIO":
                lines.append(
                    f"circuit.D('{dev.name}', {node_repr(dev.P)}, {node_repr(dev.N)}, model='default')"
                )
            elif dev_type == "NPN":
                lines.append(
                    f"circuit.BJT('{dev.name}', {node_repr(dev.C)}, {node_repr(dev.B)}, "
                    f"{node_repr(dev.E)}, model='npn_model')"
                )
            elif dev_type == "PNP":
                lines.append(
                    f"circuit.BJT('{dev.name}', {node_repr(dev.C)}, {node_repr(dev.B)}, "
                    f"{node_repr(dev.E)}, model='pnp_model')"
                )
            else:
                lines.append(f"# Unsupported device type for {dev.name} (type {dev_type})")

    # Add operating point simulation
    lines.append("\n# Operating Point Simulation")
    lines.append("simulator = circuit.simulator(temperature=25, nominal_temperature=25)")
    lines.append("analysis = simulator.operating_point()")
    lines.append("print('\\nOperating Point Results:')")
    lines.append("for node in analysis.nodes.values():")
    lines.append("    print(f'Node {node}: {float(node):.2f} V')")
    lines.append("for branch in analysis.branches.values():")
    lines.append("    print(f'Branch {branch}: {float(branch):.2e} A')")

    # Write the generated code to the output file
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w') as f:
        f.write("\n".join(lines))


# Main execution: process run{i}.txt files and keep terminal output
for i in range(0, 1000):
    test_filepath = Path(f"Inference/run{i}.txt")
    if test_filepath.exists():
        print(f"Processing file: run{i}.txt")
        
        # Step 1: Parse tokens, devices, and external pins
        tokens, devices, external_pins = file_open_and_list_up(test_filepath)
        
        # Skip further processing if file_open_and_list_up returned None
        if tokens is None or devices is None or external_pins is None:
            print(f"Skipping file: run{i}.txt due to digital circuits or other issues.\n")
            continue
        
        # Step 2: Assign nets to pins
        pin_to_net, nets = assign_pins_to_nets(tokens, devices, external_pins)
        
        # Debug: Print pin-to-net mapping
        print(f"Pin-to-Net Mapping for run{i}.txt:")
        for pin, net in pin_to_net.items():
            print(f"  {pin} -> {net}")
        
        # Debug: Print device pin connections
        print(f"Device Pin Connections for run{i}.txt:")
        for dev_type, dev_list in sorted(devices.items()):
            print(f"  {dev_type}:")
            for dev in dev_list:
                if dev_type in ["NM", "PM"]:  # MOSFETs
                    print(f"    {dev.name}: D={dev.D}, G={dev.G}, S={dev.S}, B={dev.B}")
                elif dev_type in ["C", "R", "L", "DIO"]:  # Capacitors, Resistors, Inductors, Diodes
                    print(f"    {dev.name}: P={dev.P}, N={dev.N}")
                elif dev_type in ["NPN", "PNP"]:  # Bipolar Junction Transistors
                    print(f"    {dev.name}: C={dev.C}, B={dev.B}, E={dev.E}")
                else:
                    print(f"    {dev.name}: Unsupported device type")
        
        # Step 3: Generate PySpice code
        output_path = f"SPICE/run{i}.py"
        generate_pyspice_code(devices, external_pins, nets, output_path)
        print(f"Generated PySpice code for run{i}.txt at {output_path}\n")
    else:
        print(f"File run{i}.txt does not exist. Skipping...\n")

# Print skipped files at the end
print("\nSkipped Files:")
for skipped_file in skipped_files:
    print(skipped_file)
print("Total Skipped Files:", len(skipped_files))