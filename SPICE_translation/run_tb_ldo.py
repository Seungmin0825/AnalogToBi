#!/usr/bin/env python3
"""
run_tb_ldo - LDO batch testbench (SPICE_Inference_LDO)

Target : subckts containing VSS VOUT1 VREF1 + (VIN1 or VDD)
Method : (1) Line - DC sweep of the input (VIN1, else VDD) 2.8 -> 3.3 V (no load)
         (2) Load - VOUT1 load current {0, 1u, 10u} A (input at 3.3 V)
Measure: nominal VOUT1, line/load variation (%), DC power
PASS   : line variation < 10% AND load variation < 10% AND nominal VOUT1 >= 0.5 V
Output : batch_results/LDO/run<id>/ + summary.csv
"""

from pathlib import Path

import numpy as np

import tb_common as tc
from tb_common import BASE_DIR, IND, fmt

CATEGORY   = 'LDO'
SUBCKT_DIR = BASE_DIR / 'SPICE_Inference_LDO'
OUT_DIR    = BASE_DIR / 'batch_results' / CATEGORY
REQUIRED   = {'VSS', 'VOUT1', 'VREF1'}
VAR_LIMIT_PCT = 10.0
VOUT_MIN_V    = 0.5
LOAD_VALUES   = [0.0, 1e-6, 10e-6]

CSV_FIELDS = ['run_id', 'subckt_name', 'ports', 'bias_info', 'status', 'pass',
              'vout_nom_V', 'line_var_pct', 'load_var_pct', 'dc_power_mW',
              'line_input']


def _extra_filter(scs_file, name, ports):
    """Per-category port condition applied on top of the required-port set."""
    pset = set(p.upper() for p in ports)
    return 'VIN1' in pset or 'VDD' in pset


def create_testbench(scs_file, subckt_name, ports_list, sim_dir, args,
                     ib_dirs=None):
    """Write the Spectre testbench for one DUT; returns (tb_path, bias_info, skip_reason)."""
    sim_dir.mkdir(parents=True, exist_ok=True)
    tb = sim_dir / 'testbench.scs'
    vdd = args.vdd
    pset = set(p.upper() for p in ports_list)

    # Line-sweep input: prefer VIN1, else sweep VDD itself
    line_input = 'VIN1' if 'VIN1' in pset else 'VDD'

    handled = {'VSS', 'VOUT1', 'VREF1'}
    handled |= {'VIN1', 'VDD'} & pset
    misc_lines, infos, misc_saves, skip = tc.classify_misc_ports(
        scs_file, ports_list, handled, vdd, ib_dirs=ib_dirs)
    if skip:
        return None, None, None, skip

    with open(tb, 'w') as f:
        tc.write_tb_header(f, CATEGORY, scs_file, subckt_name, ports_list)
        f.write(f'parameters vin_val={vdd} iload_val=0\n\n')
        f.write('// -- Power / Inputs ----------------------------------\n')
        f.write('Vvss (vss 0) vsource dc=0 type=dc\n')
        if 'VDD' in pset:
            if line_input == 'VDD':
                f.write('Vvdd (vdd 0) vsource dc=vin_val type=dc  // swept supply\n')
            else:
                f.write(f'Vvdd (vdd 0) vsource dc={vdd} type=dc\n')
        if 'VIN1' in pset:
            f.write('Vvin1 (vin1 0) vsource dc=vin_val type=dc  // swept input\n')
        f.write(f'Vvref1 (vref1 0) vsource dc={args.vref} type=dc\n')
        for line in misc_lines:
            f.write(line + '\n')
        f.write('\n// -- Load --------------------------------------------\n')
        f.write('IL (vout1 0) isource dc=iload_val type=dc  // load sink\n\n')
        tc.write_dut(f, ports_list, subckt_name)
        tc.write_sim_options(f, args.temp)
        saves = ['vout1'] + misc_saves
        f.write(f'save {" ".join(saves)}\n')
        f.write('saveOptions options save=selected pwr=total\n\n')
        f.write('dc_op dc oppoint=rawfile\n\n')
        f.write(f'linereg dc param=vin_val start={args.line_start} '
                f'stop={args.line_stop} step={args.line_step} annotate=status\n\n')
        loads = ' '.join(f'{v:g}' for v in LOAD_VALUES)
        f.write(f'loadreg dc param=iload_val values=[{loads}] annotate=status\n')
    return tb, ' '.join(infos), line_input, None


def measure(sim_dir):
    """Extract the category metrics from the simulation results, or None on parse failure."""
    pwr, dc_vals = tc.parse_dc_op(sim_dir)
    pwr_mw = pwr * 1e3 if pwr is not None else None
    vout_nom = dc_vals.get('vout1')

    x1, d1 = tc.parse_psf_sweep(sim_dir / 'raw' / 'linereg.dc',
                                'vin_val', ['vout1'])
    x2, d2 = tc.parse_psf_sweep(sim_dir / 'raw' / 'loadreg.dc',
                                'iload_val', ['vout1'])
    if (x1 is None or d1.get('vout1') is None or
            x2 is None or d2.get('vout1') is None or vout_nom is None):
        return None

    ref = abs(vout_nom) if abs(vout_nom) > 1e-9 else 1e-9
    line_var = float(np.max(d1['vout1']) - np.min(d1['vout1'])) / ref * 100
    load_var = float(np.max(d2['vout1']) - np.min(d2['vout1'])) / ref * 100

    return {
        'vout_nom_V':   float(vout_nom),
        'line_var_pct': line_var,
        'load_var_pct': load_var,
        'dc_power_mW':  pwr_mw,
    }


