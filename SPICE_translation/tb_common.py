#!/usr/bin/env python3
"""
tb_common - shared module for SPICE_Inference_* batch testbenches

Functionality shared by each run_tb_<category>.py script:
  - subckt scanning / required-port filtering
  - automatic IB*/IIN* current direction and VB*/VBB* bias voltage decisions
  - automatic source generation for misc ports (VCONT/VCM/VREF/IOUT/...)
  - Spectre execution (GPDK045, psfascii)
  - PSF ascii parsers (dc op / dc sweep / ac / tran)
  - console header/footer, incremental summary CSV writing
"""

import os
import re
import csv
import shutil
import argparse
import itertools
import subprocess
from pathlib import Path

import numpy as np

# --- Paths / env --------------------------------------------------------------
BASE_DIR    = Path(__file__).parent
# Site configuration. Set these three environment variables (or edit the defaults):
#   GPDK045_LIB  path to the GPDK045 Spectre model file (gpdk045.scs)
#   SPECTRE_BIN  Cadence Spectre binary (falls back to `spectre` on PATH)
#   LM_LICENSE_FILE  Cadence license server, as port@host
GPDK045_LIB = os.environ.get('GPDK045_LIB', '/path/to/gpdk045.scs')
SPECTRE_BIN = os.environ.get('SPECTRE_BIN', '/path/to/spectre')
LICENSE     = os.environ.get('LM_LICENSE_FILE', 'port@your-license-server')

IB_CURRENT  = 100e-6   # default IB* bias current
IIN_CURRENT = 10e-6    # default IIN* current (misc-port handling)

IND = ' ' * 11         # indent for per-run result lines

_MOS_PAT  = re.compile(r'^\s+(NM|PM)\d+\s+\(([^)]+)\)\s+g45[np]1svt')
# accepts the converter's g45v[np]pn* models and the gpdk045_[np]pn aliases
_BJT_PAT  = re.compile(r'^\s+(NPN|PNP)\d+\s+\(([^)]+)\)\s+(?:gpdk045_[np]pn|g45v[np]pn\d*)')
_PASS_PAT = re.compile(r'^\s+[CRL]\d+\s+\(([^)]+)\)')
_NUM      = r'[-+]?\d[\d.eE+-]*'


# --- Subckt scanning ----------------------------------------------------------
def run_id_of(path):
    """Integer run id encoded in a run<N> file name."""
    return int(re.search(r'run(\d+)', path.stem).group(1))


def list_subckts(subckt_dir):
    """All subckts in a directory -> [(path, subckt_name, ports_list)] (run-id order)."""
    out = []
    for f in sorted(subckt_dir.glob('*.scs'), key=run_id_of):
        with open(f) as fh:
            for line in fh:
                m = re.match(r'^subckt\s+(\S+)\s+(.+)$', line.strip())
                if m:
                    out.append((f, m.group(1), m.group(2).split()))
                    break
    return out


def collect_targets(subckt_dir, required, run_ids=None, limit=None,
                    extra_filter=None):
    """
    Select only subckts containing every port in `required` (upper-case set).
    extra_filter(path, name, ports)->bool adds a per-category condition.
    returns (targets, n_port_skip)
    """
    targets, n_skip = [], 0
    for f, name, ports in list_subckts(subckt_dir):
        pset = set(p.upper() for p in ports)
        if not required.issubset(pset):
            n_skip += 1
            continue
        if extra_filter and not extra_filter(f, name, ports):
            n_skip += 1
            continue
        if run_ids is not None and run_id_of(f) not in run_ids:
            continue
        targets.append((f, name, ports))
    if limit:
        targets = targets[:limit]
    return targets, n_skip


