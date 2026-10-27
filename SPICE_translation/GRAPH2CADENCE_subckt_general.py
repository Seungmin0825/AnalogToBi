#!/usr/bin/env python3
"""
GRAPH2CADENCE_subckt_general - bipartite-graph-to-Spectre netlist converter.

Translates generated circuit-topology sequences (bipartite device/net graphs
serialized as token streams) into Cadence Spectre subckt netlists, ready for
batch simulation with the run_tb_<category>.py testbenches.

Pipeline (per circuit type):
  1. Discover the Inference_CIRCUIT_<Type>_masked/ folders of a generation run
     (--run-dir) and select only the run
     IDs listed under 'valid_novel_ids' in the run's valid_novel_ids_<Type>.json,
     written by METRIC_Valid_n_Novel.py --write-ids.
  2. Run an inline electrical rule check (ERC) on every run<id>.txt sequence:
     token-alternation integrity, device pin completeness, pin-to-net
     consistency, and minimum net connectivity. Violating runs are rejected.
  3. Parse the token stream into devices (MOSFET/BJT/R/C/L/diode), external
     ports, and an undirected device-net graph; assign device pins from the
     edge labels.
  4. Emit a self-contained Spectre subckt with canonical port ordering
     (rails, inputs, outputs, others) and default GPDK045 device parameters.

Outputs (under --out-dir, default: the run directory):
  SPICE_Inference_<Type>/SPICE_Inference_<Type>_run<id>.scs

The token vocabulary and the ERC tests come from CORE_Vocab.py and CORE_ERC.py
in the package root.

Usage:
    python SPICE_translation/GRAPH2CADENCE_subckt_general.py --run-dir runs/AnalogToBi                 # all types
    python SPICE_translation/GRAPH2CADENCE_subckt_general.py --run-dir runs/AnalogToBi --folder Opamp  # one type
    python SPICE_translation/GRAPH2CADENCE_subckt_general.py --run-dir runs/AnalogToBi --verbose       # per-file details

Options:
    --folder CIRCUIT   Restrict processing to one circuit type. Must match an
                       Inference_CIRCUIT_<CIRCUIT>_masked/ folder
                       (case-insensitive).
    --verbose          Print per-file parser output.

Supported circuit types:
    Opamp, LDO, Comparator, Bandgap_Ref, Power_converter,
    Oscillator, General, Mirror, Mixer, Power_Amp, PLL,
    Filter, Voltage_Regulator, Switched_Cap, ADC_DAC
"""

import re
import sys
import json
import argparse
import contextlib
import io
from collections import defaultdict
from pathlib import Path

import networkx as nx

# ===============================================================================
#  Device parameter defaults  (GPDK045 / AnalogLib)
# ===============================================================================
NMOS_MODEL  = 'g45n1svt'
PMOS_MODEL  = 'g45p1svt'
NMOS_PARAMS = 'w=10u l=1u nf=1 m=1'
PMOS_PARAMS = 'w=15u l=1u nf=2 m=1'
# BJT model names as used in the GPDK045 Spectre library.
NPN_MODEL   = 'g45vnpn2'
PNP_MODEL   = 'g45vpnp2'
NPN_PARAMS  = 'area=1'
PNP_PARAMS  = 'area=1'
DEFAULT_C   = '1p'
DEFAULT_R   = '10k'
DEFAULT_L   = '1n'

SUPPORTED_FOLDERS = [
    'Opamp', 'LDO', 'Comparator', 'Bandgap_Ref', 'Power_converter',
    'Oscillator', 'General', 'Mirror', 'Mixer', 'Power_Amp', 'PLL',
    'Filter', 'Voltage_Regulator', 'Switched_Cap', 'ADC_DAC',
]

# ===============================================================================
#  Vocabulary / token constants
# ===============================================================================
# The vocabulary has a single definition in the package root (CORE_Vocab.py);
# this script lives one directory down, so the root goes on the import path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from CORE_Vocab import passive_edges, all_edge_types

# The four ERC tests come from CORE_ERC.py in the package root, which is the
# single definition of what "valid" means.
from CORE_ERC import (check_sequence_first_test as _erc_test1,
                      check_sequence_second_test as _erc_test2,
                      check_sequence_third_test as _erc_test3,
                      check_internal_net_connections as _erc_test4)

PASSIVE_EDGES = passive_edges
ALL_EDGES     = all_edge_types

