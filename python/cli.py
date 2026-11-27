"""
Command line entry point: ``reneat <command> ...``

    reneat ntuple 4185 -o data_4185.root [--max-events 400000]
    reneat ntuple 'mc/prd_src_Cs137_*.root' -o mc_Cs137.root
    reneat runs --source Cs137 --first 4100 --last 4240
    reneat source-compare --src data_4185.root --bkg data_4063.root --mc mc_Cs137.root \\
                          -o cs137.png            # fit window: auto, or --fit LO HI
"""
import argparse
import json
import sys

import numpy as np

import catalog, compare, ntuple
from qsum import QSumConfig


def _qsum_args(ap):
    g = ap.add_argument_group("QSUM definition (keep identical for data and MC)")
    g.add_argument("--ped1", type=int, default=0)
    g.add_argument("--ped2", type=int, default=100)
    g.add_argument("--sig1", type=int, default=100)
    g.add_argument("--sig-len", type=int, default=250)
    g.add_argument("--tail-mode", choices=["fixed", "fired"], default="fixed")
    g.add_argument("--tail1", type=int, default=300)
    g.add_argument("--tail-off", type=int, default=15)


def _qsum_cfg(a):
    return QSumConfig(ped1=a.ped1, ped2=a.ped2, sig1=a.sig1, sig_len=a.sig_len,
                      tail_mode=a.tail_mode, tail1=a.tail1, tail_off=a.tail_off)


def cmd_ntuple(a):
    t, m = ntuple.make(a.inputs, cfg=_qsum_cfg(a), max_events=a.max_events,
                       fadc_only=not a.all_events, verbose=not a.quiet)
    ntuple.save(a.output, t, m)
    norm = f"n_primary={m['n_primary']}" if m["is_mc"] else f"livetime={m['livetime']:.2f} s"
    print(f"[reneat] {m['n_trig']} triggers of {m['n_read']} entries, {norm} -> {a.output}")


def cmd_runs(a):
    cat = catalog.RunCatalog()
    for r in cat.runs(a.first, a.last, source=a.source, good_only=not a.include_bad):
        info = cat[r]
        print(f"{r:6d}  {cat.source(r) or '-':10s} {info['stime']}  nfadc={info['nfadc']}  "
              f"tfadc={info['tfadc']}  {'BAD:' + cat.badruns()[r] if cat.is_bad(r) else ''}")


def _load(path_or_run, cache, max_events):
    """An ntuple file, or a run number (built on the fly, cached as <cache>/data_<run>.root)."""
    import os
    if str(path_or_run).isdigit():
        out = os.path.join(cache, f"data_{int(path_or_run)}.root")
        if not os.path.exists(out):
            os.makedirs(cache, exist_ok=True)
            ntuple.save(out, *ntuple.make([int(path_or_run)], max_events=max_events, verbose=False))
        path_or_run = out
    return ntuple.load(path_or_run)


