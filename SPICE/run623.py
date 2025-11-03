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
circuit.V('vb6', 'VB6', circuit.gnd, 0.9@u_V)
circuit.V('vdd', 'VDD', circuit.gnd, 1.8@u_V)
circuit.V('vout1', 'VOUT1', circuit.gnd, 0.9@u_V)
circuit.V('vref1', 'VREF1', circuit.gnd, 0.9@u_V)
circuit.V('vss', 'VSS', circuit.gnd, 0.0@u_V)

# Nets
circuit.C('C1', 'VOUT1', 'VSS', 1@u_pF)
circuit.C('C2', 'VOUT1', 'VOUT1', 1@u_pF)
circuit.MOSFET('NM1', 'x117', 'x114', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM2', 'x115', 'x114', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM3', 'x111', 'x107', 'x117', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM4', 'VOUT1', 'x107', 'x115', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM5', 'x107', 'x107', 'x114', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM12', 'VOUT1', 'x105', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM8', 'x105', 'x103', 'x100', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM10', 'x103', 'x103', 'x105', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM7', 'x100', 'x101', 'VB3', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM6', 'x114', 'x114', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM11', 'VB3', 'VB3', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM13', 'x49', 'VB6', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM9', 'x101', 'x101', 'x100', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM14', 'VOUT1', 0, 0, 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM2', 'x117', 'VREF1', 'VOUT1', 'x67', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM1', 'x115', 'x66', 'VOUT1', 'x67', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM4', 'x111', 'VB2', 'x38', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM5', 'VOUT1', 'VB2', 'x40', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM8', 'x107', 'VOUT1', 'VDD', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM10', 'x103', 'VOUT1', 'VDD', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM9', 'x101', 'VOUT1', 'VDD', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM11', 'VB3', 'VOUT1', 'VDD', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM12', 'VOUT1', 'VOUT1', 'VDD', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM3', 'VOUT1', 'VB1', 'VDD', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM6', 'x38', 'x111', 'VDD', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM7', 'x40', 'x111', 'VDD', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM13', 'x49', 'VOUT1', 'VOUT1', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM14', 'VOUT1', 'VOUT1', 'VDD', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM15', 'VOUT1', 0, 'VDD', 0, model='pmos_model', w=50e-6, l=1e-6)
circuit.R('R1', 'x66', 'VSS', 1@u_kΩ)
circuit.R('R2', 'VOUT1', 'x66', 1@u_kΩ)

# Operating Point Simulation
simulator = circuit.simulator(temperature=25, nominal_temperature=25)
analysis = simulator.operating_point()
print('\nOperating Point Results:')
for node in analysis.nodes.values():
    print(f'Node {node}: {float(node):.2f} V')
for branch in analysis.branches.values():
    print(f'Branch {branch}: {float(branch):.2e} A')