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
circuit.V('vdd', 'VDD', circuit.gnd, 1.8@u_V)
circuit.V('vin1', 'VIN1', circuit.gnd, 0.9@u_V)
circuit.V('vout1', 'VOUT1', circuit.gnd, 0.9@u_V)
circuit.V('vout2', 'VOUT2', circuit.gnd, 0.9@u_V)
circuit.V('vref1', 'VREF1', circuit.gnd, 0.9@u_V)
circuit.V('vss', 'VSS', circuit.gnd, 0.0@u_V)

# Nets
circuit.MOSFET('NM6', 'x109', 'x109', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM5', 'x108', 'x109', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM3', 'x107', 'VREF1', 'x108', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM1', 'x102', 'x102', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM2', 'x102', 'x102', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM4', 'x103', 'x102', 'x108', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM9', 'VOUT2', 'VOUT2', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM11', 'x12', 'VB3', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM7', 'VB1', 'VB1', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM8', 'x24', 'VB1', 'x29', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM10', 'VOUT2', 'VOUT2', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM12', 'VOUT2', 'VB2', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM13', 'VB2', 'VOUT2', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM2', 'x102', 'x107', 'VDD', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM1', 'x102', 'x103', 'VDD', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM10', 'VOUT2', 'x102', 'VDD', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM8', 'VOUT2', 'x12', 'VOUT1', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM12', 'x12', 'x12', 'x58', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM5', 'x109', 'x24', 'VDD', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM6', 'x24', 'x24', 'VDD', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM7', 'VB1', 'x24', 'VDD', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM9', 'VOUT1', 'VOUT2', 'VIN1', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM3', 'x107', 'x107', 'VDD', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM4', 'x103', 'x103', 'VDD', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM11', 'VB2', 'VB2', 'VIN1', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM13', 'x58', 'x102', 'VIN1', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.R('R1', 'x29', 'VSS', 1@u_kΩ)
circuit.R('R2', 'VDD', 'VOUT2', 1@u_kΩ)

# Operating Point Simulation
simulator = circuit.simulator(temperature=25, nominal_temperature=25)
analysis = simulator.operating_point()
print('\nOperating Point Results:')
for node in analysis.nodes.values():
    print(f'Node {node}: {float(node):.2f} V')
for branch in analysis.branches.values():
    print(f'Branch {branch}: {float(branch):.2e} A')