POWER_RAILS         = {'VSS', 'VDD'}
CIRCUIT_TYPE_TOKENS = {
    'CIRCUIT_Opamp', 'CIRCUIT_LDO', 'CIRCUIT_Bandgap_Ref',
    'CIRCUIT_Power_converter', 'CIRCUIT_Oscillator', 'CIRCUIT_General',
    'CIRCUIT_Mirror', 'CIRCUIT_Mixer', 'CIRCUIT_Power_Amp',
    'CIRCUIT_PLL', 'CIRCUIT_Filter', 'CIRCUIT_Comparator',
    'CIRCUIT_Voltage_Regulator', 'CIRCUIT_Switched_Cap', 'CIRCUIT_ADC_DAC',
}

DEVICE_PATTERN = re.compile(r'^(NM|PM|NPN|PNP|R|C|L|DIO)[0-9]+$')
EXTERNAL_PIN_RE = re.compile(
    r'^(VDD|VSS|GND'
    r'|VIN[0-9]*|VOUT[0-9]*|VB[0-9]*|VCM[0-9]*|VREF[0-9]*'
    r'|IREF[0-9]*|VRF[0-9]*|VLO[0-9]*|VCONT[0-9]*|VIF[0-9]*|VBB[0-9]*'
    r'|IIN[0-9]*|IOUT[0-9]*|IB[0-9]*)$'
)
_INPUT_PORT_RE  = re.compile(
    r'^(VIN|VREF|VCM|VB|VBB|VLO|VRF|VIF|VCONT|IIN|IB|IREF)[0-9]*$'
)
_OUTPUT_PORT_RE = re.compile(r'^(VOUT|IOUT)[0-9]*$')

# ===============================================================================
#  Device classes
# ===============================================================================
class MOSFET:
    """MOSFET record; D/G/S/B hold net names once the walk is parsed."""
    def __init__(self, name, is_pmos=False):
        self.name = name; self.is_pmos = is_pmos
        self.D = self.G = self.S = self.B = None

class BJT:
    """BJT record; C/B/E hold net names once the walk is parsed."""
    def __init__(self, name, is_pnp=False):
        self.name = name; self.is_pnp = is_pnp
        self.C = self.B = self.E = None

class Passive:
    """Two-terminal passive record (type 'R', 'C' or 'L'); P/N hold net names."""
    def __init__(self, name, comp_type):
        self.name = name; self.type = comp_type
        self.P = self.N = None

class Diode:
    """Diode record; P (anode) and N (cathode) hold net names."""
    def __init__(self, name):
        self.name = name; self.P = self.N = None

# ===============================================================================
#  Token classification helpers
# ===============================================================================
def _extract_pins_from_edge(edge_type):
    """Pin letters named by an edge token, as a list (['P', 'N'] for passive edges)."""
    if edge_type.startswith(('M_', 'B_', 'D_')):
        return list(edge_type[2:])
    if edge_type in PASSIVE_EDGES:
        return ['P', 'N']
    return []


def _load_tokens(filepath):
    """Read a generated walk file and return its tokens up to the end token."""
    with open(filepath, 'r') as f:
        content = f.read().strip()
    if not content or '->' not in content:
        return []
    cleaned = []
    for t in content.split('->'):
        t = t.strip()
        # TRUNCATE ends every walk; End is accepted as another name for it
        if t in ('TRUNCATE', 'End'):
            break
        if t:
            cleaned.append(t)
    return cleaned

def run_erc(filepath):
    """Run all four ERC tests. Returns (is_clean, total_violation_count)."""
    tokens = _load_tokens(filepath)
    if not tokens:
        return False, -1
    total = sum(len(f(tokens)) for f in (_erc_test1, _erc_test2, _erc_test3, _erc_test4))
    return total == 0, total

