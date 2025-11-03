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
circuit.V('vin1', 'VIN1', circuit.gnd, 0.9@u_V)
circuit.V('vout1', 'VOUT1', circuit.gnd, 0.9@u_V)
circuit.V('vref1', 'VREF1', circuit.gnd, 0.9@u_V)
circuit.V('vss', 'VSS', circuit.gnd, 0.0@u_V)

# Nets
circuit.C('C1', 'VOUT1', 'x5', 1@u_pF)
circuit.C('C3', 'VOUT1', 'x31', 1@u_pF)
circuit.C('C2', 'VOUT1', 'VOUT1', 1@u_pF)
circuit.MOSFET('NM7', 'VB3', 'VB3', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM1', 'x28', 'x110', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM10', 'VB3', 'VB3', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM2', 'x111', 'x110', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM3', 'x107', 'x102', 'x28', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM4', 'VOUT1', 'x102', 'x111', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM14', 'x31', 'VOUT1', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM12', 'x119', 'VB6', 'x118', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM11', 'x118', 'VB5', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM5', 'x102', 'x102', 'x110', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM6', 'x110', 'x110', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM8', 'x45', 'VB3', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM9', 'x46', 'VB3', 'x45', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM13', 'x55', 'x31', 'x118', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM16', 'x31', 'VOUT1', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM15', 'x31', 'x31', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM2', 'x28', 'x5', 'x114', 'x113', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM11', 'VOUT1', 'x46', 'VIN1', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM12', 'VB3', 'VB3', 'VIN1', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM13', 'VB3', 'VB3', 'VIN1', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM5', 'VB3', 'VB2', 'x106', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM4', 'x107', 'VB2', 'x118', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM6', 'x118', 'x107', 'VIN1', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM3', 'x114', 'VB1', 'VIN1', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM1', 'x111', 'VREF1', 'x114', 'x113', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM7', 'x106', 'x107', 'VIN1', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM8', 'x102', 'x46', 'VIN1', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM16', 'x31', 'x119', 0, 0, model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM15', 'x119', 'x119', 'VIN1', 0, model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM9', 'VB3', 'x46', 'VIN1', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM14', 'x31', 'VB4', 'VIN1', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM10', 'x46', 'x46', 'VIN1', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM17', 'x31', 'VB4', 'VIN1', 0, model='pmos_model', w=50e-6, l=1e-6)
circuit.R('R2', 'VOUT1', 'x5', 1@u_kΩ)
circuit.R('R1', 'x5', 'VSS', 1@u_kΩ)

# Operating Point Simulation
simulator = circuit.simulator(temperature=25, nominal_temperature=25)
analysis = simulator.operating_point()
print('\nOperating Point Results:')
for node in analysis.nodes.values():
    print(f'Node {node}: {float(node):.2f} V')
for branch in analysis.branches.values():
    print(f'Branch {branch}: {float(branch):.2e} A')