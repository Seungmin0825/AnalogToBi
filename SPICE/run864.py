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
circuit.V('vb4', 'VB4', circuit.gnd, 0.9@u_V)
circuit.V('vb5', 'VB5', circuit.gnd, 0.9@u_V)
circuit.V('vdd', 'VDD', circuit.gnd, 1.8@u_V)
circuit.V('vin1', 'VIN1', circuit.gnd, 0.9@u_V)
circuit.V('vout1', 'VOUT1', circuit.gnd, 0.9@u_V)
circuit.V('vref1', 'VREF1', circuit.gnd, 0.9@u_V)
circuit.V('vss', 'VSS', circuit.gnd, 0.0@u_V)

# Nets
circuit.C('C3', 'VSS', 'VSS', 1@u_pF)
circuit.C('C1', 'VOUT1', 'VOUT1', 1@u_pF)
circuit.C('C2', 'VSS', 'x103', 1@u_pF)
circuit.D('DIO1', 'x103', 'VSS', model='default')
circuit.MOSFET('NM6', 'x2', 'x2', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM1', 'x16', 'x2', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM2', 'x18', 'x2', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM5', 'x118', 'x118', 'x2', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM3', 'VSS', 'x118', 'x16', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM4', 'VSS', 'x118', 'x18', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM7', 'VSS', 'VB4', 'VB3', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM8', 'VB4', 'VB3', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM9', 'VB3', 'VSS', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM10', 'VSS', 'VSS', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM11', 'VSS', 'VSS', 'VSS', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM14', 'VSS', 'VSS', 0, 0, model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM17', 'VIN1', 'VSS', 'VOUT1', 0, model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM12', 'VSS', 'VSS', 'IB1', 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM13', 'VIN1', 'VSS', 'IB1', 'IB1', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM16', 'VSS', 'VSS', 'VSS', 0, model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('NM15', 'VSS', 0, 0, 'VSS', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM2', 'x16', 'VREF1', 'VSS', 'x58', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM1', 'x18', 'VSS', 'VSS', 'x58', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM4', 'VSS', 'VB2', 'VSS', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM5', 'VSS', 'VB2', 'VSS', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM8', 'x118', 'VSS', 'VDD', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM3', 'VSS', 'VB1', 'VDD', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM6', 'VSS', 'VSS', 'VDD', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM7', 'VSS', 'VSS', 'VDD', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM9', 'VSS', 'VSS', 'VDD', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM10', 'VB4', 'VSS', 'VDD', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM11', 'VSS', 'VSS', 'VDD', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM16', 'VSS', 'x52', 'VDD', 'VIN1', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM17', 'VSS', 0, 'VIN1', 0, model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM15', 'VSS', 'VSS', 'VSS', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM14', 'VSS', 'VSS', 'VDD', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM12', 'VSS', 'VSS', 'VDD', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM13', 'VSS', 'VSS', 'VDD', 'VDD', model='pmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('PM18', 'VSS', 'VB5', 'VDD', 0, model='pmos_model', w=50e-6, l=1e-6)
circuit.R('R2', 0, 'VSS', 1@u_kΩ)
circuit.R('R1', 'VOUT1', 'VSS', 1@u_kΩ)
circuit.R('R4', 'VOUT1', 'VSS', 1@u_kΩ)
circuit.R('R3', 'VSS', 'VSS', 1@u_kΩ)

# Operating Point Simulation
simulator = circuit.simulator(temperature=25, nominal_temperature=25)
analysis = simulator.operating_point()
print('\nOperating Point Results:')
for node in analysis.nodes.values():
    print(f'Node {node}: {float(node):.2f} V')
for branch in analysis.branches.values():
    print(f'Branch {branch}: {float(branch):.2e} A')