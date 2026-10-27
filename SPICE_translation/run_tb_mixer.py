#!/usr/bin/env python3
"""
run_tb_mixer - Mixer batch testbench (SPICE_Inference_Mixer)

Target : subckts containing VSS + VLO1 + RF input (VRF1 > VIN1 > IIN1)
         + output (VIF1 > VOUT1)
Method : downconversion transient - RF 10 MHz (50 mV sine), LO 9 MHz
         (1 V sine, VLO2 anti-phase), 10 us simulation, then output FFT
         (IIN1-type input driven with DC 10u + 5u sine current)
Measure: 1 MHz IF tone amplitude, conversion gain (w.r.t. voltage RF),
         spectral prominence ratio
PASS   : A(1MHz) >= 1 mV AND A(1MHz) >= 3 x spectral median
Output : batch_results/Mixer/run<id>/ + summary.csv
"""

from pathlib import Path

import numpy as np

import tb_common as tc
from tb_common import BASE_DIR, IND, fmt

CATEGORY   = 'Mixer'
SUBCKT_DIR = BASE_DIR / 'SPICE_Inference_Mixer'
OUT_DIR    = BASE_DIR / 'batch_results' / CATEGORY
REQUIRED   = {'VSS', 'VLO1'}

F_RF, F_LO, F_IF = 10e6, 9e6, 1e6
RF_AMP_V  = 0.05
RF_DC_I, RF_AMP_I = 10e-6, 5e-6
LO_AMP_V  = 1.0
TSTOP, MAXSTEP = 10e-6, 5e-9
IF_MIN_V, PROM_RATIO = 1e-3, 3.0

CSV_FIELDS = ['run_id', 'subckt_name', 'ports', 'bias_info', 'status', 'pass',
              'rf_port', 'out_port', 'a_if_V', 'conv_gain_dB', 'prominence',
              'dc_power_mW']


def _pick_ports(ports):
    """Choose the RF input and IF output ports of a mixer DUT by preference order."""
    pset = set(p.upper() for p in ports)
    rf = next((p for p in ('VRF1', 'VIN1', 'IIN1') if p in pset), None)
    out = next((p for p in ('VIF1', 'VOUT1') if p in pset), None)
    return rf, out


def _extra_filter(scs_file, name, ports):
    """Per-category port condition applied on top of the required-port set."""
    rf, out = _pick_ports(ports)
    return rf is not None and out is not None


def create_testbench(scs_file, subckt_name, ports_list, sim_dir, args,
                     ib_dirs=None):
    """Write the Spectre testbench for one DUT; returns (tb_path, bias_info, skip_reason)."""
    sim_dir.mkdir(parents=True, exist_ok=True)
    tb = sim_dir / 'testbench.scs'
    vdd = args.vdd
    vmid = round(vdd / 2, 3)
    pset = set(p.upper() for p in ports_list)
    rf, out = _pick_ports(ports_list)

    handled = {'VSS', 'VLO1', rf, out}
    handled |= {'VDD', 'VLO2', 'VRF2', 'VIF2'} & pset
    misc_lines, infos, misc_saves, skip = tc.classify_misc_ports(
        scs_file, ports_list, handled, vdd, ib_dirs=ib_dirs)
    if skip:
        return None, None, None, skip

    save_sigs = [out.lower()]
    if out == 'VIF1' and 'VIF2' in pset:
        save_sigs.append('vif2')

    with open(tb, 'w') as f:
        tc.write_tb_header(f, CATEGORY, scs_file, subckt_name, ports_list)
        f.write('// -- Power -------------------------------------------\n')
        f.write('Vvss (vss 0) vsource dc=0 type=dc\n')
        if 'VDD' in pset:
            f.write(f'Vvdd (vdd 0) vsource dc={vdd} type=dc\n')
        f.write('\n// -- LO ----------------------------------------------\n')
        f.write(f'Vvlo1 (vlo1 0) vsource type=sine dc={vmid} ampl={LO_AMP_V} '
                f'freq={F_LO:g} sinephase=0\n')
        if 'VLO2' in pset:
            f.write(f'Vvlo2 (vlo2 0) vsource type=sine dc={vmid} ampl={LO_AMP_V} '
                    f'freq={F_LO:g} sinephase=180  // anti-phase\n')
        f.write('\n// -- RF ----------------------------------------------\n')
        if rf == 'IIN1':
            d = tc.determine_ib_direction(scs_file, 'IIN1') or 'in'
            nodes = '(iin1 0)' if d == 'out' else '(0 iin1)'
            f.write(f'Iiin1 {nodes} isource type=sine dc={RF_DC_I:g} '
                    f'ampl={RF_AMP_I:g} freq={F_RF:g}  // RF current ({d})\n')
        else:
            f.write(f'V{rf.lower()} ({rf.lower()} 0) vsource type=sine dc={vmid} '
                    f'ampl={RF_AMP_V} freq={F_RF:g}\n')
        if 'VRF2' in pset and rf != 'VRF2':
            f.write(f'Vvrf2 (vrf2 0) vsource dc={vmid} type=dc\n')
        for line in misc_lines:
            f.write(line + '\n')
        f.write('\n')
        tc.write_dut(f, ports_list, subckt_name)
        tc.write_sim_options(f, args.temp)
        f.write(f'save {" ".join(save_sigs + misc_saves)}\n')
        f.write('saveOptions options save=selected pwr=total\n\n')
        f.write('dc_op dc oppoint=rawfile\n\n')
        f.write(f'tran1 tran stop={TSTOP:g} maxstep={MAXSTEP:g} annotate=status\n')
    return tb, ' '.join(infos), (rf, out, save_sigs), None