# --- Bias-port analysis -------------------------------------------------------
def determine_ib_direction(scs_file, port):
    """
    Decide current direction from the MOSFET D/S positions connected to the port.
    'out' = current flows out of the circuit (attach a sink),
    'in'  = current is injected into the circuit.
    Returns None on passive connection or conflicting evidence.
    """
    pu = port.upper()
    directions = []
    with open(scs_file) as f:
        for line in f:
            mp = _PASS_PAT.match(line)
            if mp and pu in [n.upper() for n in mp.group(1).split()]:
                return None
            m = _MOS_PAT.match(line)
            if not m:
                continue
            nodes = [n.upper() for n in m.group(2).split()]  # D G S B
            if pu not in nodes:
                continue
            pos = nodes.index(pu)
            if pos in (1, 3):
                continue
            if m.group(1) == 'NM':
                directions.append('out' if pos == 2 else 'in')
            else:
                directions.append('out' if pos == 0 else 'in')
    if not directions:
        return None
    return directions[0] if len(set(directions)) == 1 else None


def determine_vb_voltage(scs_file, port, vdd):
    """MOSFET types on VB*: NMOS only->VDD*0.25, PMOS only->VDD*0.75, mixed->VDD*0.5."""
    pu = port.upper()
    nmos = pmos = 0
    with open(scs_file) as f:
        for line in f:
            m = _MOS_PAT.match(line)
            if not m:
                continue
            nodes = [n.upper() for n in m.group(2).split()]
            if pu not in nodes or nodes.index(pu) == 3:
                continue
            if m.group(1) == 'NM':
                nmos += 1
            else:
                pmos += 1
    if nmos and not pmos:
        return round(vdd * 0.25, 3)
    if pmos and not nmos:
        return round(vdd * 0.75, 3)
    return round(vdd * 0.5, 3)


def determine_vbb_voltage(scs_file, port, vdd):
    """BJT types on VBB*: NPN->0.8V, PNP->VDD-0.8V, mixed/none->VDD/2."""
    pu = port.upper()
    npn = pnp = 0
    with open(scs_file) as f:
        for line in f:
            m = _BJT_PAT.match(line)
            if not m:
                continue
            nodes = [n.upper() for n in m.group(2).split()]  # C B E sub
            if pu not in nodes:
                continue
            if m.group(1) == 'NPN':
                npn += 1
            else:
                pnp += 1
    if npn and not pnp:
        return 0.8
    if pnp and not npn:
        return round(vdd - 0.8, 3)
    return round(vdd * 0.5, 3)


def classify_misc_ports(scs_file, ports_list, handled, vdd, vcont_v=None,
                        ib_dirs=None):
    """
    Auto-generate source lines for ports not in `handled` (upper-case set).
    ib_dirs: direction overrides for indeterminate IB ports {'IB1': 'out'|'in'}.
    returns (src_lines, info_strs, save_only_nodes, skip_reason)
      skip_reason != None means this circuit must be skipped
      (e.g. indeterminate IB with no override).
    """
    ib_dirs = ib_dirs or {}
    lines, infos, saves = [], [], []
    for p in ports_list:
        pu = p.upper()
        if pu in handled:
            continue
        pl = p.lower()
        base = re.sub(r'\d+$', '', pu)

        if base == 'VB':
            v = determine_vb_voltage(scs_file, p, vdd)
            lines.append(f'V{pl} ({pl} 0) vsource dc={v} type=dc  // {pu} bias')
            infos.append(f'{pu}={v}V')
        elif base == 'VBB':
            v = determine_vbb_voltage(scs_file, p, vdd)
            lines.append(f'V{pl} ({pl} 0) vsource dc={v} type=dc  // {pu} BJT bias')
            infos.append(f'{pu}={v}V')
        elif base == 'VCONT':
            v = round(vcont_v if vcont_v is not None else vdd / 2, 3)
            lines.append(f'V{pl} ({pl} 0) vsource dc={v} type=dc  // {pu} control')
            infos.append(f'{pu}={v}V')
        elif base in ('VCM', 'VREF'):
            v = round(vdd / 2, 3)
            lines.append(f'V{pl} ({pl} 0) vsource dc={v} type=dc  // {pu}')
            infos.append(f'{pu}={v}V')
        elif base == 'IB':
            d = determine_ib_direction(scs_file, p)
            mark = ''
            if d is None:
                d = ib_dirs.get(pu)
                mark = '?'          # indeterminate -> mark override usage
                if d is None:
                    return None, None, None, f'{pu} direction indeterminate'
            if d == 'out':
                lines.append(f'I{pl} ({pl} 0) isource dc={IB_CURRENT:g}  // {pu} sink')
            else:
                lines.append(f'I{pl} (0 {pl}) isource dc={IB_CURRENT:g}  // {pu} source')
            infos.append(f'{pu}={d}{mark}')
        elif base == 'IIN':
            d = determine_ib_direction(scs_file, p) or 'in'
            if d == 'out':
                lines.append(f'I{pl} ({pl} 0) isource dc={IIN_CURRENT:g}  // {pu} sink')
            else:
                lines.append(f'I{pl} (0 {pl}) isource dc={IIN_CURRENT:g}  // {pu} source')
            infos.append(f'{pu}={d}')
        elif base == 'IOUT':
            v = round(vdd / 2, 3)
            lines.append(f'V{pl}_cl ({pl} 0) vsource dc={v} type=dc  // {pu} clamp')
            infos.append(f'{pu}=clamp')
        elif base in ('VIN', 'VLO', 'VRF'):
            v = round(vdd / 2, 3)
            lines.append(f'V{pl} ({pl} 0) vsource dc={v} type=dc  // {pu} tie')
            infos.append(f'{pu}={v}V')
        elif base in ('VOUT', 'VIF'):
            saves.append(pl)
        else:
            saves.append(pl)
            infos.append(f'{pu}=float')
    return lines, infos, saves, None


