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
circuit.I('ib1', 'IB1', circuit.gnd, 100@u_uA)
circuit.V('vb1', 'VB1', circuit.gnd, 0.9@u_V)
circuit.V('vb2', 'VB2', circuit.gnd, 0.9@u_V)
circuit.V('vb3', 'VB3', circuit.gnd, 0.9@u_V)
circuit.V('vdd', 'VDD', circuit.gnd, 1.8@u_V)
circuit.V('vout1', 'VOUT1', circuit.gnd, 0.9@u_V)
circuit.V('vref1', 'VREF1', circuit.gnd, 0.9@u_V)
circuit.V('vss', 'VSS', circuit.gnd, 0.0@u_V)

# Nets
circuit.C('C1', 'VOUT1', 'x49', 1@u_pF)
circuit.MOSFET('NM8', 'x129', 'VDD', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM5', 'VDD', 'x107', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM3', 'x112', 'VREF1', 'VDD', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM2', 'VB2', 'x123', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM1', 'x123', 'x123', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM4', 'x110', 'x10', 'VDD', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM11', 'VDD', 'VDD', 'VDD', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM13', 'VDD', 'VDD', 'VDD', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM6', 'VB1', 'x107', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM7', 'x107', 'x107', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM9', 'VDD', 'VDD', 'VDD', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM10', 'VDD', 'x101', 'VDD', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM12', 'x101', 'x101', 'VDD', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM14', 'VB2', 'VDD', 'VDD', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM15', 'x101', 'VB3', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM17', 'x101', 'VB2', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM16', 'VDD', 'VDD', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM6', 'x107', 'x129', 'VDD', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM2', 'VB2', 'x112', 'VDD', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM1', 'x123', 'x110', 'VDD', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM3', 'x112', 'x112', 'VDD', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM4', 'x110', 'x110', 'VDD', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM5', 'VB1', 'VB1', 'VDD', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM9', 'x101', 'VB2', 'VDD', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM13', 'VDD', 'VB2', 'VB2', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM10', 'VSS', 'IB1', 'VDD', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM8', 'VDD', 'VB2', 'VDD', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM11', 'VDD', 'VB2', 'VDD', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM7', 'x129', 'x129', 'VDD', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM12', 'VDD', 'VDD', 'VDD', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM14', 'VB2', 0, 'VDD', 0, model='pmos_model', w=50e-6, l=1e-6)
circuit.R('R3', 'x10', 'VSS', 1@u_kΩ)
circuit.R('R1', 'VOUT1', 'VSS', 1@u_kΩ)
circuit.R('R4', 'VOUT1', 'x10', 1@u_kΩ)
circuit.R('R2', 'x49', 'VSS', 1@u_kΩ)

# Operating Point Simulation
simulator = circuit.simulator(temperature=25, nominal_temperature=25)
analysis = simulator.operating_point()
print('\nOperating Point Results:')
for node in analysis.nodes.values():
    print(f'Node {node}: {float(node):.2f} V')
for branch in analysis.branches.values():
    print(f'Branch {branch}: {float(branch):.2e} A')