# ===============================================================================
#  Bipartite-graph parser
# ===============================================================================
def _parse_bipartite_sequence(filepath):
    """Parse a walk file into device records, external pins and a networkx graph."""
    tokens = _load_tokens(filepath)
    if not tokens:
        return None, None, None, None

    if tokens and tokens[0] in CIRCUIT_TYPE_TOKENS:
        tokens = tokens[1:]

    devices = {k: {} for k in ('NM', 'PM', 'NPN', 'PNP', 'R', 'C', 'L', 'DIO')}
    external_pins = set()
    graph = nx.Graph()

    def _ensure_device(tok):
        """Create the device record for a token on first sight."""
        if not DEVICE_PATTERN.match(tok):
            return
        dt = re.match(r'^[A-Z]+', tok).group()
        if tok in devices.get(dt, {}):
            return
        if dt in ('NM', 'PM'):
            devices[dt][tok] = MOSFET(tok, is_pmos=(dt == 'PM'))
        elif dt in ('NPN', 'PNP'):
            devices[dt][tok] = BJT(tok, is_pnp=(dt == 'PNP'))
        elif dt in ('R', 'C', 'L'):
            devices[dt][tok] = Passive(tok, dt)
        elif dt == 'DIO':
            devices['DIO'][tok] = Diode(tok)
        graph.add_node(tok, node_type='device')

    def _ensure_net(tok):
        """Register a net or port token as a graph node."""
        if EXTERNAL_PIN_RE.match(tok):
            external_pins.add(tok)
            graph.add_node(tok, node_type='port')
        else:
            graph.add_node(tok, node_type='net')

    i, prev_node = 0, None
    while i < len(tokens):
        tok = tokens[i]
        if tok in ALL_EDGES:
            if i + 1 < len(tokens):
                nxt = tokens[i + 1]
                if DEVICE_PATTERN.match(nxt):
                    _ensure_device(nxt)
                else:
                    _ensure_net(nxt)
                if prev_node:
                    graph.add_edge(prev_node, nxt, edge_type=tok)
                prev_node = nxt
                i += 2
            else:
                break
        else:
            if DEVICE_PATTERN.match(tok):
                _ensure_device(tok)
            else:
                _ensure_net(tok)
            prev_node = tok
            i += 1

    devices = {k: list(v.values()) for k, v in devices.items()}
    return tokens, devices, sorted(external_pins), graph


def _assign_device_pins(tokens, devices, graph):
    """Fill the pin fields of each device from the device-edge-net triples of the walk."""
    device_lookup = {dev.name: dev for dl in devices.values() for dev in dl}
    i = 0
    while i < len(tokens) - 2:
        t1, edge, t2 = tokens[i], tokens[i + 1], tokens[i + 2]
        if edge not in ALL_EDGES:
            i += 1
            continue
        if t1 in device_lookup and t2 not in device_lookup:
            dev, net = device_lookup[t1], t2
        elif t2 in device_lookup and t1 not in device_lookup:
            dev, net = device_lookup[t2], t1
        else:
            i += 1
            continue
        if isinstance(dev, Passive):
            if dev.P is None:
                dev.P = net
            elif dev.N is None and net != dev.P:
                dev.N = net
        else:
            for pin in _extract_pins_from_edge(edge):
                if hasattr(dev, pin) and getattr(dev, pin) is None:
                    setattr(dev, pin, net)
        i += 2

# ===============================================================================
#  Subckt generation
# ===============================================================================
def _norm_net(name):
    """Lower-case internal net names; rails and ports are left unchanged."""
    return name.lower() if re.match(r'^NET\d+$', name, re.IGNORECASE) else name

def _order_ports(external_pins):
    """Order subcircuit ports: power rails, inputs, outputs, then the rest."""
    pin_set  = set(external_pins)
    vdd_vss  = [p for p in ('VDD', 'VSS') if p in pin_set]
    in_pins  = sorted(p for p in pin_set if _INPUT_PORT_RE.match(p))
    out_pins = sorted(p for p in pin_set if _OUTPUT_PORT_RE.match(p))
    rest     = sorted(p for p in pin_set
                      if p not in vdd_vss and p not in in_pins and p not in out_pins)
    return vdd_vss + in_pins + out_pins + rest