def ib_direction_variants(scs_file, ports_list):
    """
    Return the list of direction combinations for indeterminate IB ports.
    No indeterminate IB -> [{}] (single variant).
    Otherwise return all 2^N combinations (e.g. [{'IB1':'out'}, {'IB1':'in'}]).
    """
    indet = []
    for p in ports_list:
        pu = p.upper()
        if re.match(r'^IB\d+$', pu) and determine_ib_direction(scs_file, p) is None:
            indet.append(pu)
    if not indet:
        return [{}]
    combos = itertools.product(('out', 'in'), repeat=len(indet))
    return [dict(zip(indet, c)) for c in combos]


def try_ib_variants(scs_file, ports_list, sim_dir, attempt_fn):
    """
    Driver that tries direction combinations for indeterminate IB ports in turn.
    attempt_fn(variant_dir, ib_dirs) -> result dict
      required keys: 'status' ('ok'|'sim_fail'|'parse_fail'|'bias_skip'),
                     'passed' (bool), 'score' (float, higher is better)
    Returns immediately once any variant passes.
    Otherwise returns the best result by status priority
    (ok > parse_fail > sim_fail) then by score.
    Returns: (result, n_tried)
    """
    variants = ib_direction_variants(scs_file, ports_list)
    rank = {'ok': 3, 'parse_fail': 2, 'sim_fail': 1, 'bias_skip': 0}
    best = None
    for k, ib_dirs in enumerate(variants):
        vdir = sim_dir if len(variants) == 1 else \
            sim_dir / ('ib_' + '_'.join(f'{p.lower()}{d}'
                                        for p, d in sorted(ib_dirs.items())))
        res = attempt_fn(vdir, ib_dirs)
        if res.get('passed'):
            return res, k + 1
        key = (rank.get(res.get('status'), 0), res.get('score') or 0.0)
        if best is None or key > best[0]:
            best = (key, res)
    return best[1], len(variants)


# --- Testbench boilerplate ----------------------------------------------------
def write_tb_header(f, category, subckt_file, subckt_name, ports_list):
    """Testbench preamble: title, simulator language, model include and DUT include."""
    f.write(f'// Auto-generated {category} Testbench\n')
    f.write(f'// DUT: {subckt_name}  Ports: {" ".join(ports_list)}\n')
    f.write('simulator lang=spectre\n')
    f.write('global 0\n\n')
    f.write(f'include "{GPDK045_LIB}" section=mc\n\n')
    f.write(f'include "{subckt_file.absolute()}"\n\n')


def write_sim_options(f, temp):
    """Standard simulatorOptions block at the given temperature."""
    f.write('simulatorOptions options reltol=1e-3 vabstol=1e-6 iabstol=1e-12 \\\n')
    f.write(f'    temp={temp} tnom=27 scalem=1.0 scale=1.0 gmin=1e-12 rforce=1 \\\n')
    f.write('    maxnotes=5 maxwarns=5 digits=5 cols=80 pivrel=1e-3\n\n')