def cmd_overview(a):
    """One row per source: background-subtracted data vs MC as generated (no scale)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows = []
    for spec in a.set:
        if len(spec) not in (3, 4):
            sys.exit(f"--set LABEL SRC BKG [MC], got {spec}")
        label, s, b = spec[:3]
        src, ms = _load(s, a.cache, a.max_events)
        bkg, mb = _load(b, a.cache, a.max_events)
        mc = mm = None
        if len(spec) == 4 and spec[3] != "-":
            mc, mm = ntuple.load(spec[3])
            if ms["qsum_config"] != mm["qsum_config"]:
                sys.exit(f"{label}: QSUM definitions differ between data and MC")
        rows.append((label, s, b, src, ms, bkg, mb, mc, mm))

    colors = {0: "#2a6fdb", 1: "#e07b39"}
    norm_min = {}
    for x in a.norm_min or []:
        k, v = x.split("=")
        norm_min[k] = float(v)
    fig, ax = plt.subplots(len(rows), 3, figsize=(15, 3.6 * len(rows)), squeeze=False)
    summary = {}
    for i, (label, s, b, src, ms, bkg, mb, mc, mm) in enumerate(rows):
        logy = label in (a.logy or [])
        qmax = 1.3 * float(np.percentile(np.r_[src["Qsum_0"], src["Qsum_1"]], 99.5))
        bins = np.linspace(0, qmax, a.nbins + 1)
        cc = 0.5 * (bins[1:] + bins[:-1])
        summary[label] = {"livetime_src": ms["livetime"], "livetime_bkg": mb["livetime"]}
        rs = "+".join(ms.get("livetime_by_run", {})) or s
        rb_ = "+".join(mb.get("livetime_by_run", {})) or b
        for c in (0, 1):
            p = ax[i, c]
            h, e = compare.subtracted_rate(src, ms, bkg, mb, f"Qsum_{c}", bins)
            hb, _ = compare.rate_hist(bkg, mb, f"Qsum_{c}", bins)
            p.fill_between(cc, hb, step="mid", color="#bbb", alpha=0.6, lw=0, label=f"bkg run {rb_} ({mb['livetime']:.0f} s)")
            p.errorbar(cc, h, e, fmt="o", ms=2, color="#333", lw=0.7, label=f"run {rs} - bkg ({ms['livetime']:.0f} s)")
            summary[label][f"bkg_fraction_{'AB'[c]}"] = float(hb.sum() / (h.sum() + hb.sum()))
            summary[label][f"median_data_{'AB'[c]}"] = float(np.median(src[f"Qsum_{c}"]))
            if mc is not None:
                hm, _ = np.histogram(mc[f"Qsum_{c}"], bins)
                qn = norm_min.get(label, 0.0)          # area only: source activity is not used
                sel = cc >= qn
                norm = h[sel].sum() / max(hm[sel].sum(), 1)
                p.step(cc, hm * norm, where="mid", color=colors[c], lw=1.5,
                       label="MC as generated" + (f" (area Qsum>{qn:.0f})" if qn else " (area)"))
                if qn:
                    p.axvline(qn, color="#999", lw=0.8, ls="--")
                summary[label][f"median_mc_{'AB'[c]}"] = float(np.median(mc[f"Qsum_{c}"]))
            p.set(title=f"{label}: Qsum PMT {'AB'[c]}", xlabel="Qsum [ADC x sample]", ylabel="rate [Hz/bin]")
            if logy:
                p.set_yscale("log")
                p.set_ylim(bottom=max(1e-4, 0.5 * np.min(h[h > 0])) if (h > 0).any() else 1e-4)
            else:
                p.set_ylim(bottom=min(0, h.min() * 1.1))
            p.legend(fontsize=7)
        p = ax[i, 2]
        rb = np.linspace(-1.2, 1.2, 81)
        c2 = 0.5 * (rb[1:] + rb[:-1])
        hs, _ = np.histogram(compare.log_ratio(src), rb)
        hbk, _ = np.histogram(compare.log_ratio(bkg), rb)
        hd = hs / ms["livetime"] - hbk / mb["livetime"]
        p.step(c2, hd / hd.sum(), where="mid", color="#333", lw=1.4, label="data - bkg")
        if mc is not None:
            hmc, _ = np.histogram(compare.log_ratio(mc), rb)
            p.step(c2, hmc / hmc.sum(), where="mid", color=colors[0], lw=1.4, label="MC")
        p.set(title=f"{label}: A/B balance", xlabel="log10(Qsum A / Qsum B)", ylabel="fraction")
        p.legend(fontsize=7)
    fig.suptitle(a.title or "source runs vs MC as generated (no scale; MC normalised to the data area)", fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 1 - 0.45 / (3.6 * len(rows))))
    fig.savefig(a.output, dpi=110)
    print(json.dumps(summary, indent=1))
    print(f"[reneat] -> {a.output}")


def cmd_source_compare(a):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    src, ms = _load(a.src, a.cache, a.max_events)
    bkg, mb = _load(a.bkg, a.cache, a.max_events)
    mc, mm = ntuple.load(a.mc)
    if ms["qsum_config"] != mm["qsum_config"]:
        sys.exit(f"QSUM definitions differ:\n data {ms['qsum_config']}\n MC   {mm['qsum_config']}")

    qmax = a.qmax or 1.3 * float(np.percentile(np.r_[src["Qsum_0"], src["Qsum_1"]], 99.5))
    bins = np.linspace(0, qmax, a.nbins + 1)
    cc = 0.5 * (bins[1:] + bins[:-1])
    res = {}
    fig, ax = plt.subplots(2, 3, figsize=(14, 8.5))
    for col, (c, name, color) in enumerate(((0, "PMT A", "#2a6fdb"), (1, "PMT B", "#e07b39"))):
        h, e = compare.subtracted_rate(src, ms, bkg, mb, f"Qsum_{c}", bins)
        rng = a.fit or compare.auto_range(src[f"Qsum_{c}"])
        fit = compare.fit_scale(h, e, mc[f"Qsum_{c}"], bins, rng)
        fit["fit_range"] = list(rng)
        res[name] = {k: v for k, v in fit.items() if not k.startswith("scan")}
        hm, _ = np.histogram(mc[f"Qsum_{c}"] * fit["k"], bins)
        p = ax[0, col]
        p.errorbar(cc, h, e, fmt="o", ms=2.5, color="#555", lw=0.8, label="data - bkg")
        p.step(cc, hm * fit["norm"], where="mid", color=color, lw=1.6,
               label=f"MC x {fit['k']:.4f} ± {fit['k_err_scaled']:.4f}")
        p.axvspan(*rng, color="#ccc", alpha=0.3, lw=0)
        p.set(title=f"Qsum {name}", xlabel="Qsum [ADC x sample]", ylabel="rate [Hz/bin]")
        p.legend(fontsize=8)
        p = ax[1, col]
        o = np.argsort(fit["scan_k"])
        p.plot(fit["scan_k"][o], fit["scan_chi2"][o] - fit["chi2"], ".-", ms=3, color=color)
        p.set(ylim=(0, max(50, 0.3 * fit["chi2"])), xlim=(fit["k"] - 0.05, fit["k"] + 0.05), xlabel="MC scale k",
              ylabel="Δχ²", title=f"{name}: χ²/ndf = {fit['chi2']:.0f}/{fit['ndf']}")

    p = ax[0, 2]
    rb = np.linspace(-1.2, 1.2, 81)
    rd, rbk, rm = compare.log_ratio(src), compare.log_ratio(bkg), compare.log_ratio(mc)
    hs, _ = np.histogram(rd, rb); hb, _ = np.histogram(rbk, rb)
    hd = hs / ms["livetime"] - hb / mb["livetime"]
    hmc, _ = np.histogram(rm, rb)
    c2 = 0.5 * (rb[1:] + rb[:-1])
    p.step(c2, hd / hd.sum(), where="mid", color="#555", lw=1.5, label="data - bkg")
    p.step(c2, hmc / hmc.sum(), where="mid", color="#2a6fdb", lw=1.5, label="MC")
    md = float(np.sum(c2 * hd) / hd.sum()); mmc = float(np.mean(rm))
    p.set(title=f"A/B balance, means {md:+.3f} / {mmc:+.3f}", xlabel="log10(Qsum A / Qsum B)")
    p.legend(fontsize=8)
    res["log10(A/B) mean"] = {"data": md, "mc": mmc}

    if not a.no_pulse:
        p = ax[1, 2]
        for c, color in ((0, "#2a6fdb"), (1, "#e07b39")):
            td, yd, nd = compare.mean_pulse(ms["files"], c, *a.pulse_height)
            tm, ym, nm = compare.mean_pulse(mm["files"], c, *a.pulse_height)
            p.plot(td, yd, color=color, ls=":", label=f"data {'AB'[c]} ({nd}), FWHM {compare.fwhm(td, yd):.0f} ns")
            p.plot(tm, ym, color=color, label=f"MC {'AB'[c]} ({nm}), FWHM {compare.fwhm(tm, ym):.0f} ns")
            res[f"FWHM {'AB'[c]} [ns]"] = {"data": compare.fwhm(td, yd), "mc": compare.fwhm(tm, ym)}
        p.set(title=f"mean pulse, height {a.pulse_height[0]:.0f}-{a.pulse_height[1]:.0f}",
              xlabel="time from peak [ns]", ylabel="normalised")
        p.legend(fontsize=7)
    else:
        ax[1, 2].axis("off")

    fig.suptitle(a.title or f"source {ms['files'][0].split('/')[-1]} vs MC", fontsize=10)
    fig.tight_layout()
    fig.savefig(a.output, dpi=120)
    print(json.dumps(res, indent=1))
    print(f"[reneat] -> {a.output}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="reneat")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("ntuple", help="PRD (data runs or MC files) -> feature ntuple")
    p.add_argument("inputs", nargs="+", help="run numbers and/or PRD files (globs ok)")
    p.add_argument("-o", "--output", required=True, help=".root or .npz")
    p.add_argument("--max-events", type=int)
    p.add_argument("--all-events", action="store_true", help="keep SADC-only entries too")
    p.add_argument("-q", "--quiet", action="store_true")
    _qsum_args(p)
    p.set_defaults(func=cmd_ntuple)

    p = sub.add_parser("runs", help="list runs from the run catalog")
    p.add_argument("--first", type=int)
    p.add_argument("--last", type=int)
    p.add_argument("--source", help="Cs137, Co60, AmBe, Cf252, none, or e.g. Co60+AmBe")
    p.add_argument("--include-bad", action="store_true")
    p.set_defaults(func=cmd_runs)

    p = sub.add_parser("overview", help="several sources, data - bkg vs MC as generated (no fit)")
    p.add_argument("--set", nargs="+", action="append", required=True, metavar="ARG",
                   help="LABEL SRC BKG [MC]: SRC/BKG are ntuples or run numbers, MC an ntuple or '-' (repeat)")
    p.add_argument("--logy", nargs="*", metavar="LABEL", help="labels drawn with a log y axis")
    p.add_argument("--norm-min", nargs="*", metavar="LABEL=QSUM",
                   help="normalise the MC to the data area above this Qsum only (e.g. Cf252=20000)")
    p.add_argument("--nbins", type=int, default=120)
    p.add_argument("--cache", default=".", help="where run-number inputs are cached as ntuples")
    p.add_argument("--max-events", type=int, help="for run-number inputs")
    p.add_argument("--title")
    p.add_argument("-o", "--output", required=True)
    p.set_defaults(func=cmd_overview)

    p = sub.add_parser("source-compare", help="background-subtracted source run vs source MC")
    p.add_argument("--src", required=True, help="source-run ntuple or run number")
    p.add_argument("--bkg", required=True, help="background-run ntuple or run number")
    p.add_argument("--mc", required=True, help="MC ntuple")
    p.add_argument("--fit", type=float, nargs=2, metavar=("LO", "HI"),
                   help="Qsum fit range (default: 5-99 percentile of the source-run Qsum, per channel)")
    p.add_argument("--qmax", type=float, help="histogram upper edge (default: 1.3 x 99.5 percentile of source Qsum)")
    p.add_argument("--nbins", type=int, default=120)
    p.add_argument("--pulse-height", type=float, nargs=2, default=(150, 400))
    p.add_argument("--no-pulse", action="store_true")
    p.add_argument("--cache", default=".", help="where run-number inputs are cached as ntuples")
    p.add_argument("--max-events", type=int, help="for run-number inputs")
    p.add_argument("--title")
    p.add_argument("-o", "--output", required=True)
    p.set_defaults(func=cmd_source_compare)

    a = ap.parse_args(argv)
    a.func(a)


if __name__ == "__main__":
    main()
