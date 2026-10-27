#!/usr/bin/env python3
"""
run_tb_oscillator - Oscillator batch testbench (SPICE_Inference_Oscillator)

Target : subckts containing VDD VSS VOUT1 (circuits without output ports are skipped)
Method : 2-pass transient (ic vout1=0 startup stimulus, VCONT*=VDD/2)
         [fine] 400 ns, maxstep=10 ps - captures GHz LC/ring oscillation
                (observable >= ~20 MHz)
         [slow] only if fine shows no oscillation: 2 us, maxstep=2 ns -
                slow oscillation (>= ~4 MHz)
         Judged on the best VOUT<n> node: periodic ones first, then largest amplitude.
         Indeterminate IB: all direction combinations (out/in) are
         attempted; PASS if any passes.
Measure: Vpp, oscillation frequency (rising-crossing based),
         period consistency (std/mean), DC power
PASS   : Vpp >= 10% of VDD AND periodic (>= 4 crossings, period deviation < 25%)
Output : batch_results/Oscillator/run<id>/(fine|slow)/ + summary.csv
"""

from pathlib import Path

import numpy as np

import tb_common as tc
from tb_common import BASE_DIR, IND, fmt

CATEGORY   = 'Oscillator'
SUBCKT_DIR = BASE_DIR / 'SPICE_Inference_Oscillator'
OUT_DIR    = BASE_DIR / 'batch_results' / CATEGORY
REQUIRED   = {'VDD', 'VSS', 'VOUT1'}

#          (stage, tstop, maxstep)
PASSES = [('fine', 400e-9, 10e-12),
          ('slow', 2e-6,   2e-9)]
VPP_FRAC   = 0.10   # PASS: Vpp >= VDD * 0.10
PERIOD_TOL = 0.25   # allowed period std/mean

CSV_FIELDS = ['run_id', 'subckt_name', 'ports', 'bias_info', 'status', 'pass',
              'stage', 'osc_node', 'vpp_V', 'freq_Hz', 'period_jitter',
              'dc_power_mW']


def create_testbench(scs_file, subckt_name, ports_list, sim_dir, args,
                     ib_dirs=None, tstop=2e-6, maxstep=2e-9):
    """Write the Spectre testbench for one DUT; returns (tb_path, bias_info, skip_reason)."""
    sim_dir.mkdir(parents=True, exist_ok=True)
    tb = sim_dir / 'testbench.scs'
    vdd = args.vdd
    pset = set(p.upper() for p in ports_list)

    vouts = sorted((p for p in pset if p.startswith('VOUT')),
                   key=lambda s: int(s[4:]))
    handled = {'VDD', 'VSS'} | set(vouts)
    misc_lines, infos, misc_saves, skip = tc.classify_misc_ports(
        scs_file, ports_list, handled, vdd, ib_dirs=ib_dirs)
    if skip:
        return None, None, None, skip

    save_sigs = [v.lower() for v in vouts]

    with open(tb, 'w') as f:
        tc.write_tb_header(f, CATEGORY, scs_file, subckt_name, ports_list)
        f.write('// -- Power -------------------------------------------\n')
        f.write(f'Vvdd (vdd 0) vsource dc={vdd} type=dc\n')
        f.write('Vvss (vss 0) vsource dc=0 type=dc\n')
        for line in misc_lines:
            f.write(line + '\n')
        f.write('\n')
        tc.write_dut(f, ports_list, subckt_name)
        f.write('ic vout1=0  // initial condition to trigger oscillation startup\n\n')
        tc.write_sim_options(f, args.temp)
        f.write(f'save {" ".join(save_sigs + misc_saves)}\n')
        f.write('saveOptions options save=selected pwr=total\n\n')
        f.write('dc_op dc oppoint=rawfile\n\n')
        f.write(f'tran1 tran stop={tstop:g} maxstep={maxstep:g} annotate=status\n')
    return tb, ' '.join(infos), save_sigs, None


def _analyze_node(t, v):
    """Last 50% window -> (vpp, freq|None, jitter|None, periodic)."""
    mask = t >= t[-1] * 0.5
    tw, vw = t[mask], v[mask]
    if len(tw) < 10:
        return 0.0, None, None, False
    vpp = float(np.max(vw) - np.min(vw))

    mid = (np.max(vw) + np.min(vw)) / 2
    d = vw - mid
    tx = []
    for i in range(1, len(d)):
        if d[i-1] < 0 <= d[i]:   # rising crossing
            frac = -d[i-1] / (d[i] - d[i-1])
            tx.append(tw[i-1] + frac * (tw[i] - tw[i-1]))
    if len(tx) < 4:
        return vpp, None, None, False
    periods = np.diff(tx)
    mean_p = float(np.mean(periods))
    jitter = float(np.std(periods) / mean_p) if mean_p > 0 else None
    periodic = jitter is not None and jitter < PERIOD_TOL
    freq = 1.0 / mean_p if mean_p > 0 else None
    return vpp, freq, jitter, periodic


