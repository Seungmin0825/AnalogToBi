#!/usr/bin/env python3
"""
run_tb_filter - Filter batch testbench (SPICE_Inference_Filter)

Target : subckts containing VIN1 VSS + (VOUT1 or IOUT1) (VDD applied if present)
Method : AC 1 Hz -> 10 GHz (VIN1 = DC VDD/2 + AC mag=1, VIN2 = DC)
         Measures voltage output (VOUT1) or current output
         (IOUT* -> current through a VDD/2 clamp voltage source).
         With both IOUT1/IOUT2 present, uses differential current (I1-I2).
Measure: peak response |H|max and its frequency, selectivity = peak-to-edge
         (min) ratio [dB], shape (LP/HP/BP)
PASS   : selectivity >= 20 dB AND peak >= floor (-40 dBV / -120 dBS,
         to reject numerical noise)
Output : batch_results/Filter/run<id>/ + summary.csv
"""

from pathlib import Path

import numpy as np

import tb_common as tc
from tb_common import BASE_DIR, IND, fmt

CATEGORY   = 'Filter'
SUBCKT_DIR = BASE_DIR / 'SPICE_Inference_Filter'
OUT_DIR    = BASE_DIR / 'batch_results' / CATEGORY
REQUIRED   = {'VIN1', 'VSS'}
SEL_PASS_DB = 20.0
PEAK_MIN_DB = {'voltage': -40.0, 'current': -120.0}   # floor to reject numerical noise

CSV_FIELDS = ['run_id', 'subckt_name', 'ports', 'bias_info', 'status', 'pass',
              'out_kind', 'sel_dB', 'peak_dB', 'f_peak_Hz', 'shape',
              'dc_power_mW']


def _extra_filter(scs_file, name, ports):
    """Per-category port condition applied on top of the required-port set."""
    pset = set(p.upper() for p in ports)
    return 'VOUT1' in pset or 'IOUT1' in pset


def create_testbench(scs_file, subckt_name, ports_list, sim_dir, args,
                     ib_dirs=None):
    """Write the Spectre testbench for one DUT; returns (tb_path, bias_info, skip_reason)."""
    sim_dir.mkdir(parents=True, exist_ok=True)
    tb = sim_dir / 'testbench.scs'
    vdd = args.vdd
    vmid = round(vdd / 2, 3)
    pset = set(p.upper() for p in ports_list)

    # Output: prefer VOUT1 (voltage), else IOUT* (clamped current)
    if 'VOUT1' in pset:
        out_kind = 'voltage'
        iouts = []
    else:
        out_kind = 'current'
        iouts = sorted((p for p in pset if p.startswith('IOUT')),
                       key=lambda s: int(s[4:]))[:2]     # IOUT1 (+IOUT2)

    handled = {'VIN1', 'VSS'}
    handled |= {'VDD', 'VIN2', 'VOUT1'} & pset
    handled |= set(iouts)
    misc_lines, infos, misc_saves, skip = tc.classify_misc_ports(
        scs_file, ports_list, handled, vdd, ib_dirs=ib_dirs)
    if skip:
        return None, None, None, skip

    with open(tb, 'w') as f:
        tc.write_tb_header(f, CATEGORY, scs_file, subckt_name, ports_list)
        f.write('// -- Power / Inputs ----------------------------------\n')
        f.write('Vvss (vss 0) vsource dc=0 type=dc\n')
        if 'VDD' in pset:
            f.write(f'Vvdd (vdd 0) vsource dc={vdd} type=dc\n')
        f.write(f'Vvin1 (vin1 0) vsource type=dc dc={vmid} mag=1\n')
        if 'VIN2' in pset:
            f.write(f'Vvin2 (vin2 0) vsource dc={vmid} type=dc\n')
        for line in misc_lines:
            f.write(line + '\n')

        save_sigs = []
        if out_kind == 'voltage':
            save_sigs.append('vout1')
        else:
            f.write('\n// -- Output current clamps -----------------------\n')
            for io in iouts:
                io_l = io.lower()
                f.write(f'Vcl{io_l} ({io_l} 0) vsource dc={vmid} type=dc  '
                        f'// {io} clamp\n')
                save_sigs.append(f'Vcl{io_l}:p')
        f.write('\n')
        tc.write_dut(f, ports_list, subckt_name)
        tc.write_sim_options(f, args.temp)
        f.write(f'save {" ".join(save_sigs + misc_saves)}\n')
        f.write('saveOptions options save=selected pwr=total\n\n')
        f.write('dc_op dc oppoint=rawfile\n\n')
        f.write(f'ac_analysis ac start=1 stop={args.ac_stop:.3e} '
                f'dec={args.ac_dec} annotate=status\n')
    return tb, ' '.join(infos), (out_kind, save_sigs), None


