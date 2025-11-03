import torch
from torch.nn import functional as F
import numpy as np
import csv
import os
from Models.GPT import GPTLanguageModel

# hyperparameters
block_size = 1024 
device = 'cuda:0' if torch.cuda.is_available() else 'cpu'
print(device)
n_embd = 384
n_head = 6
n_layer = 6
dropout = 0.2
# ------------

filename = 'Inference'

torch.manual_seed(1337)

# Tokenizer
# Define the device base names
nm_np_bases = ["{}_D", "{}_G", "{}_S", "{}_B"]
npn_pnp_bases = ["{}_C", "{}_B", "{}_E"]
c_r_l_i_bases = ["{}_P", "{}_N"]
xor_bases = ["{}_A", "{}_B", "{}_VDD", "{}_VSS", "{}_Y"]
pfd_bases = ["{}_A", "{}_B", "{}_QA", "{}_QB", "{}_VDD", "{}_VSS"]
inverter_bases = ["{}_A", "{}_Q", "{}_VDD", "{}_VSS"]
transmission_gate_bases = ["{}_A", "{}_B", "{}_C", "{}_VDD", "{}_VSS"]

# Initialize the list of NM, PM, C, R, L, I, VIN, VB, VOUT devices, and additional entries
devices = []
for prefix in ["NM", "PM"]:
    for i in range(1, 35):
        devices.append(f"{prefix}{i}")
        for base in nm_np_bases:
            devices.append(base.format(f"{prefix}{i}"))

for prefix in ["NPN", "PNP"]:
    for i in range(1, 27):
        devices.append(f"{prefix}{i}")
        for base in npn_pnp_bases:
            devices.append(base.format(f"{prefix}{i}"))

for i in range(1, 28):
    devices.append(f"R{i}")
    for base in c_r_l_i_bases:
        devices.append(base.format(f"R{i}"))

for i in range(1, 16):
    devices.append(f"C{i}")
    for base in c_r_l_i_bases:
        devices.append(base.format(f"C{i}"))

for i in range(1, 24):
    devices.append(f"L{i}")
    for base in c_r_l_i_bases:
        devices.append(base.format(f"L{i}"))

for i in range(1, 8):
    devices.append(f"DIO{i}")
    for base in c_r_l_i_bases:
        devices.append(base.format(f"DIO{i}"))

for i in range(1, 2):
    devices.append(f"XOR{i}")
    for base in xor_bases:
        devices.append(base.format(f"XOR{i}"))

for i in range(1, 2):
    devices.append(f"PFD{i}")
    for base in pfd_bases:
        devices.append(base.format(f"PFD{i}"))

for i in range(1, 11):
    devices.append(f"INVERTER{i}")
    for base in inverter_bases:
        devices.append(base.format(f"INVERTER{i}"))

for i in range(1, 13):
    devices.append(f"TRANSMISSION_GATE{i}")
    for base in transmission_gate_bases:
        devices.append(base.format(f"TRANSMISSION_GATE{i}"))

for i in range(1, 11):
    devices.append(f"VIN{i}")

for i in range(1, 3):
    devices.append(f"IIN{i}")

for i in range(1, 7):
    devices.append(f"VOUT{i}")

for i in range(1, 5):
    devices.append(f"IOUT{i}")

for i in range(1, 11):
    devices.append(f"VB{i}")

for i in range(1, 7):
    devices.append(f"IB{i}")

for i in range(1, 21):
    devices.append(f"VCONT{i}")

for i in range(1, 9):
    devices.append(f"VCLK{i}")

for i in range(1, 3):
    devices.append(f"VCM{i}")

for i in range(1, 3):
    devices.append(f"VREF{i}")

for i in range(1, 3):
    devices.append(f"IREF{i}")

for i in range(1, 3):
    devices.append(f"VRF{i}")

for i in range(1, 5):
    devices.append(f"VLO{i}")

for i in range(1, 3):
    devices.append(f"VIF{i}")

for i in range(1, 5):
    devices.append(f"VBB{i}")

for i in range(1, 3):
    devices.append(f"LOGICA{i}")

for i in range(1, 3):
    devices.append(f"LOGICB{i}")

for i in range(1, 3):
    devices.append(f"LOGICD{i}")

for i in range(1, 3):
    devices.append(f"LOGICF{i}")

for i in range(1, 3):
    devices.append(f"LOGICG{i}")

for i in range(1, 3):
    devices.append(f"LOGICQ{i}")

