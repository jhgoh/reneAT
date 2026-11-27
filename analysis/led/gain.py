#!/usr/bin/env python3
"""LED runs: PMT gain vs HV (prompt analysis, commissioning stage 2).

Step 1 (extract): for every LED run of a dataset (run sheet type "LED"), charge in the LED window and in an
empty window of the same length, per channel, from the first PRD file of the run.
Step 2 (fit):
  - LED(spe) runs: direct fit of pedestal + Poisson sum of Gaussian p.e. peaks -> SPE charge and width.
  - LED(~10pe), LED(6-38) runs: photostatistics,
        n_pe = mean^2 / (var - var_ped) * (1 + r^2),   gain = (var - var_ped) / mean / (1 + r^2),
    r = SPE relative width from the direct fits at HV >= 2000 V.
  - G = k HV^beta fitted per PMT; gain at the operating HV.

Run after `source reneAT/setup.sh`:
    analysis/led/gain.py --dataset Y2026A --out DIR            # extract (cached in DIR/led_charges.json) + fit
    analysis/led/gain.py --dataset Y2026A --out DIR --refit    # fit only, from the cached charges
Outputs in DIR: led_charges.json, led_gain.json (result), spe_fits.png, gain_vs_hv.png.

Window settings are for the Y2026A LED configuration (LED_PMT_gain_check.config: 1008-sample records,
LED-synchronous trigger on FADC ch3, LED pulse near sample 366). Check them before using another dataset.
"""
import argparse, json, os, sys
from concurrent.futures import ProcessPoolExecutor
import numpy as np

SIG, PED = (340, 420), (100, 180)                # LED window, empty window [samples]; even length, even start
PARITY_PED = 200                                 # per-parity baseline from samples [0, 200)
PC_PER_ADC_SAMPLE = 0.488e-3 * 2e-9 / 50 * 1e12  # 2 V / 4096 counts, 2 ns, 50 ohm -> pC
E_PC = 1.602176634e-7                            # electron charge [pC]
EDGES = np.arange(-500, 3001, 10.0)              # charge histogram [ADC x sample]
PHOTOSTAT_SOURCES = ("LED(~10pe)", "LED(6-38)")
SPE_SOURCE = "LED(spe)"
MIN_NPE = 3                                      # photostatistics only where the LED gives >= 3 p.e.


def extract_run(args):
    run, nmax = args
    import uproot, prd, runsheet
    x = runsheet.RunSheet()[run]
    out = {"run": run, "source": x["source"], "hv": [float(x["PMT-A HV (V)"]), float(x["PMT-B HV (V)"])]}
    try:
        a = uproot.open(prd.run_files(run)[0])["Event"].arrays(["F_Waveform_0", "F_Waveform_1"], entry_stop=nmax)
    except Exception as e:
        out["error"] = str(e)[:120]
        return out
    for c in (0, 1):
        w = prd.waveform(a, c)
        n = w.shape[1]
        pe, po = np.median(w[:, 0:PARITY_PED:2], 1), np.median(w[:, 1:PARITY_PED:2], 1)
        ws = w - np.where((np.arange(n) % 2 == 0)[None], pe[:, None], po[:, None])
        q, q0 = ws[:, SIG[0]:SIG[1]].sum(1), ws[:, PED[0]:PED[1]].sum(1)
        mad = np.median(np.abs(q0 - np.median(q0)))
        ok = np.abs(q0 - np.median(q0)) < 6 * 1.4826 * mad          # drop records with a pulse in the empty window
        q, q0 = q[ok], q0[ok]
        out[str(c)] = {"n": int(ok.sum()), "mean": float(q.mean() - q0.mean()), "var": float(q.var()),
                       "var0": float(q0.var()), "hist": np.histogram(q, EDGES)[0].tolist(),
                       "hist0": np.histogram(q0, EDGES)[0].tolist()}
    return out