def generate_cadence_subckt(output_path, devices, external_pins, circuit_name):
    """Write a Spectre subcircuit netlist for the parsed circuit."""
    ports = _order_ports(external_pins)
    lines = [
        '// Generated subckt netlist',
        f'// Cell name: {circuit_name}',
        f'subckt {circuit_name} {" ".join(ports)}',
    ]
    dc = dict.fromkeys(('NM', 'PM', 'NPN', 'PNP', 'C', 'R', 'L', 'DIO'), 0)

    for dev in devices.get('NM', []):
        D = _norm_net(dev.D or 'UNCONNECTED')
        G = _norm_net(dev.G or 'UNCONNECTED')
        S = _norm_net(dev.S or 'VSS')
        B = _norm_net(dev.B or 'VSS')
        lines.append(f'    NM{dc["NM"]} ({D} {G} {S} {B}) {NMOS_MODEL} {NMOS_PARAMS}')
        dc['NM'] += 1

    for dev in devices.get('PM', []):
        D = _norm_net(dev.D or 'UNCONNECTED')
        G = _norm_net(dev.G or 'UNCONNECTED')
        S = _norm_net(dev.S or 'VDD')
        B = _norm_net(dev.B or 'VDD')
        lines.append(f'    PM{dc["PM"]} ({D} {G} {S} {B}) {PMOS_MODEL} {PMOS_PARAMS}')
        dc['PM'] += 1

    # Spectre BJT syntax: Qx (C B E substrate) model params
    for dev in devices.get('NPN', []):
        C   = _norm_net(dev.C or 'UNCONNECTED')
        B_n = _norm_net(dev.B or 'UNCONNECTED')
        E   = _norm_net(dev.E or 'VSS')
        lines.append(f'    NPN{dc["NPN"]} ({C} {B_n} {E} VSS) {NPN_MODEL} {NPN_PARAMS}')
        dc['NPN'] += 1

    for dev in devices.get('PNP', []):
        C   = _norm_net(dev.C or 'UNCONNECTED')
        B_n = _norm_net(dev.B or 'UNCONNECTED')
        E   = _norm_net(dev.E or 'VDD')
        lines.append(f'    PNP{dc["PNP"]} ({C} {B_n} {E} VDD) {PNP_MODEL} {PNP_PARAMS}')
        dc['PNP'] += 1

    for dev in devices.get('C', []):
        P = _norm_net(dev.P or 'UNCONNECTED')
        N = _norm_net(dev.N or 'VSS')
        lines.append(f'    C{dc["C"]} ({P} {N}) capacitor c={DEFAULT_C}')
        dc['C'] += 1

    for dev in devices.get('R', []):
        P = _norm_net(dev.P or 'UNCONNECTED')
        N = _norm_net(dev.N or 'VSS')
        lines.append(f'    R{dc["R"]} ({P} {N}) resistor r={DEFAULT_R}')
        dc['R'] += 1

    for dev in devices.get('L', []):
        P = _norm_net(dev.P or 'UNCONNECTED')
        N = _norm_net(dev.N or 'VSS')
        lines.append(f'    L{dc["L"]} ({P} {N}) inductor l={DEFAULT_L}')
        dc['L'] += 1

    for dev in devices.get('DIO', []):
        P = _norm_net(dev.P or 'UNCONNECTED')
        N = _norm_net(dev.N or 'VSS')
        lines.append(f'    D{dc["DIO"]} ({P} {N}) diode')
        dc['DIO'] += 1

    lines.append(f'ends {circuit_name}')
    lines.append('')
    output_path.write_text('\n'.join(lines))

# ===============================================================================
#  Main
# ===============================================================================
@contextlib.contextmanager
def _quiet():
    """Context manager that silences stdout."""
    old, sys.stdout = sys.stdout, io.StringIO()
    try:
        yield
    finally:
        sys.stdout = old


def _discover_circuit_types(base_dir):
    """Return [(circuit_type, input_dir), ...] for every masked inference folder."""
    found = []
    for d in sorted(base_dir.glob('Inference_CIRCUIT_*_masked')):
        if not d.is_dir():
            continue
        m = re.match(r'^Inference_CIRCUIT_(.+)_masked$', d.name)
        if m:
            found.append((m.group(1), d))
    return found


