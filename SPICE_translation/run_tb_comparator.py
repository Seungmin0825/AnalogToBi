#!/usr/bin/env python3
"""
run_tb_comparator - Comparator batch testbench (SPICE_Inference_Comparator)

Target : subckts containing VDD VSS VIN1 VOUT1 (VIN2, if present, fixed at VDD/2)
Method : VIN1 DC sweep 0 -> VDD (VCONT* driven logic-high = VDD)
Measure: VOUT1 swing (max-min), threshold voltage (VDD/2 crossing),
         polarity, DC power
PASS   : swing >= 50% of VDD
Output : batch_results/Comparator/run<id>/ + summary.csv
"""

from pathlib import Path

import numpy as np

import tb_common as tc
from tb_common import BASE_DIR, IND, fmt

CATEGORY   = 'Comparator'
SUBCKT_DIR = BASE_DIR / 'SPICE_Inference_Comparator'
OUT_DIR    = BASE_DIR / 'batch_results' / CATEGORY
REQUIRED   = {'VDD', 'VSS', 'VIN1', 'VOUT1'}
SWING_FRAC = 0.5   # PASS: swing >= VDD * 0.5

CSV_FIELDS = ['run_id', 'subckt_name', 'ports', 'bias_info', 'status', 'pass',
              'swing_V', 'vth_V', 'polarity', 'vout_lo_V', 'vout_hi_V',
              'dc_power_mW']


def create_testbench(scs_file, subckt_name, ports_list, sim_dir, args,
                     ib_dirs=None):
    """Write the Spectre testbench for one DUT; returns (tb_path, bias_info, skip_reason)."""
    sim_dir.mkdir(parents=True, exist_ok=True)
    tb = sim_dir / 'testbench.scs'
    vdd = args.vdd
    vmid = round(vdd / 2, 3)
    pset = set(p.upper() for p in ports_list)

    handled = {'VDD', 'VSS', 'VIN1', 'VOUT1'}
    if 'VIN2' in pset:
        handled.add('VIN2')
    misc_lines, infos, misc_saves, skip = tc.classify_misc_ports(
        scs_file, ports_list, handled, vdd, vcont_v=args.vcont, ib_dirs=ib_dirs)
    if skip:
        return None, None, skip

    with open(tb, 'w') as f:
        tc.write_tb_header(f, CATEGORY, scs_file, subckt_name, ports_list)
        f.write('parameters vin1_val=%s\n\n' % vmid)
        f.write('// -- Power -------------------------------------------\n')
        f.write(f'Vvdd (vdd 0) vsource dc={vdd} type=dc\n')
        f.write('Vvss (vss 0) vsource dc=0 type=dc\n\n')
        f.write('// -- Inputs ------------------------------------------\n')
        f.write('Vvin1 (vin1 0) vsource dc=vin1_val type=dc\n')
        if 'VIN2' in pset:
            f.write(f'Vvin2 (vin2 0) vsource dc={vmid} type=dc  // reference\n')
        for line in misc_lines:
            f.write(line + '\n')
        f.write('\n')
        tc.write_dut(f, ports_list, subckt_name)
        tc.write_sim_options(f, args.temp)
        saves = ['vout1'] + misc_saves
        f.write(f'save {" ".join(saves)}\n')
        f.write('saveOptions options save=selected pwr=total\n\n')
        f.write('dc_op dc oppoint=rawfile\n\n')
        f.write(f'vsweep dc param=vin1_val start=0 stop={vdd} '
                f'step={args.step} annotate=status\n')
    return tb, ' '.join(infos), None


