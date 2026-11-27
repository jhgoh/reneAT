"""
Run-level data quality monitoring from the prompt outputs (prompt.py).

``run_report(run)`` writes ``<out>/dqm/<run:06d>/``:
    summary.json      numbers of the run (one row of the trend), flags
    overview.png      rates vs time, clock / trigger-number checks, run info
    fadc.png          inner PMTs: spectra, pedestal, noise, pulse position, A/B vs time
    veto.png          SADC: channel rates, rates vs time, spectra, multiplicity, coincidences
    prompt.png        time correlations: trigger spacing, after-muon spacing, delayed pairs
    index.html        the four pages and the flags
``trend()`` writes ``<out>/dqm/trend.csv``, ``trend.png`` and ``index.html`` over all runs.

Times inside a run are the TCB elapsed time; sub-runs are chained with the gap between the
last entry of one and the first entry of the next (modulo the 16.78 s TCB wrap).
"""
import csv
import datetime as dt
import glob
import html
import json
import os

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import prd
import prompt
from prompt import QSUM_EDGES, SADC_EDGES, DT_EDGES, PEAK_EDGES, PED_EDGES, RMS_EDGES, RISE_EDGES, SPE_EDGES

# prompt pair search (delayed = FADC trigger following another one), in us and Qgm
PAIR_WINDOW = (10.0, 200.0)    # starts after the retriggers that follow large pulses (< 10 us)
MUON_VETO_US = 1000.0
DEFAULT_FLAGS = {"max_gap_s": 1.0, "rate_drop": 0.5, "ped_shift": 3.0, "rise_shift": 5.0, "noise_max": 1.5,
                 "rule_mismatch": 0.01, "spe_shift": 0.10, "slot8_max": 0.5}
PC_PER_ADC_SAMPLE = 0.488e-3 * 2e-9 / 50 * 1e12      # 2 V / 4096 counts, 2 ns, 50 ohm
E_PC = 1.602176634e-7


def spe_peak(h, edges=None):
    """Position of the single-photoelectron peak in a single-pulse charge histogram:
    Gaussian fit around the smoothed mode above 15 ADC x sample. None if too few entries."""
    from scipy.optimize import curve_fit
    edges = SPE_EDGES if edges is None else edges
    h = np.asarray(h, float); x = _centers(edges)
    m = x > 15
    if h[m].sum() < 200:
        return None
    mode = x[m][np.argmax(np.convolve(h[m], np.ones(5) / 5, "same"))]
    sel = (x > 0.6 * mode) & (x < 1.5 * mode)
    g = lambda x, a, mu, s: a * np.exp(-0.5 * ((x - mu) / s) ** 2)
    try:
        p, _ = curve_fit(g, x[sel], h[sel], p0=[h[sel].max(), mode, 0.4 * mode])
        return float(p[1]) if 0.5 * mode < p[1] < 1.5 * mode else float(mode)
    except Exception:
        return float(mode)


def _previous_summary(run, base):
    """summary.json of the closest earlier run that has one."""
    best = None
    for fn in glob.glob(os.path.join(dqm_dir(None, base), "[0-9]" * 6, "summary.json")):
        r = int(os.path.basename(os.path.dirname(fn)))
        if r < run and (best is None or r > best[0]):
            best = (r, fn)
    if best is None:
        return None
    with open(best[1]) as fh:
        return json.load(fh)


def dqm_dir(run=None, base=None):
    d = os.path.join(prompt.out_dir(base), "dqm")
    return d if run is None else os.path.join(d, f"{run:06d}")


def _centers(e):
    return 0.5 * (e[1:] + e[:-1])


def _chain(summ):
    """Start time [s] of each sub-run from the run start, in sub-run order."""
    subs = sorted(summ)
    start, t = {}, 0.0
    prev = None
    for s in subs:
        x = summ[s]
        if x.get("error") or not x.get("n_read"):
            start[s] = t
            continue
        if prev is not None and prev.get("tcb_last") is not None:
            gap = (x["tcb_first"] - prev["tcb_last"]) % prd.TCB_WRAP_NS * 1e-9
            t += gap
        start[s] = t
        t += x["duration"]
        prev = x
    return start


def _sum_hist(summ, key, sub=None):
    tot = None
    for x in summ.values():
        h = x.get(sub, {}).get(key) if sub else x.get(key)
        if h is None:
            continue
        h = np.asarray(h)
        tot = h if tot is None else tot + h
    return tot


def _median_from_hist(h, edges):
    if h is None or h.sum() == 0:
        return np.nan
    c = np.cumsum(h)
    i = np.searchsorted(c, 0.5 * c[-1])
    return float(_centers(edges)[i])


