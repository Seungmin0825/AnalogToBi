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
circuit.V('vin1', 'VIN1', circuit.gnd, 0.9@u_V)
circuit.V('vout1', 'VOUT1', circuit.gnd, 0.9@u_V)
circuit.V('vref1', 'VREF1', circuit.gnd, 0.9@u_V)
circuit.V('vss', 'VSS', circuit.gnd, 0.0@u_V)

# Nets
circuit.C('C1', 'VOUT1', 'x16', 1@u_pF)
circuit.C('C3', 'x21', 'VB2', 1@u_pF)
circuit.C('C2', 'VOUT1', 'x21', 1@u_pF)
circuit.MOSFET('NM8', 'x101', 'x101', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM7', 'VB1', 'x101', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM5', 'x12', 'x107', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM3', 'x111', 'x16', 'x12', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM2', 'x21', 'x8', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM1', 'x8', 'x8', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM4', 'VB2', 'VREF1', 'x12', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM11', 'VB2', 'x21', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM15', 'VB2', 'x21', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM13', 'x111', 'VB3', 'x110', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM12', 'x110', 'VB2', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM6', 'x107', 'x107', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM9', 'VB2', 'x101', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM10', 'VB2', 'VB2', 'VB2', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM17', 'VB2', 'x21', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM16', 'VB2', 'VB2', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM14', 'x58', 'VB2', 'x110', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM18', 'VB2', 'VB2', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM5', 'x107', 'VB1', 'VIN1', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM2', 'x21', 'x111', 'VIN1', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM1', 'x8', 'VB2', 'VIN1', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM9', 'VOUT1', 'VB2', 'VIN1', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM10', 'VB2', 'VB2', 'VIN1', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM11', 'VB2', 'VB2', 'VIN1', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM14', 'VB2', 'x111', 'VIN1', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM3', 'x111', 'x111', 'VIN1', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM13', 'x111', 'x111', 'VIN1', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM7', 'x101', 'VB2', 'VIN1', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM4', 'VB2', 'VB2', 'VIN1', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM6', 'VB1', 'VB1', 'VIN1', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM8', 'VB2', 'VB2', 'VIN1', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM15', 'VB2', 'VB4', 'VIN1', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM12', 'x58', 'x58', 'VIN1', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.R('R1', 'VIN1', 'x101', 1@u_kΩ)
circuit.R('R2', 'x16', 'VSS', 1@u_kΩ)
circuit.R('R3', 'VOUT1', 'x16', 1@u_kΩ)

# Operating Point Simulation
simulator = circuit.simulator(temperature=25, nominal_temperature=25)
analysis = simulator.operating_point()
print('\nOperating Point Results:')
for node in analysis.nodes.values():
    print(f'Node {node}: {float(node):.2f} V')
for branch in analysis.branches.values():
    print(f'Branch {branch}: {float(branch):.2e} A')