for i in range(1, 2):
    devices.append(f"LOGICQA{i}")

for i in range(1, 2):
    devices.append(f"LOGICQB{i}")

for i in range(1, 3):
    devices.append(f"VLATCH{i}")

for i in range(1, 2):
    devices.append(f"VHOLD{i}")

for i in range(1, 3):
    devices.append(f"VTRACK{i}")

# Adding the additional entries
additional_entries = ["VDD", "VSS", "TRUNCATE"]
# circuit type tokens (must match training vocabulary)
circuit_type_tokens = [
    "CIRCUIT_Opamp", "CIRCUIT_Comparator", "CIRCUIT_Oscillator",
    "CIRCUIT_Current_Mirror", "CIRCUIT_Differential_Amp", "CIRCUIT_LNA",
    "CIRCUIT_Mixer", "CIRCUIT_LDO", "CIRCUIT_Bandgap_Ref",
    "CIRCUIT_Single_Stage_Amp", "CIRCUIT_Power_Amp",
    "CIRCUIT_Voltage_Regulator", "CIRCUIT_Filter",
    "CIRCUIT_Switched_Cap", "CIRCUIT_General"
]
devices.extend(additional_entries)
devices.extend(circuit_type_tokens)

# Create a mapping from device names to integers and vice versa
stoi = { device: i for i, device in enumerate(devices) }
itos = { i:device for i,device in enumerate(devices) }
vocab_size = len(devices)

# Print the results
print("Devices sample:", devices[:8], "...", devices[-8:])
print("Vocabulary size:", len(devices))
print("Device to index mapping sample:", {k: stoi[k] for k in list(stoi.keys())[:8]})
print("Index to device mapping sample:", {k: itos[k] for k in list(itos.keys())[:8]})

encode = lambda s: [stoi[c] for c in s] # encoder: take a string, output a list of integers
decode = lambda l: '->'.join([itos[i] for i in l]) + '->'

model = GPTLanguageModel(vocab_size, n_embd, block_size, n_head, n_layer, dropout)
m = model.to(device)
print(sum(p.numel() for p in m.parameters())/1e6, 'M parameters')

savemodel_name = 'Pretrain_multiGPU.pth'
model.load_state_dict(torch.load(savemodel_name),strict=False)
run = 1000
os.makedirs(filename, exist_ok=True)

def generate_with_banned(model, context, max_new_tokens=1024, banned_indices=None, temperature=0.7):
    """
    Autoregressive generation that forbids tokens in banned_indices from being sampled.
    context: LongTensor shape (B, T)
    banned_indices: list or tensor of token indices to ban (these logits will be set very low)
    """
    if banned_indices is None:
        banned_indices = []
    # ensure tensor on same device
    banned_tensor = torch.tensor(banned_indices, dtype=torch.long, device=context.device) if len(banned_indices)>0 else None
    idx = context
    for _ in range(max_new_tokens):
        idx_cond = idx[:, -model.block_size:]
        logits, _ = model(idx_cond)
        logits = logits[:, -1, :]
        logits = logits / temperature
        if banned_tensor is not None and banned_tensor.numel()>0:
            # set banned token logits to large negative so softmax~0
            logits.index_fill_(1, banned_tensor, -1e9)
        probs = F.softmax(logits, dim=-1)
        idx_next = torch.multinomial(probs, num_samples=1)
        idx = torch.cat((idx, idx_next), dim=1)
    return idx


# Determine banned token indices: circuit type tokens should not be generated further
banned_indices = [stoi[t] for t in circuit_type_tokens if t in stoi]

# Allow specifying desired circuit type via env var CIRCUIT_TYPE or default to CIRCUIT_Opamp
desired_circuit = os.environ.get('CIRCUIT_TYPE', 'CIRCUIT_Opamp')
if desired_circuit not in stoi:
    raise ValueError(f"Desired circuit type '{desired_circuit}' not in vocabulary")

vss_idx = stoi.get('VSS')
if vss_idx is None:
    raise ValueError("VSS token not found in vocabulary")

for i in range(run):
    # context: [CIRCUIT_xxx, VSS]
    context = torch.tensor([[stoi[desired_circuit], vss_idx]], dtype=torch.long, device=device)
    save_dir = filename + '/run'+str(i)+'.txt'
    sequence = generate_with_banned(m, context, max_new_tokens=1024, banned_indices=banned_indices)[0].tolist()
    open(save_dir, 'w').write(decode(sequence))