def run_report(run, base=None, catalog=None, flags_cfg=None, pairs=True):
    flags_cfg = {**DEFAULT_FLAGS, **(flags_cfg or {})}
    summ = prompt.read_summaries(run, base)
    if not summ:
        raise FileNotFoundError(f"no prompt outputs for run {run} under {prompt.out_dir(base)}")
    try:
        prd_subs = sorted(prd.subrun_of(f) for f in prd.run_files(run))
    except FileNotFoundError:
        prd_subs = []
    if catalog is None:
        from catalog import RunCatalog
        catalog = RunCatalog()
    info = catalog[run] if run in catalog else {}
    import runsheet
    sheet = runsheet.try_sheet()
    sh = (sheet.get(run) if sheet else None) or {}

    subs = sorted(summ)
    start = _chain(summ)
    good = [s for s in subs if not summ[s].get("error") and summ[s].get("n_read")]
    dur = np.array([summ[s]["duration"] if s in good else 0.0 for s in subs])
    tmid = np.array([(start[s] + 0.5 * summ[s].get("duration", 0) if s in good else start[s]) for s in subs]) / 3600
    livetime = float(dur.sum())

    def per_sub(fn):
        return np.array([fn(summ[s]) if s in good else np.nan for s in subs], dtype=float)

    et_n = {k: per_sub(lambda x, k=k: x["eventtype"].get(k, 0)) for k in ("1", "2", "3")}
    with np.errstate(invalid="ignore", divide="ignore"):
        et_rate = {k: v / np.where(dur > 0, dur, np.nan) for k, v in et_n.items()}

    flags = []
    missing = sorted(set(prd_subs) - set(subs))
    errors = {s: summ[s]["error"] for s in subs if summ[s].get("error")}
    holes = sorted(set(range(min(prd_subs), max(prd_subs) + 1)) - set(prd_subs)) if prd_subs else []
    if missing:
        flags.append(f"{len(missing)} PRD sub-runs not processed yet")
    if errors:
        flags.append(f"{len(errors)} unreadable sub-runs: {sorted(errors)[:10]}")
    if holes:
        flags.append(f"{len(holes)} sub-run numbers missing in PRD: {holes[:10]}")
    max_gap = per_sub(lambda x: x["max_gap"])
    if np.nanmax(max_gap, initial=0) > flags_cfg["max_gap_s"]:
        bad = [s for s, g in zip(subs, max_gap) if g > flags_cfg["max_gap_s"]]
        flags.append(f"trigger gap > {flags_cfg['max_gap_s']} s in {len(bad)} sub-runs: {bad[:10]}")
    for k, name in (("1", "FADC-only"), ("2", "SADC-only"), ("3", "FADC+SADC")):
        r = et_rate[k]
        if np.nansum(et_n[k]) > 0:
            med = np.nanmedian(r)
            low = [s for s, x in zip(subs, r) if x < flags_cfg["rate_drop"] * med]
            if low:
                flags.append(f"{name} rate below {flags_cfg['rate_drop']:.0%} of the run median in {len(low)} sub-runs: {low[:10]}")
    back = per_sub(lambda x: x["tcb_backward"] + x["trgnum_back"] + x["trgnum_dup"])
    if np.nansum(back) > 0:
        flags.append(f"out-of-order TCB time or trigger number: {int(np.nansum(back))} entries")

    has_fadc = any("fadc" in summ[s] for s in good)
    has_sadc = any("sadc" in summ[s] for s in good)
    if sh.get("Data issue"):
        flags.append(f"run sheet data issue: {sh['Data issue']}")
    row = {"run": run, "dataset": sh.get("dataset", ""), "type": sh.get("type", ""), "source": sh.get("source", ""),
           "stime": info.get("stime"), "etime": info.get("etime"),
           "config": os.path.basename(info.get("config") or ""), "rundesc": (info.get("rundesc") or "").replace("\n", " ")[:200],
           "n_prd_subruns": len(prd_subs), "n_processed": len(subs), "n_error": len(errors),
           "livetime": livetime, "tfadc_catalog": info.get("tfadc"),
           "rate_fadc_only": float(np.nansum(et_n["1"]) / livetime) if livetime else 0.0,
           "rate_sadc_only": float(np.nansum(et_n["2"]) / livetime) if livetime else 0.0,
           "rate_both": float(np.nansum(et_n["3"]) / livetime) if livetime else 0.0}
    if livetime:
        n_all = float(np.nansum(per_sub(lambda x: x["n_read"])))
        row["rate_both_ab"] = float(np.nansum(per_sub(lambda x: x.get("et3_ab", np.nan))) / livetime)
        row["rate_both_single"] = float(np.nansum(per_sub(lambda x: x.get("et3_single", np.nan))) / livetime)
        dtmin = per_sub(lambda x: x.get("dt_min_us") if x.get("dt_min_us") is not None else np.nan)
        row["dt_min_us"] = float(np.nanmin(dtmin)) if np.isfinite(dtmin).any() else None
        # dead time: every recorded entry blocks the next for about dt_min; skipped trigger numbers were lost
        row["dead_frac_est"] = n_all / livetime * row["dt_min_us"] * 1e-6 if row["dt_min_us"] else None
        row["trgnum_skip_frac"] = float(np.nansum(per_sub(lambda x: x["trgnum_skip"])) / max(n_all, 1))

    os.makedirs(dqm_dir(run, base), exist_ok=True)
    out = dqm_dir(run, base)
    title = (f"Run {run}  {info.get('stime', '')}  {sh.get('dataset', '')} {sh.get('source', '')}  "
             f"{os.path.basename(info.get('config') or '')}")

    pages = []

    # ---------------- FADC
    if has_fadc:
        fig, ax = plt.subplots(3, 4, figsize=(22, 12))
        for c, col in ((0, "C0"), (1, "C3")):
            h = _sum_hist(summ, f"qsum_{c}", "fadc")
            ax[0, 0].step(_centers(QSUM_EDGES)[1:], (h / np.diff(QSUM_EDGES) / livetime)[1:], where="mid", color=col, label=f"PMT {'AB'[c]}")
            row[f"qsum_median_{c}"] = _median_from_hist(h, QSUM_EDGES)
            hp = _sum_hist(summ, f"peak_{c}", "fadc")
            ax[0, 2].step(_centers(PEAK_EDGES), hp, where="mid", color=col, label=f"PMT {'AB'[c]}: median {_median_from_hist(hp, PEAK_EDGES):.0f}")
            row[f"peak_median_{c}"] = _median_from_hist(hp, PEAK_EDGES)
            row[f"ped_median_{c}"] = float(np.nanmedian(per_sub(lambda x: x.get("fadc", {}).get(f"ped_median_{c}", np.nan))))
            row[f"pedrms_median_{c}"] = float(np.nanmedian(per_sub(lambda x: x.get("fadc", {}).get(f"pedrms_median_{c}", np.nan))))
            for key in ("pedeo_median", "rise_median", "width_median", "fired_median", "prepulse_frac"):
                v = per_sub(lambda x: (x.get("fadc", {}).get(f"{key}_{c}") if x.get("fadc", {}).get(f"{key}_{c}") is not None else np.nan))
                row[f"{key}_{c}"] = float(np.nanmedian(v)) if np.isfinite(v).any() else None
                if key == "rise_median" and np.isfinite(v).any():
                    bad = [sb for sb, x in zip(subs, v) if abs(x - row[f"{key}_{c}"]) > flags_cfg["rise_shift"]]
                    if bad:
                        flags.append(f"PMT {'AB'[c]} pulse shape changed (rise time off by > {flags_cfg['rise_shift']:.0f} samples) in {len(bad)} sub-runs: {bad[:10]}")
            if row[f"pedrms_median_{c}"] > flags_cfg["noise_max"]:
                flags.append(f"PMT {'AB'[c]} random noise {row[f'pedrms_median_{c}']:.2f} ADC (> {flags_cfg['noise_max']})")
            hr = _sum_hist(summ, f"rise_{c}", "fadc")
            if hr is not None:
                ax[0, 3].step(_centers(RISE_EDGES), hr / max(hr.sum(), 1), where="mid", color=col,
                              label=f"PMT {'AB'[c]}: median {_median_from_hist(hr, RISE_EDGES):.0f}, Qsum/height {row[f'width_median_{c}'] or 0:.1f}")
            for (i, j), key, lab in (((1, 0), "ped_median", "pedestal median [ADC]"),
                                     ((1, 1), "pedrms_median", "random noise: pedestal rms after even/odd pedestals [ADC]"),
                                     ((1, 3), "pedeo_median", "even - odd sample offset [ADC]"),
                                     ((2, 3), "rise_median", "pulse rise: peak - leading edge [samples]"),
                                     ((1, 2), "peak_median", "pulse peak sample median"),
                                     ((2, 0), "qsum_median", "Qsum median")):
                y = per_sub(lambda x: x.get("fadc", {}).get(f"{key}_{c}", np.nan))
                ax[i, j].plot(tmid, y, ".", ms=3, color=col, label=f"PMT {'AB'[c]}")
                ax[i, j].set_ylabel(lab); ax[i, j].set_xlabel("hours since run start")
            sat = per_sub(lambda x: x.get("fadc", {}).get("n_sat", [0, 0])[c]) / np.maximum(per_sub(lambda x: x.get("fadc", {}).get("n_trig", 0)), 1)
            ax[2, 2].plot(tmid, sat, ".", ms=3, color=col, label=f"PMT {'AB'[c]}")
            row[f"sat_frac_{c}"] = float(np.nansum(sat * per_sub(lambda x: x.get("fadc", {}).get("n_trig", 0))) /
                                         max(np.nansum(per_sub(lambda x: x.get("fadc", {}).get("n_trig", 0))), 1))
        hg = _sum_hist(summ, "qgm", "fadc")
        ax[0, 0].step(_centers(QSUM_EDGES)[1:], (hg / np.diff(QSUM_EDGES) / livetime)[1:], where="mid", color="k", label="sqrt(A*B)")
        row["qgm_median"] = _median_from_hist(hg, QSUM_EDGES)
        ax[0, 0].set_xscale("log"); ax[0, 0].set_yscale("log"); ax[0, 0].set_xlabel("Qsum [ADC x sample]")
        ax[0, 0].set_ylabel("rate density [Hz per unit]"); ax[0, 0].set_title("FADC Qsum spectra"); ax[0, 0].legend(fontsize=8)
        y = per_sub(lambda x: x.get("fadc", {}).get("log_ab_median", np.nan))
        ax[0, 1].plot(tmid, y, ".", ms=3, color="k"); ax[0, 1].set_ylabel("median log10(Qsum A / Qsum B)")
        ax[0, 1].set_xlabel("hours since run start"); ax[0, 1].set_title("A/B balance")
        row["log_ab_median"] = float(np.nanmedian(y))
        ax[0, 2].set_xlim(100, 350); ax[0, 2].set_title("pulse peak sample"); ax[0, 2].legend(fontsize=8)
        ax[2, 1].plot(tmid, et_rate["1"] + np.nan_to_num(et_rate["3"]), ".", ms=3, color="k")
        ax[2, 1].set_ylabel("FADC trigger rate [Hz]"); ax[2, 1].set_xlabel("hours since run start")
        ax[2, 2].set_ylabel("saturated fraction"); ax[2, 2].set_xlabel("hours since run start")
        ax[0, 3].set_xlabel("peak - leading edge [samples], height > 200, not saturated"); ax[0, 3].set_title("pulse rise")
        for a in ax.flat:
            if a.get_legend_handles_labels()[0] and a.get_legend() is None:
                a.legend(fontsize=8)
        fig.suptitle(title + "  -  inner PMTs (FADC)"); fig.tight_layout()
        fig.savefig(os.path.join(out, "fadc.png"), dpi=80); plt.close(fig)
        pages.append("fadc.png")

    # ---------------- FADC sample-slot pattern: even/odd offset (per event) and the 8-slot clock pattern
    if has_fadc and any(f"slot8_amp_0" in summ[s_].get("fadc", {}) for s_ in good):
        fig, ax = plt.subplots(2, 3, figsize=(19, 10))
        freqs = ("62.5", "125", "187.5")
        for c, col in ((0, "C0"), (1, "C3")):
            eo = per_sub(lambda x: x.get("fadc", {}).get(f"eo_mean_{c}", np.nan))
            jit = per_sub(lambda x: x.get("fadc", {}).get(f"eo_jitter_{c}", np.nan))
            ax[0, 0].plot(tmid, eo, ".", ms=3, color=col, label=f"PMT {'AB'[c]}: run median {np.nanmedian(eo):.2f}")
            ax[0, 1].plot(tmid, jit, ".", ms=3, color=col, label=f"PMT {'AB'[c]}: run median {np.nanmedian(jit):.2f}")
            row[f"eo_mean_{c}"] = float(np.nanmedian(eo)) if np.isfinite(eo).any() else None
            row[f"eo_min_{c}"] = float(np.nanmin(eo)) if np.isfinite(eo).any() else None
            row[f"eo_max_{c}"] = float(np.nanmax(eo)) if np.isfinite(eo).any() else None
            row[f"eo_jitter_{c}"] = float(np.nanmedian(jit)) if np.isfinite(jit).any() else None
            # run mean 8-slot shape, weighted by the number of quiet records per sub-run
            sh_, wt = [], []
            for s_ in good:
                f_ = summ[s_].get("fadc", {})
                if f"slot8_{c}" in f_:
                    sh_.append(f_[f"slot8_{c}"]); wt.append(f_.get(f"eo_n_{c}", 1))
            if sh_:
                shape = np.average(np.array(sh_), axis=0, weights=np.array(wt, float))
                F = np.abs(np.fft.rfft(shape)) * 2 / 8
                row[f"slot8_{c}"] = np.round(shape, 4).tolist()
                for j, fq in enumerate(freqs):
                    row[f"slot8_{fq}_{c}"] = float(F[j + 1])
                ax[0, 2].plot(range(8), shape, "o-", color=col,
                              label=f"PMT {'AB'[c]}: 62.5/125/187.5 MHz = {F[1]:.2f}/{F[2]:.2f}/{F[3]:.2f}")
                if max(F[1:4]) > flags_cfg["slot8_max"]:
                    flags.append(f"PMT {'AB'[c]} clock-synchronous 8-sample pattern {max(F[1:4]):.2f} ADC (> {flags_cfg['slot8_max']})")
            for j, (fq, ls) in enumerate(zip(freqs, ("-", "--", ":"))):
                y = per_sub(lambda x: (x.get("fadc", {}).get(f"slot8_amp_{c}") or [np.nan] * 3)[j])
                ax[1, c].plot(tmid, y, ls, lw=0.9, label=f"{fq} MHz")
            ax[1, c].set_title(f"PMT {'AB'[c]}: 8-sample pattern per sub-run"); ax[1, c].set_xlabel("hours since run start")
            ax[1, c].set_ylabel("amplitude [ADC]"); ax[1, c].legend(fontsize=9)
        ax[0, 0].set_title("even - odd offset (per event, sub-run mean)"); ax[0, 0].set_ylabel("ADC")
        ax[0, 1].set_title("event-to-event spread of the even/odd offset"); ax[0, 1].set_ylabel("ADC")
        ax[0, 2].set_title("8-sample pattern after even/odd, run mean (aligned to the 16 ns TCB clock)")
        ax[0, 2].set_xlabel("sample slot (index + 4 x TCB 16 ns phase) mod 8"); ax[0, 2].set_ylabel("ADC"); ax[0, 2].axhline(0, color="grey", lw=0.5)
        for a_ in (ax[0, 0], ax[0, 1]):
            a_.set_xlabel("hours since run start")
        for a_ in ax[0]:
            a_.legend(fontsize=9)
        ax[1, 2].axis("off")
        ax[1, 2].text(0, 1, "From quiet pedestal windows (samples 0-99) of FADC triggers.\n"
                      "even/odd: two sample paths of the ADC; changes between runs and\n"
                      "within a run, so qsum takes it from every event.\n"
                      "8-sample pattern: what is left after even/odd; locked to the\n"
                      "16 ns clock and stable within a run (clock pick-up).",
                      va="top", fontsize=11, family="monospace")
        fig.suptitle(title + "  -  FADC sample-slot pattern"); fig.tight_layout()
        fig.savefig(os.path.join(out, "adc.png"), dpi=80); plt.close(fig)
        pages.append("adc.png")

    # ---------------- PMT / FADC front end: single p.e., effective threshold, trigger rule, settings
    if has_fadc:
        fig, ax = plt.subplots(2, 3, figsize=(18, 9))
        g = max(1, len(good) // 12)                                     # ~12 time bins for the gain trend
        for c, col in ((0, "C0"), (1, "C3")):
            h = _sum_hist(summ, f"spe_{c}", "fadc")
            if h is not None:
                q1 = spe_peak(h)
                row[f"spe_q1_{c}"] = q1
                row[f"spe_pc_{c}"] = q1 * PC_PER_ADC_SAMPLE if q1 else None
                row[f"spe_n_{c}"] = int(h.sum())
                ax[0, 0].step(_centers(SPE_EDGES), h, where="mid", color=col,
                              label=f"PMT {'AB'[c]}: peak {q1 or 0:.0f} ADCxsample = {(q1 or 0) * PC_PER_ADC_SAMPLE:.2f} pC (n={int(h.sum())})")
                if q1:
                    ax[0, 0].axvline(q1, color=col, ls=":")
                tq, yq = [], []
                for i in range(0, len(good), g):
                    grp = good[i:i + g]
                    hh = np.sum([np.asarray(summ[s]["fadc"][f"spe_{c}"]) for s in grp if f"spe_{c}" in summ[s].get("fadc", {})], axis=0)
                    q = spe_peak(hh) if np.ndim(hh) else None
                    if q:
                        tq.append(np.mean([start[s] + 0.5 * summ[s]["duration"] for s in grp]) / 3600); yq.append(q * PC_PER_ADC_SAMPLE)
                ax[0, 1].plot(tq, yq, "o-", ms=4, color=col, label=f"PMT {'AB'[c]}")
                if q1 and yq and (max(yq) - min(yq)) / (q1 * PC_PER_ADC_SAMPLE) > flags_cfg["spe_shift"]:
                    flags.append(f"PMT {'AB'[c]} single p.e. peak moves by {100 * (max(yq) - min(yq)) / (q1 * PC_PER_ADC_SAMPLE):.0f}% within the run")
            for key, ls in (("effthr_even", "-"), ("effthr_odd", "--")):
                y = per_sub(lambda x: x.get("fadc", {}).get(f"{key}_{c}", np.nan))
                ax[0, 2].plot(tmid, y, ls, color=col, lw=0.8, label=f"PMT {'AB'[c]} {key.split('_')[1]} samples")
                row[f"{key}_{c}"] = float(np.nanmedian(y)) if np.isfinite(y).any() else None
            n = per_sub(lambda x: x.get("fadc", {}).get(f"rule_n_{c}", np.nan))
            for key, mk in (("rule_on_bit_off", "v"), ("rule_off_bit_on", "^")):
                k_ = per_sub(lambda x: x.get("fadc", {}).get(f"{key}_{c}", np.nan))
                with np.errstate(invalid="ignore", divide="ignore"):
                    ax[1, 0].plot(tmid, k_ / n, mk, ms=3, color=col, label=f"PMT {'AB'[c]} {key.replace('_', ' ')}")
                row[f"{key}_frac_{c}"] = float(np.nansum(k_) / max(np.nansum(n), 1))
            mism = row[f"rule_on_bit_off_frac_{c}"] + row[f"rule_off_bit_on_frac_{c}"]
            if mism > flags_cfg["rule_mismatch"]:
                flags.append(f"PMT {'AB'[c]} trigger bit disagrees with raw >= board pedestal + THR + 1 in {100 * mism:.1f}% of triggers")
            bp = sorted({v for s_ in good for v in summ[s_].get("fadc", {}).get(f"board_ped_{c}", [])})
            row[f"board_ped_{c}"] = bp
            if len(bp) > 1:
                flags.append(f"PMT {'AB'[c]} board pedestal changes within the run: {bp}")
            y = per_sub(lambda x: (x.get("fadc", {}).get(f"board_ped_{c}") or [np.nan])[0])
            ax[1, 1].plot(tmid, y, ".", ms=3, color=col, label=f"PMT {'AB'[c]} board pedestal")
            ax[1, 1].plot(tmid, per_sub(lambda x: x.get("fadc", {}).get(f"ped_median_{c}", np.nan)), "-", lw=0.8, color=col,
                          label=f"PMT {'AB'[c]} measured baseline (mean of even and odd)")
        fthr = sorted({tuple(summ[s_]["fadc"].get("f_thr", [])) for s_ in good if "fadc" in summ[s_]})
        row["f_thr"] = list(fthr[0]) if len(fthr) == 1 else [list(x) for x in fthr]
        if len(fthr) > 1:
            flags.append(f"F_THR changes within the run: {fthr}")
        try:
            thr_sheet = float(sh.get("THR (mV)", "nan"))
            if fthr and np.isfinite(thr_sheet) and any(abs(v - thr_sheet) > 0.5 for v in fthr[0][:2]):
                flags.append(f"run sheet THR {thr_sheet:g} differs from F_THR {list(fthr[0][:2])}")
        except ValueError:
            pass
        ax[0, 0].set_xlabel("isolated single-pulse charge in the pedestal window [ADC x sample]"); ax[0, 0].set_title("single p.e. (in situ)")
        ax[0, 1].set_xlabel("hours since run start"); ax[0, 1].set_ylabel("single p.e. peak [pC]"); ax[0, 1].set_title("gain trend")
        ax[0, 2].set_xlabel("hours since run start"); ax[0, 2].set_ylabel("ADC above the real baseline")
        ax[0, 2].set_title("effective FADC threshold = board pedestal + THR + 1 - baseline")
        ax[1, 0].set_xlabel("hours since run start"); ax[1, 0].set_ylabel("fraction of FADC triggers"); ax[1, 0].set_yscale("symlog", linthresh=1e-4)
        ax[1, 0].set_title("trigger bit vs raw-sample threshold rule")
        ax[1, 1].set_xlabel("hours since run start"); ax[1, 1].set_ylabel("ADC"); ax[1, 1].set_title("board pedestal and measured baseline")
        ax[1, 2].axis("off")
        for a in ax.flat:
            if a.get_legend_handles_labels()[0]:
                a.legend(fontsize=8)
        fig.suptitle(title + "  -  PMT and FADC front end"); fig.tight_layout()
        fig.savefig(os.path.join(out, "pmt.png"), dpi=80); plt.close(fig)
        pages.append("pmt.png")

    # ---------------- SADC (veto)
    if has_sadc:
        s0 = next(summ[s]["sadc"] for s in good if "sadc" in summ[s])
        nch = len(s0["thr"])
        pid = s0["pmt_id"]
        lab = [f"{c + 1}" for c in range(nch)]
        hits = np.array([summ[s]["sadc"]["n_hit"] if "sadc" in summ[s] else [np.nan] * nch for s in subs], float)
        with np.errstate(invalid="ignore", divide="ignore"):
            hrate = hits / dur[:, None]
        tot = np.nansum(hits, axis=0) / livetime
        row["veto_rate_total"] = float(np.nansum(hits) / livetime)
        row["veto_rate_by_ch"] = tot.tolist()
        row["sadc_thr"] = list(s0["thr"]); row["sadc_pmt_id"] = list(s0["pmt_id"])
        dead = [c + 1 for c in range(nch) if tot[c] == 0 and s0["thr"][c] < 10000]   # THR >= 10000: disabled
        if dead:
            flags.append(f"SADC channels without hits: {dead}")
        fig, ax = plt.subplots(2, 3, figsize=(18, 10))
        a = ax[0, 0]
        a.bar(np.arange(1, nch + 1), tot, color=["C0" if t < 1e9 else "C7" for t in s0["thr"]])
        a.set_xticks(np.arange(1, nch + 1)); a.set_xticklabels([f"{c}\n{p}" for c, p in zip(lab, pid)], fontsize=7)
        a.set_yscale("log"); a.set_xlabel("SADC channel (1-based) / PmtID"); a.set_ylabel("hit rate [Hz]")
        a.set_title("veto hit rate per channel")
        a = ax[0, 1]
        g = max(1, len(subs) // 144)                 # group sub-runs: ~144 time bins
        m = len(subs) // g * g
        hg_ = np.nansum(hits[:m].reshape(-1, g, nch), axis=1)
        dg_ = dur[:m].reshape(-1, g).sum(axis=1)
        with np.errstate(invalid="ignore", divide="ignore"):
            rg = hg_ / dg_[:, None]
            rel = rg / np.nanmedian(rg, axis=0)
        im = a.imshow(rel.T, aspect="auto", origin="lower", cmap="coolwarm", vmin=0.5, vmax=1.5,
                      extent=[tmid[0] if len(tmid) else 0, tmid[-1] if len(tmid) else 1, 0.5, nch + 0.5], interpolation="nearest")
        fig.colorbar(im, ax=a, label="rate / channel median")
        a.set_xlabel("hours since run start"); a.set_ylabel("SADC channel"); a.set_title("channel rate vs time")
        a = ax[0, 2]
        adc = np.array(_sum_hist(summ, "adc_hit", "sadc"), float)
        with np.errstate(divide="ignore"):
            im = a.imshow(np.log10(adc / np.diff(SADC_EDGES)[None, :] / livetime), aspect="auto", origin="lower",
                          extent=[0, len(SADC_EDGES) - 1, 0.5, nch + 0.5], interpolation="nearest")
        tick = [10, 100, 1000, 10000, 100000]
        a.set_xticks([np.searchsorted(SADC_EDGES, t) for t in tick]); a.set_xticklabels([str(t) for t in tick])
        fig.colorbar(im, ax=a, label="log10 rate density"); a.set_xlabel("SADC ADC (hits over threshold)")
        a.set_ylabel("SADC channel"); a.set_title("hit spectra")
        a = ax[1, 0]
        m = np.asarray(_sum_hist(summ, "mult", "sadc"), float)
        a.bar(np.arange(len(m)), m / livetime); a.set_yscale("log"); a.set_xlabel("channels over threshold in one entry")
        a.set_ylabel("rate [Hz]"); a.set_title("multiplicity")
        a = ax[1, 1]
        pair = np.asarray(_sum_hist(summ, "pair", "sadc"), float) / livetime
        with np.errstate(divide="ignore"):
            im = a.imshow(np.log10(pair), origin="lower", extent=[0.5, nch + 0.5, 0.5, nch + 0.5], interpolation="nearest")
        fig.colorbar(im, ax=a, label="log10 rate [Hz]"); a.set_xlabel("SADC channel"); a.set_ylabel("SADC channel")
        a.set_title("channels over threshold together (multiplicity >= 2)")
        a = ax[1, 2]
        pm = np.array([summ[s]["sadc"]["ped_mean"] for s in good if "sadc" in summ[s]])
        pr = np.array([summ[s]["sadc"]["ped_rms"] for s in good if "sadc" in summ[s]])
        a.errorbar(np.arange(1, nch + 1), np.median(pm, axis=0), yerr=np.median(pr, axis=0), fmt="o", ms=3, label="median over sub-runs (bar: rms)")
        a.plot(np.arange(1, nch + 1), pm.max(axis=0), "_", color="r", label="max over sub-runs")
        a.plot(np.arange(1, nch + 1), pm.min(axis=0), "_", color="b", label="min over sub-runs")
        a.set_xlabel("SADC channel"); a.set_ylabel("ADC of channels under threshold"); a.legend(fontsize=8)
        a.set_title("SADC baseline")
        fig.suptitle(title + "  -  veto (SADC)"); fig.tight_layout()
        fig.savefig(os.path.join(out, "veto.png"), dpi=80); plt.close(fig)
        pages.append("veto.png")

    # ---------------- prompt time correlations
    if has_fadc and pairs:
        rate_f = (np.nansum(et_n["1"]) + np.nansum(et_n["3"])) / livetime
        fig, ax = plt.subplots(2, 2, figsize=(15, 10))
        a = ax[0, 0]
        h = _sum_hist(summ, "dt_prev_fadc", "fadc")
        n_tot = h.sum()
        exp = n_tot * (np.exp(-rate_f * DT_EDGES[:-1] * 1e-6) - np.exp(-rate_f * DT_EDGES[1:] * 1e-6))
        a.step(_centers(DT_EDGES), h, where="mid", label="data")
        a.plot(_centers(DT_EDGES), exp, "k--", lw=0.8, label=f"uncorrelated, {rate_f:.1f} Hz")
        a.set_xscale("log"); a.set_yscale("log"); a.set_ylim(0.5, None); a.set_xlabel("time since previous FADC trigger [us]")
        for x in PAIR_WINDOW:
            a.axvline(x, color="grey", ls=":")
        a.set_title("FADC trigger spacing"); a.legend(fontsize=8)
        w = (DT_EDGES[:-1] >= PAIR_WINDOW[0]) & (DT_EDGES[1:] <= PAIR_WINDOW[1])
        row["pairs_excess_per_day"] = float((h[w].sum() - exp[w].sum()) / livetime * 86400)
        row["pairs_excess_sigma"] = float((h[w].sum() - exp[w].sum()) / np.sqrt(max(exp[w].sum(), 1)))
        a = ax[0, 1]
        hm = _sum_hist(summ, "dt_prev_muon", "fadc")
        if hm is not None and hm.sum():
            a.step(_centers(DT_EDGES), hm / np.diff(DT_EDGES), where="mid")
            a.set_xscale("log"); a.set_yscale("log")
        a.set_xlabel("time since previous FADC+SADC entry (muon-like) [us]"); a.set_ylabel("per us")
        a.set_title(f"after muon-like entries ({np.nansum(et_n['3']) / livetime:.2f} Hz)")
        # delayed pairs from the FADC table
        cols = prompt.read_fadc(run, base, ["SubRun", "EventType", "T", "Qgm", "NVeto", "DtPrevFADC", "DtPrevMuon"])
        if cols:
            order = np.lexsort((cols["T"], cols["SubRun"]))
            cols = {k: v[order] for k, v in cols.items()}
            dtp = cols["DtPrevFADC"]
            same = np.r_[False, cols["SubRun"][1:] == cols["SubRun"][:-1]]
            qprev = np.r_[np.nan, cols["Qgm"][:-1]]
            vprev = np.r_[0, cols["NVeto"][:-1]]
            mu_ok = (cols["DtPrevMuon"] < 0) | (cols["DtPrevMuon"] > MUON_VETO_US)
            cand = same & (dtp >= PAIR_WINDOW[0]) & (dtp <= PAIR_WINDOW[1]) & (cols["NVeto"] == 0) & (vprev == 0) & mu_ok
            a = ax[1, 0]
            if cand.any():
                hh = a.hist2d(np.log10(np.clip(qprev[cand], 1, None)), np.log10(np.clip(cols["Qgm"][cand], 1, None)),
                              bins=60, range=[[2, 6], [2, 6]], cmin=1)
                fig.colorbar(hh[3], ax=a)
            a.set_xlabel("log10 Qgm of the earlier trigger (prompt)"); a.set_ylabel("log10 Qgm of the later trigger (delayed)")
            a.set_title(f"pairs {PAIR_WINDOW[0]:.0f}-{PAIR_WINDOW[1]:.0f} us, no veto hit, > {MUON_VETO_US:.0f} us after muon: {cand.sum()}")
            a = ax[1, 1]
            # pair rate per sub-run
            sub_c = np.bincount(cols["SubRun"][cand], minlength=max(subs) + 1)
            y = np.array([sub_c[s] / summ[s]["duration"] if s in good and summ[s]["duration"] else np.nan for s in subs]) * 86400
            a.plot(tmid, y, ".", ms=3)
            a.set_xlabel("hours since run start"); a.set_ylabel("pair candidates per day")
            a.set_title("pair candidate rate per sub-run (not background-subtracted)")
            row["pairs_per_day"] = float(cand.sum() / livetime * 86400)
        fig.suptitle(title + "  -  prompt time correlations"); fig.tight_layout()
        fig.savefig(os.path.join(out, "prompt.png"), dpi=80); plt.close(fig)
        pages.append("prompt.png")

    # settings compared with the previous run that has a DQM summary
    prev = _previous_summary(run, base)
    if prev:
        changes = []
        for key in ("f_thr", "board_ped_0", "board_ped_1", "sadc_thr", "sadc_pmt_id", "config"):
            if key in prev and key in row and prev[key] != row[key]:
                changes.append(key)
        row["changed_since"] = {"run": prev["run"], "keys": changes}
        if changes:
            flags.append(f"settings changed since run {prev['run']}: {', '.join(changes)}")

    # ---------------- overview
    fig, ax = plt.subplots(2, 2, figsize=(16, 9))
    a = ax[0, 0]
    for k, lab in (("1", "FADC only"), ("2", "SADC only"), ("3", "FADC + SADC")):
        if np.nansum(et_n[k]) > 0:
            a.plot(tmid, et_rate[k], ".-", ms=3, lw=0.6, label=f"{lab}: {np.nansum(et_n[k]) / livetime:.1f} Hz")
    a.set_yscale("log"); a.set_xlabel("hours since run start"); a.set_ylabel("rate per sub-run [Hz]")
    a.set_title("trigger rates")
    if a.get_legend_handles_labels()[0]:
        a.legend(fontsize=8)
    a = ax[0, 1]
    # 1 s resolution of the total rate: spikes and dead periods
    xs, ys = [], []
    for s in good:
        r = np.sum([np.asarray(summ[s]["rate_1s"][k]) for k in ("1", "2", "3")], axis=0)
        r = r[:int(summ[s]["duration"])]             # drop the partial last second
        xs.append((start[s] + np.arange(len(r)) + 0.5) / 3600); ys.append(r)
    if xs:
        x, y = np.concatenate(xs), np.concatenate(ys)
        a.plot(x, y, lw=0.3, color="k")
        a.set_yscale("symlog", linthresh=1)
        zero = (y == 0).sum()
        a.set_title(f"all triggers per 1 s ({zero} empty seconds)")
    a.set_xlabel("hours since run start"); a.set_ylabel("triggers / s")
    a = ax[1, 0]
    a.plot(tmid, max_gap, ".", ms=3, label="largest gap between entries [s]")
    a.plot(tmid, per_sub(lambda x: x["trgnum_skip"]) / np.maximum(per_sub(lambda x: x["n_read"]), 1), ".", ms=3,
           label="TrgNum skipped / entries")
    a.plot(tmid, back, "x", ms=4, label="out-of-order entries")
    for s in errors:
        a.axvline(start[s] / 3600, color="r", lw=0.8)
    a.set_yscale("symlog", linthresh=1e-3); a.set_xlabel("hours since run start"); a.legend(fontsize=8)
    a.set_title("clock and trigger-number checks (red: unreadable sub-run)")
    a = ax[1, 1]; a.axis("off")
    txt = [f"run {run}", f"start {info.get('stime')}  end {info.get('etime')}",
           f"config {os.path.basename(info.get('config') or '')}",
           f"desc {(info.get('rundesc') or '').replace(chr(10), ' ')[:90]}",
           f"run sheet: dataset {sh.get('dataset', '-')}, type {sh.get('type', '-')}, source {sh.get('source', '-')}, "
           f"detector {sh.get('Detector', '-')}",
           f"PRD sub-runs {len(prd_subs)}, processed {len(subs)}, unreadable {len(errors)}",
           f"TCB livetime {livetime:.0f} s ({livetime / 3600:.2f} h), catalog tfadc {info.get('tfadc')}",
           f"entries {int(np.nansum(per_sub(lambda x: x['n_read'])))}, catalog nfadc {info.get('nfadc')} nsadc {info.get('nsadc')}",
           f"FADC+SADC entries: A AND B {row.get('rate_both_ab', 0):.2f} Hz, one channel only {row.get('rate_both_single', 0):.2f} Hz",
           f"min entry spacing {row.get('dt_min_us')} us, dead fraction ~{100 * (row.get('dead_frac_est') or 0):.2f}%, "
           f"skipped TrgNum {100 * row.get('trgnum_skip_frac', 0):.2f}% of entries",
           "", "flags:"] + ([f"  - {f}" for f in flags] or ["  none"])
    a.text(0, 1, "\n".join(txt), va="top", family="monospace", fontsize=9, wrap=True)
    fig.suptitle(title); fig.tight_layout(); fig.savefig(os.path.join(out, "overview.png"), dpi=80); plt.close(fig)

    pages.insert(0, "overview.png")

    row["flags"] = flags
    row["n_flags"] = len(flags)
    with open(os.path.join(out, "summary.json"), "w") as fh:
        json.dump(row, fh, indent=1, default=float)
    _run_html(out, run, info, row, flags, pages)
    return row


def _run_html(out, run, info, row, flags, pages):
    items = "".join(f"<li>{html.escape(f)}</li>" for f in flags) or "<li>none</li>"
    keys = [k for k in row if k not in ("flags", "veto_rate_by_ch", "rundesc")]
    tab = "".join(f"<tr><td>{k}</td><td>{html.escape(_fmt(row[k]))}</td></tr>" for k in keys)
    imgs = "".join(f'<p><a href="{p}"><img src="{p}" style="max-width:100%"></a></p>' for p in pages)
    with open(os.path.join(out, "index.html"), "w") as fh:
        fh.write(f"""<!doctype html><meta charset="utf-8"><title>RENE DQM run {run}</title>
<body style="font-family:sans-serif;margin:16px"><p><a href="../index.html">all runs</a></p>
<h2>Run {run}</h2><p>{html.escape((info.get('rundesc') or '').strip())}</p>
<h3>Flags</h3><ul>{items}</ul><h3>Numbers</h3><table border=1 cellpadding=3 style="border-collapse:collapse">{tab}</table>
{imgs}</body>""")


def _fmt(v):
    if isinstance(v, float):
        return f"{v:.4g}"
    return str(v)


TREND_KEYS = ["dataset", "type", "source", "livetime", "rate_both_ab", "rate_both_single", "dead_frac_est", "trgnum_skip_frac", "rate_fadc_only", "rate_both", "rate_sadc_only", "veto_rate_total",
              "ped_median_0", "ped_median_1", "pedrms_median_0", "pedrms_median_1",
              "peak_median_0", "peak_median_1", "qsum_median_0", "qsum_median_1", "qgm_median",
              "log_ab_median", "pedeo_median_0", "pedeo_median_1", "rise_median_0", "rise_median_1",
              "width_median_0", "width_median_1", "prepulse_frac_0", "prepulse_frac_1",
              "spe_pc_0", "spe_pc_1", "effthr_even_0", "effthr_odd_0", "effthr_even_1", "effthr_odd_1",
              "eo_mean_0", "eo_mean_1", "eo_jitter_0", "eo_jitter_1", "slot8_62.5_0", "slot8_125_0", "slot8_187.5_0",
              "slot8_62.5_1", "slot8_125_1", "slot8_187.5_1", "sat_frac_0", "sat_frac_1", "pairs_per_day", "pairs_excess_per_day", "n_error", "n_flags"]


def trend(base=None):
    rows = []
    for fn in sorted(glob.glob(os.path.join(dqm_dir(None, base), "*", "summary.json"))):
        with open(fn) as fh:
            rows.append(json.load(fh))
    if not rows:
        raise FileNotFoundError("no run summaries yet")
    d = dqm_dir(None, base)
    with open(os.path.join(d, "trend.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        head = ["run", "stime", "config"] + TREND_KEYS
        w.writerow(head)
        for r in rows:
            w.writerow([r.get(k) for k in head])

    def when(r):
        try:
            return dt.datetime.fromisoformat(str(r["stime"]))
        except (TypeError, ValueError):
            return None
    x = [when(r) or r["run"] for r in rows]
    panels = [("trigger rates [Hz]", ["rate_fadc_only", "rate_both", "rate_sadc_only", "veto_rate_total"], True),
              ("FADC pedestal median [ADC]", ["ped_median_0", "ped_median_1"], False),
              ("FADC pedestal rms [ADC]", ["pedrms_median_0", "pedrms_median_1"], False),
              ("pulse peak sample", ["peak_median_0", "peak_median_1"], False),
              ("Qsum median", ["qsum_median_0", "qsum_median_1", "qgm_median"], True),
              ("median log10(A/B)", ["log_ab_median"], False),
              ("even - odd offset [ADC] / random noise", ["pedeo_median_0", "pedeo_median_1", "pedrms_median_0", "pedrms_median_1"], False),
              ("pulse rise [samples] / Qsum/height", ["rise_median_0", "rise_median_1", "width_median_0", "width_median_1"], False),
              ("single p.e. peak [pC] (in situ)", ["spe_pc_0", "spe_pc_1"], False),
              ("even - odd offset [ADC] (run median)", ["eo_mean_0", "eo_mean_1"], False),
              ("8-sample clock pattern [ADC]", ["slot8_62.5_0", "slot8_125_0", "slot8_187.5_0", "slot8_62.5_1", "slot8_125_1", "slot8_187.5_1"], False),
              ("effective threshold [ADC]", ["effthr_even_0", "effthr_odd_0", "effthr_even_1", "effthr_odd_1"], False),
              ("saturated fraction", ["sat_frac_0", "sat_frac_1"], False),
              ("delayed pairs per day", ["pairs_per_day", "pairs_excess_per_day"], False),
              ("livetime [h] / flags", ["livetime", "n_flags"], False)]
    fig, ax = plt.subplots(6, 3, figsize=(18, 23), sharex=True)
    for a, (t, keys, logy) in zip(ax.flat, panels):
        for k in keys:
            y = np.array([r.get(k, np.nan) if r.get(k) is not None else np.nan for r in rows], float)
            if k == "livetime":
                y = y / 3600
            a.plot(x, y, ".", label=k)
        a.set_title(t); a.legend(fontsize=7)
        if logy:
            a.set_yscale("log")
    for a in ax[-1]:
        a.tick_params(axis="x", rotation=30)
    fig.tight_layout(); fig.savefig(os.path.join(d, "trend.png"), dpi=80); plt.close(fig)

    lines = "".join(
        f"<tr><td><a href='{r['run']:06d}/index.html'>{r['run']}</a></td><td>{html.escape(str(r.get('stime')))}</td>"
        f"<td>{html.escape((r.get('dataset') or '') + ' ' + (r.get('source') or ''))}</td><td>{html.escape(r.get('config', ''))}</td><td>{r.get('livetime', 0) / 3600:.2f}</td>"
        f"<td>{r.get('rate_fadc_only', 0) + r.get('rate_both', 0):.1f}</td><td>{r.get('veto_rate_total', 0) or 0:.0f}</td>"
        f"<td style='color:{'red' if r.get('flags') else 'green'}'>{html.escape('; '.join(r.get('flags', [])) or 'ok')}</td></tr>"
        for r in sorted(rows, key=lambda r: -r["run"]))
    with open(os.path.join(d, "index.html"), "w") as fh:
        fh.write(f"""<!doctype html><meta charset="utf-8"><title>RENE DQM</title>
<body style="font-family:sans-serif;margin:16px"><h2>RENE data quality</h2>
<p><a href="trend.png"><img src="trend.png" style="max-width:100%"></a></p>
<table border=1 cellpadding=3 style="border-collapse:collapse"><tr><th>run</th><th>start</th><th>dataset / source</th><th>config</th>
<th>livetime [h]</th><th>FADC rate [Hz]</th><th>veto hit rate [Hz]</th><th>flags</th></tr>{lines}</table></body>""")
    return rows