def write_dut(f, ports_list, subckt_name):
    """Instantiate the DUT with its ports mapped to same-named lower-case nodes."""
    f.write(f'Xdut ({" ".join(p.lower() for p in ports_list)}) {subckt_name}\n\n')


# --- Spectre runner -----------------------------------------------------------
def run_spectre(tb_file, sim_dir, timeout=300):
    """Run Spectre on a testbench (psfascii output); returns (success, log_path)."""
    log_file = sim_dir / 'spectre.log'
    raw_dir  = sim_dir / 'raw'
    if raw_dir.exists():
        shutil.rmtree(raw_dir)

    binary = SPECTRE_BIN if Path(SPECTRE_BIN).exists() else 'spectre'
    cmd = [binary, '+aps', '+mt',
           str(tb_file.absolute()),
           '-format', 'psfascii',
           '-raw', str(raw_dir.absolute())]
    env = os.environ.copy()
    env.setdefault('LM_LICENSE_FILE', LICENSE)

    try:
        with open(log_file, 'w') as log:
            r = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT,
                               universal_newlines=True, timeout=timeout, env=env)
        return r.returncode == 0, log_file
    except subprocess.TimeoutExpired:
        return False, log_file
    except FileNotFoundError:
        raise RuntimeError(f"spectre not found: {binary}")


# --- PSF ascii parsers --------------------------------------------------------
def parse_dc_op(sim_dir, analysis='dc_op'):
    """oppoint rawfile -> (total_power_W|None, {signal: value})."""
    dc_file = sim_dir / 'raw' / f'{analysis}.dc'
    if not dc_file.exists():
        return None, {}
    pat = re.compile(rf'^"([^"]+)"\s+"[^"]*"\s+({_NUM})')
    vals, pwr = {}, None
    with open(dc_file) as f:
        for line in f:
            m = pat.match(line.strip())
            if not m:
                continue
            if m.group(1) == ':pwr':
                pwr = abs(float(m.group(2)))
            else:
                vals[m.group(1)] = float(m.group(2))
    return pwr, vals


def parse_psf_sweep(psf_file, xname, signals):
    """
    dc sweep / tran psfascii -> (x_array, {sig: array}).
    Handles both 'name value' and 'name "unit" value' formats.
    """
    if not psf_file.exists():
        return None, None
    pat = re.compile(rf'^"([^"]+)"\s+(?:"[^"]*"\s+)?({_NUM})\s*$')
    sigset = set(signals)
    xs, data = [], {s: [] for s in signals}
    with open(psf_file) as f:
        for line in f:
            m = pat.match(line.strip())
            if not m:
                continue
            name, val = m.group(1), float(m.group(2))
            if name == xname:
                xs.append(val)
            elif name in sigset and len(data[name]) < len(xs):
                data[name].append(val)
    if not xs:
        return None, None
    n = min([len(xs)] + [len(v) for v in data.values() if v])
    xs = np.array(xs[:n])
    out = {s: (np.array(v[:n]) if v else None) for s, v in data.items()}
    return xs, out


def parse_ac(sim_dir, signals, analysis='ac_analysis'):
    """AC psfascii -> (freq_array, {sig: complex array})."""
    ac_file = sim_dir / 'raw' / f'{analysis}.ac'
    if not ac_file.exists():
        return None, None
    pat_f = re.compile(rf'^"freq"\s+({_NUM})')
    pat_c = re.compile(rf'^"([^"]+)"\s+\(({_NUM})\s+({_NUM})\)')
    sigset = set(signals)
    freqs, data = [], {s: [] for s in signals}
    with open(ac_file) as f:
        for line in f:
            line = line.strip()
            mf = pat_f.match(line)
            if mf:
                freqs.append(float(mf.group(1)))
                continue
            mc = pat_c.match(line)
            if mc and mc.group(1) in sigset and len(data[mc.group(1)]) < len(freqs):
                data[mc.group(1)].append(
                    complex(float(mc.group(2)), float(mc.group(3))))
    if not freqs:
        return None, None
    n = min([len(freqs)] + [len(v) for v in data.values() if v])
    freqs = np.array(freqs[:n])
    out = {s: (np.array(v[:n]) if v else None) for s, v in data.items()}
    return freqs, out


