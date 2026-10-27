#!/usr/bin/env python3
"""
run_tb_opamp - OpAmp batch testbench (SPICE_Inference_Opamp)

Target : subckts containing VDD VSS VIN1 VIN2 VOUT1
Method : open-loop AC (VIN1 = DC VDD/2 + AC mag=1, VIN2 = DC VDD/2, CL=100pF)
Measure: DC gain, -3dB BW, GBW, DC power
PASS   : DC gain >= 20 dB
Output : batch_results/Opamp/run<id>/ + summary.csv
"""

from pathlib import Path

import numpy as np

import tb_common as tc
from tb_common import BASE_DIR, IND, fmt

CATEGORY   = 'Opamp'
SUBCKT_DIR = BASE_DIR / 'SPICE_Inference_Opamp'
OUT_DIR    = BASE_DIR / 'batch_results' / CATEGORY
REQUIRED   = {'VDD', 'VSS', 'VIN1', 'VIN2', 'VOUT1'}
PASS_GAIN_DB = 20.0

CSV_FIELDS = ['run_id', 'subckt_name', 'ports', 'bias_info', 'status', 'pass',
              'dc_gain_dB', 'bw_Hz', 'gbw_MHz', 'vout1_dc_V', 'dc_power_mW',
              'vin1_polarity']


def create_testbench(scs_file, subckt_name, ports_list, sim_dir, args,
                     ib_dirs=None):
    """Write the Spectre testbench for one DUT; returns (tb_path, bias_info, skip_reason)."""
    sim_dir.mkdir(parents=True, exist_ok=True)
    tb = sim_dir / 'testbench.scs'
    vdd = args.vdd
    vmid = round(vdd / 2, 3)

    handled = {'VDD', 'VSS', 'VIN1', 'VIN2', 'VOUT1'}
    misc_lines, infos, misc_saves, skip = tc.classify_misc_ports(
        scs_file, ports_list, handled, vdd, ib_dirs=ib_dirs)
    if skip:
        return None, None, skip

    with open(tb, 'w') as f:
        tc.write_tb_header(f, CATEGORY, scs_file, subckt_name, ports_list)
        f.write('// -- Power -------------------------------------------\n')
        f.write(f'Vvdd (vdd 0) vsource dc={vdd} type=dc\n')
        f.write('Vvss (vss 0) vsource dc=0 type=dc\n\n')
        f.write('// -- Inputs ------------------------------------------\n')
        f.write(f'Vvin1 (vin1 0) vsource type=dc dc={vmid} mag=1\n')
        f.write(f'Vvin2 (vin2 0) vsource type=dc dc={vmid}\n')
        for line in misc_lines:
            f.write(line + '\n')
        f.write('\n')
        tc.write_dut(f, ports_list, subckt_name)
        f.write(f'CL (vout1 0) capacitor c={args.cl * 1e-12:.3e}  // load capacitor\n\n')
        tc.write_sim_options(f, args.temp)
        saves = ['vout1'] + misc_saves
        f.write(f'save {" ".join(saves)}\n')
        f.write('saveOptions options save=selected pwr=total\n\n')
        f.write('dc_op dc oppoint=rawfile\n\n')
        f.write(f'ac_analysis ac start=1 stop={args.ac_stop:.3e} '
                f'dec={args.ac_dec} annotate=status\n')
    return tb, ' '.join(infos), None


def measure(sim_dir):
    """Extract the category metrics from the simulation results, or None on parse failure."""
    freqs, data = tc.parse_ac(sim_dir, ['vout1'])
    if freqs is None or data.get('vout1') is None or len(freqs) < 2:
        return None
    h = data['vout1']
    mags = np.abs(h)
    vin1_is_inv = h[0].real < 0

    pwr, dc_vals = tc.parse_dc_op(sim_dir)
    pwr_mw = pwr * 1e3 if pwr is not None else None
    vout1_dc = dc_vals.get('vout1')

    dc_gain_lin = mags[0]
    dc_gain_db = 20 * np.log10(dc_gain_lin) if dc_gain_lin > 0 else float('-inf')

    thr = dc_gain_lin / np.sqrt(2)
    bw = freqs[-1]
    for i in range(1, len(mags)):
        if mags[i] <= thr:
            f1, m1, f2, m2 = freqs[i-1], mags[i-1], freqs[i], mags[i]
            t = (thr - m1) / (m2 - m1) if m2 != m1 else 0
            bw = float(np.exp(np.log(f1) + t * (np.log(f2) - np.log(f1))))
            break

    gbw = None
    if dc_gain_lin > 1.0:
        for i in range(1, len(mags)):
            if mags[i] <= 1.0:
                f1, m1, f2, m2 = freqs[i-1], mags[i-1], freqs[i], mags[i]
                t = (1.0 - m1) / (m2 - m1) if m2 != m1 else 0
                gbw = float(np.exp(np.log(f1) + t * (np.log(f2) - np.log(f1))))
                break
    if gbw is None:
        gbw = float(dc_gain_lin * bw)

    return {
        'dc_gain_dB':    float(dc_gain_db),
        'bw_Hz':         float(bw),
        'gbw_MHz':       gbw / 1e6,
        'vout1_dc_V':    vout1_dc,
        'dc_power_mW':   pwr_mw,
        'vin1_polarity': 'inv' if vin1_is_inv else 'non-inv',
    }


def main():
    """Command-line entry point: select DUTs, simulate each, record summary.csv."""
    ap = tc.base_argparser('OpAmp batch testbench (open-loop AC, GPDK045)')
    ap.add_argument('--cl', type=float, default=100.0, help='load capacitance in pF')
    ap.add_argument('--ac-stop', type=float, default=10e9)
    ap.add_argument('--ac-dec', type=int, default=50)
    args = ap.parse_args()
    subckt_dir = Path(args.subckt_dir) if args.subckt_dir else SUBCKT_DIR
    out_dir = Path(args.out_dir) if args.out_dir else OUT_DIR

    out_dir.mkdir(parents=True, exist_ok=True)
    run_ids = tc.parse_run_ids(args.run_ids)
    targets, n_skip = tc.collect_targets(subckt_dir, REQUIRED, run_ids, args.limit)
    tc.print_header(CATEGORY, subckt_dir, len(targets), n_skip, out_dir,
                    extra=[f'PASS criterion : DC gain >= {PASS_GAIN_DB} dB '
                           f'(CL={args.cl} pF, VDD={args.vdd} V)',
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
            m = measure(vdir)
            if m is None:
                return {'status': 'parse_fail', 'passed': False, 'score': 0,
                        'bias_info': bias_info}
            passed = m['dc_gain_dB'] >= PASS_GAIN_DB
            return {'status': 'ok', 'passed': passed,
                    'score': m['dc_gain_dB'], 'bias_info': bias_info,
                    'metrics': m}

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
        print(f'{IND}-> OK  [{tag}]  gain={fmt(m["dc_gain_dB"], ".1f")}dB '
              f'({m["vin1_polarity"]})  BW={fmt(m["bw_Hz"], ".3g")}Hz  '
              f'GBW={fmt(m["gbw_MHz"], ".3g")}MHz  '
              f'Vout={fmt(m["vout1_dc_V"], ".3f")}V  '
              f'Pwr={fmt(m["dc_power_mW"], ".3g")}mW')
        summary.update(rid, {**base, 'status': 'ok', 'pass': int(passed),
                             **{k: fmt(v) for k, v in m.items()}})

    tc.print_footer(CATEGORY, n_run, n_ok, n_fail, n_pass, summary.path)


if __name__ == '__main__':
    main()
