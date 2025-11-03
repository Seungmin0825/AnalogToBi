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
circuit.MOSFET('NM1', 'x108', 'x108', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM2', 'x108', 'x108', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM3', 'x19', 'VREF1', 'x24', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM4', 'x109', 'x108', 'x24', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM11', 'VOUT2', 'x10', 'VB3', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM14', 'VDD', 'VB2', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM5', 'x24', 'x23', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM6', 'x23', 'x23', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM7', 'VB1', 'VB3', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM8', 'VB3', 'VB3', 'VB3', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM9', 'VB3', 'VB3', 'VB3', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM10', 'VB3', 'VB3', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM12', 'VB3', 'VB3', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM13', 'x10', 'x10', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM2', 'x108', 'x19', 'VDD', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM1', 'x108', 'x109', 'VDD', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM11', 'x10', 'x108', 'VDD', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM9', 'VOUT2', 'VDD', 'VOUT1', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM13', 'VDD', 'VDD', 'x14', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM14', 'x14', 'VDD', 'VIN1', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM10', 'VOUT1', 'VDD', 'VDD', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM3', 'x19', 'x19', 'VDD', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM4', 'x109', 'x109', 'VDD', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM5', 'x23', 'VB1', 'VDD', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM6', 'VB1', 'VB1', 'VDD', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM7', 'VB3', 'VB2', 'VDD', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM8', 'VB3', 'VB2', 'VDD', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM12', 'VDD', 'VDD', 'VIN1', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM15', 'VIN1', 'VB3', 'VIN1', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM16', 'VB3', 0, 'VIN1', 0, model='pmos_model', w=50e-6, l=1e-6)

# Operating Point Simulation
simulator = circuit.simulator(temperature=25, nominal_temperature=25)
analysis = simulator.operating_point()
print('\nOperating Point Results:')
for node in analysis.nodes.values():
    print(f'Node {node}: {float(node):.2f} V')
for branch in analysis.branches.values():
    print(f'Branch {branch}: {float(branch):.2e} A')