def _load_valid_novel_ids(base_dir, ctype):
    """Load the valid_novel_ids set for a circuit type, or None if unavailable."""
    json_path = base_dir / f'valid_novel_ids_{ctype}.json'
    if not json_path.exists():
        return None
    try:
        data = json.loads(json_path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    ids = data.get('valid_novel_ids')
    if ids is None:
        return None
    return set(ids)


def _process_circuit(run_dir, out_dir, ctype, input_dir, verbose):
    """Convert the valid & novel runs of one circuit type to Spectre subcircuits."""
    valid_ids = _load_valid_novel_ids(run_dir, ctype)
    print(f"\n--- {ctype}")
    if valid_ids is None:
        print(f"  [SKIP] valid_novel_ids_{ctype}.json not found in {run_dir} - "
              f"produce it with: python METRIC_Valid_n_Novel.py <run_dir> --write-ids")
        return None

    output_dir = out_dir / f'SPICE_Inference_{ctype}'
    output_dir.mkdir(parents=True, exist_ok=True)

    input_files = sorted(
        input_dir.glob('run*.txt'),
        key=lambda p: int(re.search(r'\d+', p.stem).group()),
    )

    print(f"  Input       : {input_dir.name}")
    print(f"  Output      : {output_dir}")
    print(f"  Run files   : {len(input_files)}")
    print(f"  valid_novel : {len(valid_ids)}")

    stats = {
        'total': 0, 'erc_fail': 0, 'parse_error': 0, 'written': 0,
    }

    for fpath in input_files:
        run_id = int(re.search(r'\d+', fpath.stem).group())
        if run_id not in valid_ids:
            continue
        stats['total'] += 1

        # ERC
        is_clean, n_viol = run_erc(str(fpath))
        if not is_clean:
            if n_viol == -1:
                print(f"  [SKIP] {fpath.name}: empty/invalid")
                stats['parse_error'] += 1
            else:
                print(f"  [ERC_FAIL] {fpath.name}: {n_viol} violation(s)")
                stats['erc_fail'] += 1
            continue

        # Parse
        try:
            with (_quiet() if not verbose else contextlib.nullcontext()):
                tokens, devices, external_pins, graph = _parse_bipartite_sequence(str(fpath))
        except Exception as exc:
            print(f"  [ERROR] {fpath.name}: {exc}")
            stats['parse_error'] += 1
            continue

        if tokens is None:
            print(f"  [SKIP] {fpath.name}: empty/invalid sequence")
            stats['parse_error'] += 1
            continue

        _assign_device_pins(tokens, devices, graph)

        circuit_name = f'SPICE_Inference_{ctype}_run{run_id}'
        output_path  = output_dir / f'SPICE_Inference_{ctype}_run{run_id}.scs'
        generate_cadence_subckt(output_path, devices, external_pins, circuit_name)

        nm  = len(devices.get('NM',  []))
        pm  = len(devices.get('PM',  []))
        c   = len(devices.get('C',   []))
        r   = len(devices.get('R',   []))
        ports_str = ' '.join(_order_ports(external_pins))
        print(f"  [OK] {output_path.name}  NM={nm} PM={pm} C={c} R={r}  [{ports_str}]")
        stats['written'] += 1

    print(f"  -- {ctype}: written={stats['written']} "
          f"erc_fail={stats['erc_fail']} parse_err={stats['parse_error']} "
          f"of {stats['total']} valid_novel runs")
    return stats


def main():
    """Command-line entry point."""
    parser = argparse.ArgumentParser(
        description='General Graph-to-Cadence Spectre Subckt Converter. '
                    'Converts only valid & novel runs into SPICE_Inference_<Type>/ folders.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='Supported circuit types:\n  ' + ', '.join(SUPPORTED_FOLDERS),
    )
    parser.add_argument(
        '--folder', default=None, metavar='CIRCUIT',
        help='Restrict to a single circuit type (e.g. Opamp, LDO, Comparator). '
             'Must match an Inference_CIRCUIT_<CIRCUIT>_masked/ folder (case-insensitive). '
             'If omitted, all circuit types are processed.',
    )
    parser.add_argument(
        '--run-dir', required=True, metavar='DIR',
        help='Generation run directory holding Inference_CIRCUIT_<Type>_masked/ and '
             'valid_novel_ids_<Type>.json.',
    )
    parser.add_argument(
        '--out-dir', default=None, metavar='DIR',
        help='Where SPICE_Inference_<Type>/ folders are written (default: --run-dir).',
    )
    parser.add_argument(
        '--verbose', action='store_true',
        help='Print per-file parse output',
    )
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    out_dir = Path(args.out_dir) if args.out_dir else run_dir
    all_types = _discover_circuit_types(run_dir)

    if not all_types:
        print(f"[ERROR] No Inference_CIRCUIT_*_masked/ folders found in {run_dir}.")
        sys.exit(1)

    if args.folder:
        wanted = args.folder.lower()
        selected = [(t, d) for (t, d) in all_types if t.lower() == wanted]
        if not selected:
            print(f"[ERROR] No Inference_CIRCUIT_{args.folder}_masked/ folder found.")
            print(f"Available: {', '.join(t for t, _ in all_types)}")
            sys.exit(1)
    else:
        selected = all_types

    print(f"Run directory  : {run_dir}")
    print(f"Output         : {out_dir}")
    print(f"Circuit types  : {len(selected)}")

    grand = {'total': 0, 'written': 0, 'erc_fail': 0, 'parse_error': 0}
    for ctype, input_dir in selected:
        stats = _process_circuit(run_dir, out_dir, ctype, input_dir, args.verbose)
        if stats:
            for k in grand:
                grand[k] += stats.get(k, 0)

    print(f"\n{'='*60}")
    print(f"Circuit types processed : {len(selected)}")
    print(f"Total valid_novel runs  : {grand['total']}")
    print(f"Written                 : {grand['written']}")
    print(f"ERC fail                : {grand['erc_fail']}")
    print(f"Parse err               : {grand['parse_error']}")


if __name__ == '__main__':
    main()