def extract(dataset, jobs, nmax):
    import runsheet
    sh = runsheet.RunSheet()
    runs = [r for r in sh.runs(dataset=dataset) if sh[r]["type"] == "LED"]
    with ProcessPoolExecutor(jobs) as ex:
        return list(ex.map(extract_run, [(r, nmax) for r in runs]))


def _spe_model(x, N, mu, q0, s0, q1, s1):
    from scipy.stats import poisson
    y = np.zeros_like(x)
    for k in range(5):
        s = np.sqrt(s0 ** 2 + k * s1 ** 2)
        y += poisson.pmf(k, mu) * np.exp(-0.5 * ((x - q0 - k * q1) / s) ** 2) / s
    return N * (EDGES[1] - EDGES[0]) * y / np.sqrt(2 * np.pi)


def fit(rows, op_hv, outdir):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from scipy.optimize import curve_fit
    d = [r for r in rows if "error" not in r]
    x = 0.5 * (EDGES[1:] + EDGES[:-1])
    res = {"n_runs": len(rows), "n_errors": len(rows) - len(d), "windows": {"led": SIG, "empty": PED},
           "pc_per_adc_sample": PC_PER_ADC_SAMPLE, "pmt": {}}
    spe = {}
    fig, ax = plt.subplots(2, 4, figsize=(20, 8))
    for c in (0, 1):
        rs = sorted([r for r in d if r["source"] == SPE_SOURCE], key=lambda r: r["hv"][c])
        for r in rs:
            hv, h = r["hv"][c], np.array(r[str(c)]["hist"], float)
            s0g, q1g = np.sqrt(r[str(c)]["var0"]), max(30, 0.5 * 1e6 * E_PC / PC_PER_ADC_SAMPLE * (hv / 1700) ** 7 * 6.9)
            try:
                p, cov = curve_fit(_spe_model, x, h, p0=[h.sum(), 0.2, 0, s0g, q1g, 0.4 * q1g],
                                   bounds=([0, 0, -50, 1, 5, 1], [10 * h.sum(), 3, 50, 500, 3000, 3000]), maxfev=20000)
                spe[(c, hv)] = {"q1": p[4], "s1": p[5], "mu": p[1], "q1_err": float(np.sqrt(cov[4, 4]))}
            except Exception:
                pass
        for j, hv in enumerate((1700, 2000, 2200, 2500)):
            r = [r for r in rs if r["hv"][c] == hv]
            if not r:
                continue
            a = ax[c, j]
            a.step(x, r[0][str(c)]["hist"], where="mid", color="k")
            if (c, hv) in spe:
                f = spe[(c, hv)]
                a.plot(x, _spe_model(x, sum(r[0][str(c)]["hist"]), f["mu"], 0, np.sqrt(r[0][str(c)]["var0"]), f["q1"], f["s1"]),
                       "r-", lw=0.8)
                a.set_title(f"PMT {'AB'[c]} {hv:.0f} V: SPE {f['q1'] * PC_PER_ADC_SAMPLE:.2f} pC, "
                            f"rel. width {f['s1'] / f['q1']:.2f}, mu {f['mu']:.2f}")
            a.set_yscale("log"); a.set_xlim(-200, 1500); a.set_ylim(0.5, None)
            a.set_xlabel("charge in LED window [ADC x sample]")
    fig.tight_layout(); fig.savefig(os.path.join(outdir, "spe_fits.png"), dpi=70); plt.close(fig)

    fig, ax = plt.subplots(1, 2, figsize=(15, 5.5))
    for c in (0, 1):
        r_w = float(np.median([v["s1"] / v["q1"] for (cc, hv), v in spe.items() if cc == c and hv >= 2000]))
        pts = []
        for r in d:
            if r["source"] not in PHOTOSTAT_SOURCES:
                continue
            m, dv = r[str(c)]["mean"], r[str(c)]["var"] - r[str(c)]["var0"]
            if m <= 0 or dv <= 0 or m ** 2 / dv * (1 + r_w ** 2) < MIN_NPE:
                continue
            pts.append((r["hv"][c], dv / m / (1 + r_w ** 2) * PC_PER_ADC_SAMPLE / E_PC, r["source"], r["run"]))
        hv = np.array([p[0] for p in pts]); g = np.array([p[1] for p in pts])
        beta, lnk = np.polyfit(np.log(hv), np.log(g), 1)
        g_op = float(np.exp(lnk) * op_hv[c] ** beta)
        for src, mk in zip(PHOTOSTAT_SOURCES, "os"):
            s = [p for p in pts if p[2] == src]
            ax[c].plot([p[0] for p in s], [p[1] for p in s], mk, ms=4, label=f"photostatistics {src}")
        hh = np.linspace(hv.min() - 50, hv.max() + 50, 100)
        ax[c].plot(hh, np.exp(lnk) * hh ** beta, "k-", lw=0.8, label=f"G = k HV^{beta:.2f}")
        sv = sorted((hv_, v["q1"] * PC_PER_ADC_SAMPLE / E_PC) for (cc, hv_), v in spe.items() if cc == c)
        ax[c].plot([v[0] for v in sv], [v[1] for v in sv], "r^", ms=6, label="SPE peak fit (LED spe)")
        ax[c].axvline(op_hv[c], color="grey", ls=":")
        ax[c].set_title(f"PMT {'AB'[c]}: gain at {op_hv[c]:.0f} V = {g_op / 1e6:.2f}e6 ({g_op * E_PC:.2f} pC)")
        ax[c].set_yscale("log"); ax[c].set_xlabel("HV [V]"); ax[c].set_ylabel("gain"); ax[c].legend(fontsize=8)
        res["pmt"]["AB"[c]] = {
            "beta": float(beta), "ln_k": float(lnk), "op_hv": op_hv[c], "gain_op": g_op, "spe_pc_op": g_op * E_PC,
            "spe_rel_width": r_w, "n_photostat_runs": len(pts),
            "spe_fits": [{"hv": hv_, "spe_pc": v["q1"] * PC_PER_ADC_SAMPLE, "rel_width": v["s1"] / v["q1"], "mu": v["mu"]}
                         for (cc, hv_), v in sorted(spe.items()) if cc == c]}
    fig.tight_layout(); fig.savefig(os.path.join(outdir, "gain_vs_hv.png"), dpi=80); plt.close(fig)
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dataset", default="Y2026A", help="run-sheet dataset with the LED runs (default Y2026A)")
    ap.add_argument("--out", required=True, help="output directory")
    ap.add_argument("--op-hv", type=float, nargs=2, default=[1680.0, 1642.0], metavar=("A", "B"),
                    help="operating HV of PMT A, B [V] (default: physics-run settings 1680 1642)")
    ap.add_argument("--jobs", type=int, default=16)
    ap.add_argument("--nmax", type=int, default=30000, help="records read per run (first PRD file)")
    ap.add_argument("--refit", action="store_true", help="skip extraction, use DIR/led_charges.json")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    cache = os.path.join(a.out, "led_charges.json")
    if a.refit:
        rows = json.load(open(cache))
    else:
        rows = extract(a.dataset, a.jobs, a.nmax)
        json.dump(rows, open(cache, "w"))
    res = fit(rows, a.op_hv, a.out)
    res["dataset"] = a.dataset
    json.dump(res, open(os.path.join(a.out, "led_gain.json"), "w"), indent=1)
    for p, v in res["pmt"].items():
        print(f"PMT {p}: beta {v['beta']:.2f}, gain at {v['op_hv']:.0f} V = {v['gain_op'] / 1e6:.2f}e6 = {v['spe_pc_op']:.2f} pC,"
              f" SPE rel. width {v['spe_rel_width']:.2f}, {v['n_photostat_runs']} photostatistics runs")
    print(f"{res['n_runs']} runs, {res['n_errors']} unreadable")


if __name__ == "__main__":
    sys.exit(main())