def measure(sim_dir, save_sigs, vdd):
    """Extract the category metrics from the simulation results, or None on parse failure."""
    t, data = tc.parse_tran(sim_dir, save_sigs)
    if t is None or len(t) < 20:
        return None

    best = None
    for sig in save_sigs:
        v = data.get(sig)
        if v is None:
            continue
        vpp, freq, jitter, periodic = _analyze_node(t, v)
        cand = {'osc_node': sig, 'vpp_V': vpp, 'freq_Hz': freq,
                'period_jitter': jitter, 'periodic': periodic}
        if best is None or (cand['periodic'], cand['vpp_V']) > \
                           (best['periodic'], best['vpp_V']):
            best = cand
    if best is None:
        return None

    pwr, _ = tc.parse_dc_op(sim_dir)
    best['dc_power_mW'] = pwr * 1e3 if pwr is not None else None
    return best


def main():
    """Command-line entry point: select DUTs, simulate each, record summary.csv."""
    ap = tc.base_argparser('Oscillator batch testbench (2-pass transient, GPDK045)')
    args = ap.parse_args()
    subckt_dir = Path(args.subckt_dir) if args.subckt_dir else SUBCKT_DIR
    out_dir = Path(args.out_dir) if args.out_dir else OUT_DIR

    out_dir.mkdir(parents=True, exist_ok=True)
    run_ids = tc.parse_run_ids(args.run_ids)
    targets, n_skip = tc.collect_targets(subckt_dir, REQUIRED, run_ids, args.limit)
    pass_desc = ' -> '.join(f'{s}({t*1e9:g}ns/{m*1e12:g}ps)'
                            for s, t, m in PASSES)
    tc.print_header(CATEGORY, subckt_dir, len(targets), n_skip, out_dir,
                    extra=[f'PASS criterion : Vpp >= VDD*{VPP_FRAC:g} + periodicity '
                           f'(VDD={args.vdd} V)',
                           f'2-pass    : {pass_desc}',
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
            """For one IB direction combination: run the fine pass, then the
            slow pass only if no oscillation is detected."""
            best = None
            for stage, tstop, maxstep in PASSES:
                sdir = vdir / stage
                tb, bias_info, save_sigs, skip = create_testbench(
                    scs_file, name, ports, sdir, args,
                    ib_dirs=ib_dirs, tstop=tstop, maxstep=maxstep)
                if skip:
                    return {'status': 'bias_skip', 'passed': False,
                            'score': 0, 'skip': skip}
                if args.dry_run:
                    return {'status': 'dry-run', 'passed': False,
                            'score': 0, 'bias_info': bias_info, 'tb': tb}
                ok, log = tc.run_spectre(tb, sdir, timeout=600)
                if not ok:
                    res = {'status': 'sim_fail', 'passed': False, 'score': 0,
                           'bias_info': bias_info, 'log': log}
                else:
                    m = measure(sdir, save_sigs, args.vdd)
                    if m is None:
                        res = {'status': 'parse_fail', 'passed': False,
                               'score': 0, 'bias_info': bias_info}
                    else:
                        passed = (m['vpp_V'] >= args.vdd * VPP_FRAC
                                  and m['periodic'])
                        res = {'status': 'ok', 'passed': passed,
                               'score': m['vpp_V'], 'bias_info': bias_info,
                               'metrics': m, 'stage': stage}
                if res['passed']:
                    return res
                if best is None or (res['status'] == 'ok') > \
                                   (best['status'] == 'ok') or \
                   res.get('score', 0) > best.get('score', 0):
                    best = res
            return best

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
        print(f'{IND}-> OK  [{tag}]  stage={res["stage"]}  '
              f'node={m["osc_node"]}  '
              f'Vpp={fmt(m["vpp_V"], ".3f")}V  '
              f'f={fmt(m["freq_Hz"], ".3g")}Hz  '
              f'jitter={fmt(m["period_jitter"], ".2f")}  '
              f'Pwr={fmt(m["dc_power_mW"], ".3g")}mW')
        summary.update(rid, {**base, 'status': 'ok', 'pass': int(passed),
                             'stage': res['stage'],
                             **{k: fmt(v) for k, v in m.items()
                                if k != 'periodic'}})

    tc.print_footer(CATEGORY, n_run, n_ok, n_fail, n_pass, summary.path)


if __name__ == '__main__':
    main()