def main():
    """Command-line entry point: select DUTs, simulate each, record summary.csv."""
    ap = tc.base_argparser('LDO batch testbench (line/load regulation, GPDK045)')
    ap.add_argument('--vref', type=float, default=1.6)
    ap.add_argument('--line-start', type=float, default=2.8)
    ap.add_argument('--line-stop',  type=float, default=3.3)
    ap.add_argument('--line-step',  type=float, default=0.05)
    args = ap.parse_args()
    subckt_dir = Path(args.subckt_dir) if args.subckt_dir else SUBCKT_DIR
    out_dir = Path(args.out_dir) if args.out_dir else OUT_DIR

    out_dir.mkdir(parents=True, exist_ok=True)
    run_ids = tc.parse_run_ids(args.run_ids)
    targets, n_skip = tc.collect_targets(subckt_dir, REQUIRED, run_ids,
                                         args.limit, extra_filter=_extra_filter)
    tc.print_header(CATEGORY, subckt_dir, len(targets), n_skip, out_dir,
                    extra=[f'PASS criterion : line/load variation < {VAR_LIMIT_PCT}%, '
                           f'VOUT >= {VOUT_MIN_V} V '
                           f'(line {args.line_start}-{args.line_stop} V, '
                           f'load {"/".join(f"{v*1e6:g}u" for v in LOAD_VALUES)}A)',
                           'Indeterminate IB: all direction combinations '
                           'are attempted; PASS if any passes'])

    summary = tc.SummaryCSV(out_dir / 'summary.csv', CSV_FIELDS)
    n_ok = n_fail = n_pass = n_run = 0

    for i, (scs_file, name, ports) in enumerate(targets):
        rid = tc.run_id_of(scs_file)
        sim_dir = out_dir / f'run{rid}'
        if args.skip_existing and tc.has_existing_results(sim_dir):
            continue

        def attempt(vdir, ib_dirs):
            """Build, simulate and measure one testbench variant."""
            tb, bias_info, line_input, skip = create_testbench(
                scs_file, name, ports, vdir, args, ib_dirs=ib_dirs)
            if skip:
                return {'status': 'bias_skip', 'passed': False, 'score': 0,
                        'skip': skip}
            if args.dry_run:
                return {'status': 'dry-run', 'passed': False, 'score': 0,
                        'bias_info': bias_info, 'tb': tb,
                        'line_input': line_input}
            ok, log = tc.run_spectre(tb, vdir)
            if not ok:
                return {'status': 'sim_fail', 'passed': False, 'score': 0,
                        'bias_info': bias_info, 'log': log,
                        'line_input': line_input}
            m = measure(vdir)
            if m is None:
                return {'status': 'parse_fail', 'passed': False, 'score': 0,
                        'bias_info': bias_info, 'line_input': line_input}
            passed = (m['line_var_pct'] < VAR_LIMIT_PCT and
                      m['load_var_pct'] < VAR_LIMIT_PCT and
                      m['vout_nom_V'] >= VOUT_MIN_V)
            # Lower variation indicates better regulation;
            # score is the negative sum of line/load variation.
            score = -(m['line_var_pct'] + m['load_var_pct'])
            return {'status': 'ok', 'passed': passed, 'score': score,
                    'bias_info': bias_info, 'metrics': m,
                    'line_input': line_input}

        res, n_tried = tc.try_ib_variants(scs_file, ports, sim_dir, attempt)
        tried_str = f'  [{n_tried} variant(s)]' if n_tried > 1 else ''
        line_input = res.get('line_input', '')
        print(f'[{i+1:4d}/{len(targets)}] run{rid:<5} '
              f'line_in={line_input or "-"}  '
              f'{res.get("bias_info") or res.get("skip") or ""}{tried_str}')
        base = {'run_id': rid, 'subckt_name': name, 'ports': ' '.join(ports),
                'bias_info': res.get('bias_info', ''),
                'line_input': line_input or ''}

        status = res['status']
        if status == 'bias_skip':
            print(f'{IND}-> SKIP  ({res.get("skip")})')
            summary.update(rid, {**base, 'status': 'bias_skip', 'pass': ''})
            continue
        if status == 'dry-run':
            print(f'{IND}-> DRY   {res.get("tb")}')
            summary.update(rid, {**base, 'status': 'dry-run', 'pass': ''})
            continue

        n_run += 1
        if status == 'sim_fail':
            n_fail += 1
            print(f'{IND}-> SIMFAIL  (log: {res.get("log")})')
            summary.update(rid, {**base, 'status': 'sim_fail', 'pass': ''})
            continue
        if status == 'parse_fail':
            n_fail += 1
            print(f'{IND}-> PARSEFAIL')
            summary.update(rid, {**base, 'status': 'parse_fail', 'pass': ''})
            continue

        n_ok += 1
        m = res['metrics']
        passed = res['passed']
        n_pass += passed
        tag = 'PASS' if passed else 'FAIL'
        print(f'{IND}-> OK  [{tag}]  Vout={fmt(m["vout_nom_V"], ".3f")}V  '
              f'line={fmt(m["line_var_pct"], ".2f")}%  '
              f'load={fmt(m["load_var_pct"], ".2f")}%  '
              f'Pwr={fmt(m["dc_power_mW"], ".3g")}mW')
        summary.update(rid, {**base, 'status': 'ok', 'pass': int(passed),
                             **{k: fmt(v) for k, v in m.items()}})

    tc.print_footer(CATEGORY, n_run, n_ok, n_fail, n_pass, summary.path)


if __name__ == '__main__':
    main()
