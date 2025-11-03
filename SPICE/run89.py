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
circuit.V('vdd', 'VDD', circuit.gnd, 1.8@u_V)
circuit.V('vout1', 'VOUT1', circuit.gnd, 0.9@u_V)
circuit.V('vref1', 'VREF1', circuit.gnd, 0.9@u_V)
circuit.V('vss', 'VSS', circuit.gnd, 0.0@u_V)

# Nets
circuit.C('C1', 'x134', 'VSS', 1@u_pF)
circuit.C('C2', 'x134', 'VOUT1', 1@u_pF)
circuit.MOSFET('NM3', 'x139', 'x123', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM7', 'x123', 'x109', 'x139', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM1', 'x135', 'x123', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM5', 'x134', 'x109', 'x135', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM6', 'x126', 'x109', 'x121', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM2', 'x121', 'x113', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM8', 'x113', 'x109', 'x114', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM9', 'x110', 'x109', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM10', 'x109', 'x109', 'x110', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM4', 'x114', 'x113', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM11', 'x106', 'x102', 'VB3', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM12', 'x10', 'x104', 'x106', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM14', 'x104', 'x104', 'x10', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM13', 'x102', 'x102', 'x106', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM15', 'VB3', 'VB3', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM16', 'x134', 'x10', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM17', 'x64', 'VB6', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM18', 'x134', 'VB5', 'x64', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM5', 'x123', 'x137', 'x118', 'x25', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM3', 'x134', 'VB1', 'x10', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM4', 'x126', 'VB1', 'x102', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM1', 'x10', 'x126', 'VDD', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM2', 'x102', 'x126', 'VDD', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM6', 'x113', 'VREF1', 'x118', 'x25', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM7', 'x118', 'VB2', 'VDD', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM8', 'x109', 'x134', 'VDD', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM11', 'VB3', 'x134', 'VDD', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM9', 'x102', 'x134', 'VDD', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM10', 'x104', 'x134', 'VDD', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM12', 'x134', 'x134', 'VDD', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM13', 'x64', 'x134', 'VOUT1', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM14', 'VOUT1', 'x134', 'VDD', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM16', 'x134', 'VB4', 'VDD', 0, model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM15', 'x134', 0, 'VDD', 0, model='pmos_model', w=50e-6, l=1e-6)
circuit.R('R1', 'x137', 'VSS', 1@u_kΩ)
circuit.R('R2', 'VOUT1', 'x137', 1@u_kΩ)

# Operating Point Simulation
simulator = circuit.simulator(temperature=25, nominal_temperature=25)
analysis = simulator.operating_point()
print('\nOperating Point Results:')
for node in analysis.nodes.values():
    print(f'Node {node}: {float(node):.2f} V')
for branch in analysis.branches.values():
    print(f'Branch {branch}: {float(branch):.2e} A')