def measure(sim_dir, rf, out, save_sigs):
    """Extract the category metrics from the simulation results, or None on parse failure."""
    t, data = tc.parse_tran(sim_dir, save_sigs)
    if t is None or data.get(save_sigs[0]) is None or len(t) < 100:
        return None
    v = data[save_sigs[0]]
    v2 = data.get(save_sigs[1]) if len(save_sigs) > 1 else None
    if v2 is not None:
        v = v - v2   # differential IF

    # uniform resampling + Hann FFT
    n = 8192
    tu = np.linspace(t[0], t[-1], n)
    vu = np.interp(tu, t, v)
    vu -= np.mean(vu)
    w = np.hanning(n)
    spec = np.abs(np.fft.rfft(vu * w)) * 2.0 / np.sum(w)
    freqs = np.fft.rfftfreq(n, d=(tu[-1] - tu[0]) / (n - 1))

    k_if = int(np.argmin(np.abs(freqs - F_IF)))
    a_if = float(np.max(spec[max(k_if - 1, 1):k_if + 2]))
    med = float(np.median(spec[1:]))
    prom = a_if / max(med, 1e-30)

    conv_gain_db = (20 * np.log10(a_if / RF_AMP_V)
                    if rf != 'IIN1' and a_if > 0 else None)

    pwr, _ = tc.parse_dc_op(sim_dir)
    return {
        'a_if_V':       a_if,
        'conv_gain_dB': conv_gain_db,
        'prominence':   prom,
        'dc_power_mW':  pwr * 1e3 if pwr is not None else None,
    }


def main():
    """Command-line entry point: select DUTs, simulate each, record summary.csv."""
    ap = tc.base_argparser('Mixer batch testbench (downconversion FFT, GPDK045)')
    args = ap.parse_args()
    subckt_dir = Path(args.subckt_dir) if args.subckt_dir else SUBCKT_DIR
    out_dir = Path(args.out_dir) if args.out_dir else OUT_DIR

    out_dir.mkdir(parents=True, exist_ok=True)
    run_ids = tc.parse_run_ids(args.run_ids)
    targets, n_skip = tc.collect_targets(subckt_dir, REQUIRED, run_ids,
                                         args.limit, extra_filter=_extra_filter)
    tc.print_header(CATEGORY, subckt_dir, len(targets), n_skip, out_dir,
                    extra=[f'PASS criterion : A(1MHz) >= {IF_MIN_V*1e3:g} mV, '
                           f'prominence >= {PROM_RATIO}x  '
                           f'(RF {F_RF/1e6:g}MHz, LO {F_LO/1e6:g}MHz, '
                           f'VDD={args.vdd} V)',
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
            tb, bias_info, sigdesc, skip = create_testbench(
                scs_file, name, ports, vdir, args, ib_dirs=ib_dirs)
            if skip:
                return {'status': 'bias_skip', 'passed': False, 'score': 0,
                        'skip': skip}
            if args.dry_run:
                return {'status': 'dry-run', 'passed': False, 'score': 0,
                        'bias_info': bias_info, 'tb': tb, 'sigdesc': sigdesc}
            ok, log = tc.run_spectre(tb, vdir, timeout=600)
            if not ok:
                return {'status': 'sim_fail', 'passed': False, 'score': 0,
                        'bias_info': bias_info, 'log': log, 'sigdesc': sigdesc}
            m = measure(vdir, *sigdesc)
            if m is None:
                return {'status': 'parse_fail', 'passed': False, 'score': 0,
                        'bias_info': bias_info, 'sigdesc': sigdesc}
            passed = m['a_if_V'] >= IF_MIN_V and m['prominence'] >= PROM_RATIO
            return {'status': 'ok', 'passed': passed, 'score': m['a_if_V'],
                    'bias_info': bias_info, 'metrics': m, 'sigdesc': sigdesc}

        res, n_tried = tc.try_ib_variants(scs_file, ports, sim_dir, attempt)
        tried_str = f'  [{n_tried} variant(s)]' if n_tried > 1 else ''
        sigdesc = res.get('sigdesc')
        rf, out = (sigdesc[0], sigdesc[1]) if sigdesc else ('-', '-')
        print(f'[{i+1:4d}/{len(targets)}] run{rid:<5} RF={rf} OUT={out}  '
              f'{res.get("bias_info") or res.get("skip") or ""}{tried_str}')
        base = {'run_id': rid, 'subckt_name': name, 'ports': ' '.join(ports),
                'bias_info': res.get('bias_info', ''),
                'rf_port': rf, 'out_port': out}

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
        cg = (f'{fmt(m["conv_gain_dB"], ".1f")}dB'
              if m['conv_gain_dB'] is not None else 'N/A')
        print(f'{IND}-> OK  [{tag}]  A_IF={fmt(m["a_if_V"]*1e3, ".3g")}mV  '
              f'convGain={cg}  prom={fmt(m["prominence"], ".1f")}x  '
              f'Pwr={fmt(m["dc_power_mW"], ".3g")}mW')
        summary.update(rid, {**base, 'status': 'ok', 'pass': int(passed),
                             **{k: fmt(v) for k, v in m.items()}})

    tc.print_footer(CATEGORY, n_run, n_ok, n_fail, n_pass, summary.path)


if __name__ == '__main__':
    main()
