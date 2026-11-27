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
from prompt import QSUM_EDGES, SADC_EDGES, DT_EDGES, PEAK_EDGES, PED_EDGES, RMS_EDGES

# prompt pair search (delayed = FADC trigger following another one), in us and Qgm
PAIR_WINDOW = (10.0, 200.0)    # starts after the retriggers that follow large pulses (< 10 us)
MUON_VETO_US = 1000.0
DEFAULT_FLAGS = {"max_gap_s": 1.0, "rate_drop": 0.5, "ped_shift": 3.0, "peak_shift": 5.0}


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
    row = {"run": run, "stime": info.get("stime"), "etime": info.get("etime"),
           "config": os.path.basename(info.get("config") or ""), "rundesc": (info.get("rundesc") or "").replace("\n", " ")[:200],
           "n_prd_subruns": len(prd_subs), "n_processed": len(subs), "n_error": len(errors),
           "livetime": livetime, "tfadc_catalog": info.get("tfadc"),
           "rate_fadc_only": float(np.nansum(et_n["1"]) / livetime) if livetime else 0.0,
           "rate_sadc_only": float(np.nansum(et_n["2"]) / livetime) if livetime else 0.0,
           "rate_both": float(np.nansum(et_n["3"]) / livetime) if livetime else 0.0}

    os.makedirs(dqm_dir(run, base), exist_ok=True)
    out = dqm_dir(run, base)
    title = f"Run {run}  {info.get('stime', '')}  {os.path.basename(info.get('config') or '')}"

    pages = []

    # ---------------- FADC
    if has_fadc:
        fig, ax = plt.subplots(3, 3, figsize=(17, 12))
        for c, col in ((0, "C0"), (1, "C3")):
            h = _sum_hist(summ, f"qsum_{c}", "fadc")
            ax[0, 0].step(_centers(QSUM_EDGES)[1:], (h / np.diff(QSUM_EDGES) / livetime)[1:], where="mid", color=col, label=f"PMT {'AB'[c]}")
            row[f"qsum_median_{c}"] = _median_from_hist(h, QSUM_EDGES)
            hp = _sum_hist(summ, f"peak_{c}", "fadc")
            ax[0, 2].step(_centers(PEAK_EDGES), hp, where="mid", color=col, label=f"PMT {'AB'[c]}: median {_median_from_hist(hp, PEAK_EDGES):.0f}")
            row[f"peak_median_{c}"] = _median_from_hist(hp, PEAK_EDGES)
            row[f"ped_median_{c}"] = float(np.nanmedian(per_sub(lambda x: x.get("fadc", {}).get(f"ped_median_{c}", np.nan))))
            row[f"pedrms_median_{c}"] = float(np.nanmedian(per_sub(lambda x: x.get("fadc", {}).get(f"pedrms_median_{c}", np.nan))))
            for (i, j), key, lab in (((1, 0), "ped_median", "pedestal median [ADC]"),
                                     ((1, 1), "pedrms_median", "pedestal rms median [ADC]"),
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
        for a in ax.flat:
            if a.get_legend_handles_labels()[0] and a.get_legend() is None:
                a.legend(fontsize=8)
        fig.suptitle(title + "  -  inner PMTs (FADC)"); fig.tight_layout()
        fig.savefig(os.path.join(out, "fadc.png"), dpi=80); plt.close(fig)
        pages.append("fadc.png")

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
           f"PRD sub-runs {len(prd_subs)}, processed {len(subs)}, unreadable {len(errors)}",
           f"TCB livetime {livetime:.0f} s ({livetime / 3600:.2f} h), catalog tfadc {info.get('tfadc')}",
           f"entries {int(np.nansum(per_sub(lambda x: x['n_read'])))}, catalog nfadc {info.get('nfadc')} nsadc {info.get('nsadc')}",
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


TREND_KEYS = ["livetime", "rate_fadc_only", "rate_both", "rate_sadc_only", "veto_rate_total",
              "ped_median_0", "ped_median_1", "pedrms_median_0", "pedrms_median_1",
              "peak_median_0", "peak_median_1", "qsum_median_0", "qsum_median_1", "qgm_median",
              "log_ab_median", "sat_frac_0", "sat_frac_1", "pairs_per_day", "pairs_excess_per_day", "n_error", "n_flags"]


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
              ("saturated fraction", ["sat_frac_0", "sat_frac_1"], False),
              ("delayed pairs per day", ["pairs_per_day", "pairs_excess_per_day"], False),
              ("livetime [h] / flags", ["livetime", "n_flags"], False)]
    fig, ax = plt.subplots(3, 3, figsize=(18, 12), sharex=True)
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
        f"<td>{html.escape(r.get('config', ''))}</td><td>{r.get('livetime', 0) / 3600:.2f}</td>"
        f"<td>{r.get('rate_fadc_only', 0) + r.get('rate_both', 0):.1f}</td><td>{r.get('veto_rate_total', 0) or 0:.0f}</td>"
        f"<td style='color:{'red' if r.get('flags') else 'green'}'>{html.escape('; '.join(r.get('flags', [])) or 'ok')}</td></tr>"
        for r in sorted(rows, key=lambda r: -r["run"]))
    with open(os.path.join(d, "index.html"), "w") as fh:
        fh.write(f"""<!doctype html><meta charset="utf-8"><title>RENE DQM</title>
<body style="font-family:sans-serif;margin:16px"><h2>RENE data quality</h2>
<p><a href="trend.png"><img src="trend.png" style="max-width:100%"></a></p>
<table border=1 cellpadding=3 style="border-collapse:collapse"><tr><th>run</th><th>start</th><th>config</th>
<th>livetime [h]</th><th>FADC rate [Hz]</th><th>veto hit rate [Hz]</th><th>flags</th></tr>{lines}</table></body>""")
    return rows
