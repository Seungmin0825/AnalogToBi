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
circuit.V('vdd', 'VDD', circuit.gnd, 1.8@u_V)
circuit.V('vin1', 'VIN1', circuit.gnd, 0.9@u_V)
circuit.V('vout1', 'VOUT1', circuit.gnd, 0.9@u_V)
circuit.V('vref1', 'VREF1', circuit.gnd, 0.9@u_V)
circuit.V('vss', 'VSS', circuit.gnd, 0.0@u_V)

# Nets
circuit.C('C1', 'VOUT1', 'x30', 1@u_pF)
circuit.MOSFET('NM5', 'VIN1', 'VB2', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM3', 'x149', 'x30', 'VIN1', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM2', 'x11', 'x12', 'x28', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM1', 'x13', 'x12', 'x26', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM4', 'VIN1', 'VREF1', 'VIN1', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM17', 'VIN1', 'VB6', 'x104', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM16', 'VIN1', 'VB6', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM6', 'x26', 'x13', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM7', 'x28', 'x13', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM15', 'VIN1', 'VB7', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM8', 'x134', 'x12', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM9', 'x12', 'x12', 'VB3', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM10', 'x122', 'VB4', 'VB3', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM11', 'VB4', 'VB3', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM12', 'VB3', 'x61', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM13', 'x61', 'x61', 'VB3', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM18', 'VIN1', 'VIN1', 'x104', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM19', 'VIN1', 'VB5', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM14', 'VIN1', 'VIN1', 'VB3', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM20', 'VIN1', 'VIN1', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM21', 'VIN1', 'VB4', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM22', 'x97', 'VB5', 0, 0, model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM2', 'x149', 'VB1', 'VIN1', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM1', 'VIN1', 'VB1', 'x154', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM5', 'x154', 'VIN1', 'VIN1', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM6', 'VIN1', 'x149', 'VIN1', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM8', 'VIN1', 'x149', 'VIN1', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM4', 'x11', 'VB1', 'VIN1', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM3', 'x13', 'VB1', 'x128', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM7', 'x128', 'VIN1', 'VIN1', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM18', 'VSS', 'VIN1', 'VIN1', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM17', 'VIN1', 'VIN1', 'VIN1', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM13', 'VOUT1', 'VIN1', 'VIN1', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM14', 'VIN1', 'VIN1', 'VIN1', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM15', 'VIN1', 'VIN1', 'VIN1', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM16', 'VIN1', 'VIN1', 'VIN1', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM9', 'x12', 'x122', 'VIN1', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM10', 'x122', 'x122', 'VIN1', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM11', 'VB4', 'x122', 'VIN1', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM12', 'x61', 'x122', 'VIN1', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM19', 'VIN1', 'VB5', 'VIN1', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM20', 'VIN1', 'VB4', 'VIN1', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)

# Operating Point Simulation
simulator = circuit.simulator(temperature=25, nominal_temperature=25)
analysis = simulator.operating_point()
print('\nOperating Point Results:')
for node in analysis.nodes.values():
    print(f'Node {node}: {float(node):.2f} V')
for branch in analysis.branches.values():
    print(f'Branch {branch}: {float(branch):.2e} A')