def measure(sim_dir, out_kind, save_sigs):
    """Extract the category metrics from the simulation results, or None on parse failure."""
    freqs, data = tc.parse_ac(sim_dir, save_sigs)
    if freqs is None or len(freqs) < 3:
        return None

    if out_kind == 'voltage':
        h = data.get(save_sigs[0])
        if h is None:
            return None
    else:
        h1 = data.get(save_sigs[0])
        if h1 is None:
            return None
        h2 = data.get(save_sigs[1]) if len(save_sigs) > 1 else None
        h = (h1 - h2) if h2 is not None else h1   # differential current

    mag = np.maximum(np.abs(h), 1e-30)
    imax = int(np.argmax(mag))
    peak = float(mag[imax])
    edge_min = float(min(mag[0], mag[-1]))
    sel_db = 20 * np.log10(peak / max(edge_min, 1e-30))
    peak_db = 20 * np.log10(peak)

    # Shape classification: based on which edges stay within 3dB of the peak
    lo_close = mag[0]  >= peak / np.sqrt(2)
    hi_close = mag[-1] >= peak / np.sqrt(2)
    if lo_close and not hi_close:
        shape = 'LP'
    elif hi_close and not lo_close:
        shape = 'HP'
    elif not lo_close and not hi_close:
        shape = 'BP'
    else:
        shape = 'flat'

    pwr, _ = tc.parse_dc_op(sim_dir)
    return {
        'sel_dB':      float(sel_db),
        'peak_dB':     float(peak_db),
        'f_peak_Hz':   float(freqs[imax]),
        'shape':       shape,
        'dc_power_mW': pwr * 1e3 if pwr is not None else None,
    }


def main():
    """Command-line entry point: select DUTs, simulate each, record summary.csv."""
    ap = tc.base_argparser('Filter batch testbench (AC selectivity, GPDK045)')
    ap.add_argument('--ac-stop', type=float, default=10e9)
    ap.add_argument('--ac-dec', type=int, default=20)
    args = ap.parse_args()
    subckt_dir = Path(args.subckt_dir) if args.subckt_dir else SUBCKT_DIR
    out_dir = Path(args.out_dir) if args.out_dir else OUT_DIR

    out_dir.mkdir(parents=True, exist_ok=True)
    run_ids = tc.parse_run_ids(args.run_ids)
    targets, n_skip = tc.collect_targets(subckt_dir, REQUIRED, run_ids,
                                         args.limit, extra_filter=_extra_filter)
    tc.print_header(CATEGORY, subckt_dir, len(targets), n_skip, out_dir,
                    extra=[f'PASS criterion : selectivity (peak/edges) >= {SEL_PASS_DB} dB '
                           f'(AC 1Hz-{args.ac_stop:.0e}Hz, VDD={args.vdd} V)',
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
            tb, bias_info, outdesc, skip = create_testbench(
                scs_file, name, ports, vdir, args, ib_dirs=ib_dirs)
            if skip:
                return {'status': 'bias_skip', 'passed': False, 'score': 0,
                        'skip': skip}
            if args.dry_run:
                return {'status': 'dry-run', 'passed': False, 'score': 0,
                        'bias_info': bias_info, 'tb': tb, 'outdesc': outdesc}
            ok, log = tc.run_spectre(tb, vdir)
            if not ok:
                return {'status': 'sim_fail', 'passed': False, 'score': 0,
                        'bias_info': bias_info, 'log': log, 'outdesc': outdesc}
            m = measure(vdir, *outdesc)
            if m is None:
                return {'status': 'parse_fail', 'passed': False, 'score': 0,
                        'bias_info': bias_info, 'outdesc': outdesc}
            passed = (m['sel_dB'] >= SEL_PASS_DB and
                      m['peak_dB'] >= PEAK_MIN_DB[outdesc[0]])
            return {'status': 'ok', 'passed': passed, 'score': m['sel_dB'],
                    'bias_info': bias_info, 'metrics': m, 'outdesc': outdesc}

        res, n_tried = tc.try_ib_variants(scs_file, ports, sim_dir, attempt)
        tried_str = f'  [{n_tried} variant(s)]' if n_tried > 1 else ''
        outdesc = res.get('outdesc')
        out_kind = outdesc[0] if outdesc else ''
        print(f'[{i+1:4d}/{len(targets)}] run{rid:<5} out={out_kind or "-"}  '
              f'{res.get("bias_info") or res.get("skip") or ""}{tried_str}')
        base = {'run_id': rid, 'subckt_name': name, 'ports': ' '.join(ports),
                'bias_info': res.get('bias_info', ''), 'out_kind': out_kind}

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
        unit = 'dBV' if out_kind == 'voltage' else 'dBS'
        print(f'{IND}-> OK  [{tag}]  sel={fmt(m["sel_dB"], ".1f")}dB  '
              f'peak={fmt(m["peak_dB"], ".1f")}{unit}'
              f'@{fmt(m["f_peak_Hz"], ".3g")}Hz  shape={m["shape"]}  '
              f'Pwr={fmt(m["dc_power_mW"], ".3g")}mW')
        summary.update(rid, {**base, 'status': 'ok', 'pass': int(passed),
                             **{k: fmt(v) for k, v in m.items()}})

    tc.print_footer(CATEGORY, n_run, n_ok, n_fail, n_pass, summary.path)


if __name__ == '__main__':
    main()