def parse_tran(sim_dir, signals, analysis='tran1'):
    """Transient psfascii -> (t_array, {sig: array})."""
    raw = sim_dir / 'raw'
    for cand in (raw / f'{analysis}.tran.tran', raw / f'{analysis}.tran'):
        if cand.exists():
            return parse_psf_sweep(cand, 'time', signals)
    return None, None


# --- Console / CSV ------------------------------------------------------------
def fmt(v, spec='.4g'):
    """Format a measurement for console/CSV output; None becomes 'N/A'."""
    if v is None:
        return 'N/A'
    if isinstance(v, float):
        return format(v, spec)
    return str(v)


def print_header(category, subckt_dir, n_target, n_skip, out_dir, extra=None):
    """Console banner printed before a batch."""
    print('=' * 64)
    print(f' {category} batch testbench')
    print(f' Subckt dir : {subckt_dir.name}')
    print(f' Targets    : {n_target}  (port-filtered out: {n_skip})')
    print(f' Output     : {out_dir}')
    for line in (extra or []):
        print(f' {line}')
    print('=' * 64)


def print_footer(category, n_run, n_ok, n_fail, n_pass, csv_path):
    """Console summary printed after a batch."""
    print('\n' + '=' * 64)
    print(f' Category  : {category}')
    print(f' Simulated : {n_run}   SimOK: {n_ok}   SimFail: {n_fail}')
    print(f' PASS      : {n_pass}   (of {n_ok} measured)')
    print(f' CSV       : {csv_path}')
    print('=' * 64)


class SummaryCSV:
    """summary.csv rewritten incrementally after every run."""

    def __init__(self, path, fields):
        self.path = path
        self.fields = fields
        self.rows = {}
        if path.exists():
            with open(path) as f:
                for row in csv.DictReader(f):
                    try:
                        self.rows[int(row['run_id'])] = row
                    except (KeyError, ValueError):
                        pass

    def update(self, run_id, row):
        """Store one row and rewrite the CSV so partial results survive an interruption."""
        self.rows[run_id] = row
        with open(self.path, 'w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=self.fields, extrasaction='ignore')
            w.writeheader()
            for rid in sorted(self.rows):
                w.writerow(self.rows[rid])


def base_argparser(desc):
    """Argument parser with the options shared by every run_tb_<Type>.py script."""
    ap = argparse.ArgumentParser(description=desc)
    ap.add_argument('-v', '--vdd',  type=float, default=3.3)
    ap.add_argument('-t', '--temp', type=float, default=27)
    ap.add_argument('--run-ids', type=str, default=None,
                    help='process only comma-separated run IDs (e.g. 0,9,18)')
    ap.add_argument('--limit', type=int, default=None,
                    help='process only the first N targets')
    ap.add_argument('--dry-run', action='store_true',
                    help='generate testbenches only, no simulation')
    ap.add_argument('--skip-existing', action='store_true',
                    help='skip runs that already have raw/ results')
    ap.add_argument('--subckt-dir', type=str, default=None,
                    help='directory of converted SPICE_Inference_<Type>_run<id>.scs files '
                         '(default: SPICE_Inference_<Type>/ next to the script)')
    ap.add_argument('--out-dir', type=str, default=None,
                    help='where per-run simulation folders and summary.csv are written '
                         '(default: batch_results/<Type>/ next to the script)')
    return ap


def parse_run_ids(arg):
    """Parse a comma-separated run-id list ('0,9,18') into a set, or None."""
    return set(int(x) for x in arg.split(',')) if arg else None


def has_existing_results(sim_dir):
    """For --skip-existing: checks single, 2-pass and IB-variant layouts."""
    if (sim_dir / 'raw').exists():
        return True
    for sub in ('fine', 'slow'):
        if (sim_dir / sub / 'raw').exists():
            return True
    return (any(sim_dir.glob('ib_*/raw')) or
            any(sim_dir.glob('ib_*/*/raw')))
