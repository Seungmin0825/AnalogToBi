from PySpice.Spice.Netlist import Circuit
from PySpice.Unit import *
from PySpice.Probe.Plot import plot
import PySpice.Logging.Logging as Logging
import matplotlib.pyplot as plt
logger = Logging.setup_logging()
circuit = Circuit('Generated Circuit')

# Define NMOS and PMOS models
circuit.model('nmos_model', 'NMOS', kp=50e-6, vto=1.0, lambda_=0.02)
circuit.model('pmos_model', 'PMOS', kp=25e-6, vto=-1.0, lambda_=0.02)
# Define NPN and PNP models
circuit.model('npn_model', 'NPN', is_=1e-16, bf=100, br=1, cje=1e-12, cjc=1e-12)
circuit.model('pnp_model', 'PNP', is_=1e-16, bf=50, br=1, cje=1e-12, cjc=1e-12)

# External Pins
circuit.V('vb1', 'VB1', circuit.gnd, 0.9@u_V)
circuit.V('vb2', 'VB2', circuit.gnd, 0.9@u_V)
circuit.V('vb3', 'VB3', circuit.gnd, 0.9@u_V)
circuit.V('vb4', 'VB4', circuit.gnd, 0.9@u_V)
circuit.V('vb5', 'VB5', circuit.gnd, 0.9@u_V)
circuit.V('vb6', 'VB6', circuit.gnd, 0.9@u_V)
circuit.V('vb7', 'VB7', circuit.gnd, 0.9@u_V)
circuit.V('vb8', 'VB8', circuit.gnd, 0.9@u_V)
circuit.V('vin1', 'VIN1', circuit.gnd, 0.9@u_V)
circuit.V('vout1', 'VOUT1', circuit.gnd, 0.9@u_V)
circuit.V('vref1', 'VREF1', circuit.gnd, 0.9@u_V)
circuit.V('vss', 'VSS', circuit.gnd, 0.0@u_V)

# Nets
circuit.C('C1', 'VOUT1', 'x101', 1@u_pF)
circuit.C('C3', 'x110', 'x111', 1@u_pF)
circuit.C('C2', 'VOUT1', 'x110', 1@u_pF)
circuit.MOSFET('NM1', 'x153', 'x147', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM3', 'x147', 'x10', 'x153', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM2', 'x150', 'x147', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM4', 'x110', 'x10', 'x150', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM5', 'x12', 'x101', 'x140', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM6', 'x112', 'VREF1', 'x140', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM15', 'x135', 'x110', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM19', 'x111', 'x110', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM17', 'x131', 'VB8', 'x130', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM16', 'x130', 'VB7', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM7', 'x140', 'VB2', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM8', 'x127', 'x10', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM9', 'x10', 'x10', 'x127', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM10', 'x115', 'VB5', 'VB4', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM11', 'VB5', 'VB4', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM12', 'VB4', 'x117', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM13', 'x117', 'x117', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM18', 'x112', 'x111', 'x130', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM21', 'x104', 'x110', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM14', 'x137', 'x104', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM20', 'x104', 'x104', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM2', 'x110', 'VB3', 'x12', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM1', 'x147', 'VB3', 'x112', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM9', 'VOUT1', 'x137', 'VIN1', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM10', 'x137', 'x135', 'VIN1', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM11', 'x135', 'x135', 'VIN1', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM14', 'x111', 'x131', 'VIN1', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM13', 'x131', 'x131', 'VIN1', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM5', 'x10', 'x115', 'VIN1', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM8', 'x117', 'x115', 'VIN1', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM6', 'x115', 'x115', 'VIN1', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM7', 'VB5', 'x115', 'VIN1', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM3', 'x12', 'VB1', 'VIN1', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM4', 'x112', 'VB1', 'VIN1', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM12', 'x112', 'x112', 'VIN1', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM15', 'x104', 'VB6', 'VIN1', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.R('R1', 'x101', 'VSS', 1@u_kΩ)
circuit.R('R2', 'VOUT1', 'x101', 1@u_kΩ)

# Operating Point Simulation
simulator = circuit.simulator(temperature=25, nominal_temperature=25)
analysis = simulator.operating_point()
print('\nOperating Point Results:')
for node in analysis.nodes.values():
    print(f'Node {node}: {float(node):.2f} V')
for branch in analysis.branches.values():
    print(f'Branch {branch}: {float(branch):.2e} A')