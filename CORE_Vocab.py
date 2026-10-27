"""
The token vocabulary, in one place.

Every script that touches a sequence needs the same token list and the same
index for each token: the generator, the classifier, and each metric. Defining
it once here keeps them in step. A token added or a range widened in this file
reaches every script at once, which is what makes the indices comparable across
training, decoding and evaluation.

This module deliberately avoids heavy imports. The metrics do not need torch,
and they would inherit it if the vocabulary lived in CORE_Grammar.py, which
builds the model.

Exports:
    vocab_tokens          the ordered token list
    stoi, itos            token <-> index
    vocab_size            len(vocab_tokens)
    circuit_type_tokens   the 15 CIRCUIT_* tokens
    mosfet_edges, bjt_edges, passive_edges, diode_edges, all_edge_types
    power_rails, net_tokens, port_tokens, all_device_tokens, all_net_port_tokens
"""

vocab_tokens = []

# Edge types
mosfet_edges = [
    'M_B', 'M_D', 'M_G', 'M_S',  # Single pin
    'M_BD', 'M_BG', 'M_BS', 'M_DG', 'M_DS', 'M_GS',  # Two pins
    'M_BDG', 'M_BDS', 'M_BGS', 'M_DGS',  # Three pins
    'M_BDGS'  # Four pins
]
vocab_tokens.extend(mosfet_edges)

bjt_edges = [
    'B_B', 'B_C', 'B_E',
    'B_BC', 'B_BE', 'B_CE',
    'B_BCE'
]
vocab_tokens.extend(bjt_edges)

passive_edges = ['R_C', 'C_C', 'L_C']
vocab_tokens.extend(passive_edges)

diode_edges = ['D_P', 'D_N', 'D_NP', 'D_PN']
vocab_tokens.extend(diode_edges)

all_edge_types = set(mosfet_edges + bjt_edges + passive_edges + diode_edges)

# Power rails
power_rails = ['VSS', 'VDD']
vocab_tokens.extend(power_rails)

# Circuit type tokens
circuit_type_tokens = [
    'CIRCUIT_Opamp', 'CIRCUIT_LDO', 'CIRCUIT_Bandgap_Ref',
    'CIRCUIT_Power_converter', 'CIRCUIT_Oscillator', 'CIRCUIT_General',
    'CIRCUIT_Mirror', 'CIRCUIT_Mixer', 'CIRCUIT_Power_Amp',
    'CIRCUIT_PLL', 'CIRCUIT_Filter', 'CIRCUIT_Comparator',
    'CIRCUIT_Voltage_Regulator', 'CIRCUIT_Switched_Cap', 'CIRCUIT_ADC_DAC'
]
vocab_tokens.extend(circuit_type_tokens)

# Device tokens
# MOSFETs: NM1-NM35, PM1-PM35
mosfet_tokens = []
for i in range(1, 36):
    mosfet_tokens.append(f'NM{i}')
for i in range(1, 36):
    mosfet_tokens.append(f'PM{i}')
vocab_tokens.extend(mosfet_tokens)

# BJTs: NPN1-NPN27, PNP1-PNP27
bjt_tokens = []
for i in range(1, 28):
    bjt_tokens.append(f'NPN{i}')
for i in range(1, 28):
    bjt_tokens.append(f'PNP{i}')
vocab_tokens.extend(bjt_tokens)

# Resistors: R1-R28
resistor_tokens = [f'R{i}' for i in range(1, 29)]
vocab_tokens.extend(resistor_tokens)

# Capacitors: C1-C16
capacitor_tokens = [f'C{i}' for i in range(1, 17)]
vocab_tokens.extend(capacitor_tokens)

# Inductors: L1-L24
inductor_tokens = [f'L{i}' for i in range(1, 25)]
vocab_tokens.extend(inductor_tokens)

# Diodes: DIO1-DIO8
diode_tokens = [f'DIO{i}' for i in range(1, 9)]
vocab_tokens.extend(diode_tokens)

# All device tokens combined
all_device_tokens = set(mosfet_tokens + bjt_tokens + resistor_tokens + 
                        capacitor_tokens + inductor_tokens + diode_tokens)

# Net nodes
net_tokens = [f'NET{i}' for i in range(1, 51)]
vocab_tokens.extend(net_tokens)

# Port nodes
port_tokens = []
# Voltage/Current I/O
for i in range(1, 21):
    port_tokens.append(f'VIN{i}')
port_tokens.append('VOUT')  # Single VOUT token
for i in range(1, 8):
    port_tokens.append(f'VOUT{i}')
for i in range(1, 4):
    port_tokens.append(f'IIN{i}')
for i in range(1, 6):
    port_tokens.append(f'IOUT{i}')
# Bias voltages/currents
for i in range(1, 12):
    port_tokens.append(f'VB{i}')
for i in range(1, 8):
    port_tokens.append(f'IB{i}')
# Control/reference signals
for i in range(1, 22):
    port_tokens.append(f'VCONT{i}')
for i in range(1, 4):
    port_tokens.extend([f'VCM{i}', f'VREF{i}', f'IREF{i}', f'VRF{i}', f'VIF{i}'])
# RF/mixer/PLL specific
for i in range(1, 6):
    port_tokens.extend([f'VLO{i}', f'VBB{i}'])
vocab_tokens.extend(port_tokens)

# All net/port tokens (nodes that connect)
all_net_port_tokens = set(net_tokens + port_tokens + ['VSS', 'VDD'])

# Special tokens
vocab_tokens.append('TRUNCATE')

# Build mappings
devices = vocab_tokens
stoi = {d: i for i, d in enumerate(devices)}
itos = {i: d for i, d in enumerate(devices)}
vocab_size = len(devices)
