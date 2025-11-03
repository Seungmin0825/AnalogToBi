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
circuit.V('vb8', 'VB8', circuit.gnd, 0.9@u_V)
circuit.V('vin1', 'VIN1', circuit.gnd, 0.9@u_V)
circuit.V('vout1', 'VOUT1', circuit.gnd, 0.9@u_V)
circuit.V('vref1', 'VREF1', circuit.gnd, 0.9@u_V)
circuit.V('vss', 'VSS', circuit.gnd, 0.0@u_V)

# Nets
circuit.C('C1', 'VOUT1', 'x132', 1@u_pF)
circuit.C('C3', 'VOUT1', 'VOUT1', 1@u_pF)
circuit.C('C2', 'VOUT1', 'VOUT1', 1@u_pF)
circuit.MOSFET('NM12', 'VOUT1', 'VOUT1', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM5', 'VB1', 'x132', 'x118', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM4', 'VOUT1', 'x112', 'x12', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM3', 'x122', 'x112', 'x127', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM1', 'x127', 'x122', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM2', 'x12', 'x122', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM6', 'VB1', 'VREF1', 'x118', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM7', 'x118', 'VB2', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM8', 'x115', 'x112', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM9', 'x112', 'x112', 'x115', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM10', 'VB8', 'VB5', 'VB4', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM11', 'VB5', 'VB4', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM13', 'VOUT1', 'VOUT1', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM16', 'VOUT1', 'VOUT1', 'VB1', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM15', 'x75', 'VOUT1', 'VSS', 'x75', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM17', 'VOUT1', 'VOUT1', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM19', 'VOUT1', 'VOUT1', 0, 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM14', 'VB8', 'VB8', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM18', 'VOUT1', 'VOUT1', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM21', 0, 'VOUT1', 0, 0, model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM13', 'VOUT1', 'VOUT1', 'VIN1', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM2', 'VOUT1', 'VB3', 'VB1', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM1', 'x122', 'VB3', 'VB1', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM5', 'x112', 'VB8', 'VIN1', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM8', 'VOUT1', 'VB8', 'VIN1', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM6', 'VB8', 'VB8', 'VIN1', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM7', 'VB5', 'VB8', 'VIN1', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM3', 'VB1', 'VB1', 'VIN1', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM4', 'VB1', 'VB1', 'VIN1', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM11', 'VOUT1', 'VB1', 'VIN1', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM14', 'VOUT1', 'VB5', 'VIN1', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM9', 'VB8', 'VB8', 'VIN1', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM10', 'x58', 'VB1', 'VIN1', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM12', 'VOUT1', 'VOUT1', 'VIN1', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.R('R2', 'VOUT1', 'VREF1', 1@u_kΩ)
circuit.R('R1', 'VREF1', 'VSS', 1@u_kΩ)
circuit.R('R3', 'VOUT1', 'VOUT1', 1@u_kΩ)

# Operating Point Simulation
simulator = circuit.simulator(temperature=25, nominal_temperature=25)
analysis = simulator.operating_point()
print('\nOperating Point Results:')
for node in analysis.nodes.values():
    print(f'Node {node}: {float(node):.2f} V')
for branch in analysis.branches.values():
    print(f'Branch {branch}: {float(branch):.2e} A')