def measure(sim_dir, vdd):
    """Extract the category metrics from the simulation results, or None on parse failure."""
    x, data = tc.parse_psf_sweep(sim_dir / 'raw' / 'vsweep.dc',
                                 'vin1_val', ['vout1'])
    if x is None or data.get('vout1') is None or len(x) < 3:
        return None
    v = data['vout1']

    pwr, _ = tc.parse_dc_op(sim_dir)
    pwr_mw = pwr * 1e3 if pwr is not None else None

    vlo, vhi = float(np.min(v)), float(np.max(v))
    swing = vhi - vlo

    # VDD/2 crossing (threshold) - linear interpolation at first crossing
    vth = None
    polarity = 'flat'
    mid = vdd / 2
    d = v - mid
    for i in range(1, len(v)):
        if d[i-1] == 0 or (d[i-1] < 0) != (d[i] < 0):
            t = abs(d[i-1]) / (abs(d[i-1]) + abs(d[i])) if d[i] != d[i-1] else 0
            vth = float(x[i-1] + t * (x[i] - x[i-1]))
            polarity = 'rising' if v[i] > v[i-1] else 'falling'
            break

    return {
        'swing_V':     swing,
        'vth_V':       vth,
        'polarity':    polarity,
        'vout_lo_V':   vlo,
        'vout_hi_V':   vhi,
        'dc_power_mW': pwr_mw,
    }


def main():
    """Command-line entry point: select DUTs, simulate each, record summary.csv."""
    ap = tc.base_argparser('Comparator batch testbench (VIN1 DC sweep, GPDK045)')
    ap.add_argument('--step', type=float, default=0.05, help='VIN1 sweep step in V')
    ap.add_argument('--vcont', type=float, default=None,
                    help='VCONT* DC voltage (default: VDD = logic high)')
    args = ap.parse_args()
    subckt_dir = Path(args.subckt_dir) if args.subckt_dir else SUBCKT_DIR
    out_dir = Path(args.out_dir) if args.out_dir else OUT_DIR
    if args.vcont is None:
        args.vcont = args.vdd

    out_dir.mkdir(parents=True, exist_ok=True)
    run_ids = tc.parse_run_ids(args.run_ids)
    targets, n_skip = tc.collect_targets(subckt_dir, REQUIRED, run_ids, args.limit)
    tc.print_header(CATEGORY, subckt_dir, len(targets), n_skip, out_dir,
                    extra=[f'PASS criterion : VOUT1 swing >= VDD*{SWING_FRAC} '
                           f'(VDD={args.vdd} V, VCONT={args.vcont} V)',
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
            tb, bias_info, skip = create_testbench(
                scs_file, name, ports, vdir, args, ib_dirs=ib_dirs)
            if skip:
                return {'status': 'bias_skip', 'passed': False, 'score': 0,
                        'skip': skip}
            if args.dry_run:
                return {'status': 'dry-run', 'passed': False, 'score': 0,
                        'bias_info': bias_info, 'tb': tb}
            ok, log = tc.run_spectre(tb, vdir)
            if not ok:
                return {'status': 'sim_fail', 'passed': False, 'score': 0,
                        'bias_info': bias_info, 'log': log}
            m = measure(vdir, args.vdd)
            if m is None:
                return {'status': 'parse_fail', 'passed': False, 'score': 0,
                        'bias_info': bias_info}
            passed = m['swing_V'] >= args.vdd * SWING_FRAC
            return {'status': 'ok', 'passed': passed, 'score': m['swing_V'],
                    'bias_info': bias_info, 'metrics': m}

        res, n_tried = tc.try_ib_variants(scs_file, ports, sim_dir, attempt)
        tried_str = f'  [{n_tried} variant(s)]' if n_tried > 1 else ''
        print(f'[{i+1:4d}/{len(targets)}] run{rid:<5} '
              f'{res.get("bias_info") or res.get("skip") or ""}{tried_str}')
        base = {'run_id': rid, 'subckt_name': name, 'ports': ' '.join(ports),
                'bias_info': res.get('bias_info', '')}

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
        print(f'{IND}-> OK  [{tag}]  swing={fmt(m["swing_V"], ".3f")}V  '
              f'vth={fmt(m["vth_V"], ".3f")}V ({m["polarity"]})  '
              f'lo/hi={fmt(m["vout_lo_V"], ".2f")}/{fmt(m["vout_hi_V"], ".2f")}V  '
              f'Pwr={fmt(m["dc_power_mW"], ".3g")}mW')
        summary.update(rid, {**base, 'status': 'ok', 'pass': int(passed),
                             **{k: fmt(v) for k, v in m.items()}})

    tc.print_footer(CATEGORY, n_run, n_ok, n_fail, n_pass, summary.path)


if __name__ == '__main__':
    main()
