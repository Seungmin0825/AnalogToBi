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
circuit.V('vin1', 'VIN1', circuit.gnd, 0.9@u_V)
circuit.V('vout1', 'VOUT1', circuit.gnd, 0.9@u_V)
circuit.V('vref1', 'VREF1', circuit.gnd, 0.9@u_V)
circuit.V('vss', 'VSS', circuit.gnd, 0.0@u_V)

# Nets
circuit.C('C1', 'VOUT1', 'VB1', 1@u_pF)
circuit.MOSFET('NM6', 'x113', 'x113', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM5', 'x105', 'x113', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM3', 'x100', 'VREF1', 'x105', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM2', 'x5', 'x107', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM1', 'x107', 'x107', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM4', 'VB1', 'x111', 'x105', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM11', 'VDD', 'x105', 'VOUT1', 'VOUT1', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM13', 'VDD', 'x105', 'VDD', 'VOUT1', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM7', 'VB1', 'VB2', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM9', 'VB2', 'VB2', 'x35', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM10', 'x38', 'VB2', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM8', 'VB2', 'VB2', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM14', 'x105', 'x105', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM12', 'VDD', 'x5', 'IB1', 'IB1', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM15', 'VIN1', 'VDD', 'VOUT1', 'VOUT1', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM2', 'x5', 'x100', 'VDD', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM1', 'x107', 'VB1', 'VDD', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM3', 'x100', 'x100', 'VDD', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM4', 'VB1', 'VB1', 'VDD', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM5', 'x113', 'VB1', 'VDD', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM6', 'VB1', 'VB1', 'VDD', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM7', 'VB2', 'VB2', 'VDD', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM8', 'VB2', 'VB2', 'VDD', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM10', 'x38', 'VDD', 'VDD', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM12', 'x105', 'x5', 'x105', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM9', 'VSS', 'IB1', 'VDD', 'VSS', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM11', 'VDD', 'VDD', 'VDD', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM13', 'x105', 'VB3', 'VDD', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.R('R3', 'x111', 'VSS', 1@u_kΩ)
circuit.R('R1', 'x35', 'VSS', 1@u_kΩ)
circuit.R('R2', 'VB1', 'VSS', 1@u_kΩ)
circuit.R('R4', 'VOUT1', 'x111', 1@u_kΩ)

# Operating Point Simulation
simulator = circuit.simulator(temperature=25, nominal_temperature=25)
analysis = simulator.operating_point()
print('\nOperating Point Results:')
for node in analysis.nodes.values():
    print(f'Node {node}: {float(node):.2f} V')
for branch in analysis.branches.values():
    print(f'Branch {branch}: {float(branch):.2e} A')