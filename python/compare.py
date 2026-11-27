"""
Data vs MC comparison helpers on feature ntuples (``ntuple``).

    src, msrc = ntuple.load("data_4185.root"); bkg, mbkg = ntuple.load("data_4063.root")
    h, e = subtracted_rate(src, msrc, bkg, mbkg, "Qsum_0", bins)       # Hz per bin
    fit = fit_scale(h, e, mc["Qsum_0"], bins, (8e3, 4e4))               # MC charge scale k
"""
import numpy as np

import prd
from qsum import QSumConfig, compute_channel


def rate_hist(table, meta, key, bins, mask=None):
    """Histogram of a data ntuple column as rate [Hz per bin] with stat. error."""
    x = table[key] if mask is None else table[key][mask]
    h, _ = np.histogram(x, bins)
    live = float(meta["livetime"])
    return h / live, np.sqrt(h) / live


def subtracted_rate(src, msrc, bkg, mbkg, key, bins, mask_src=None, mask_bkg=None):
    """Source-run rate minus background-run rate, both normalised to livetime."""
    hs, es = rate_hist(src, msrc, key, bins, mask_src)
    hb, eb = rate_hist(bkg, mbkg, key, bins, mask_bkg)
    return hs - hb, np.hypot(es, eb)


def _scan(hdat, edat, xmc, bins, s, kgrid, min_frac):
    out = []
    for k in kgrid:
        hm, _ = np.histogram(xmc * k, bins)
        hm = hm.astype(float)
        if hm[s].sum() < min_frac * len(xmc) or hm[s].sum() <= 0:
            out.append((np.inf, np.nan))
            continue
        norm = hdat[s].sum() / hm[s].sum()
        var = edat[s] ** 2 + norm ** 2 * np.maximum(hm[s], 1)
        out.append((float(np.sum((hdat[s] - norm * hm[s]) ** 2 / var)), norm))
    chi2, norm = np.array(out).T
    return chi2, norm


def fit_scale(hdat, edat, xmc, bins, fit_range, kgrid=None, min_frac=0.3):
    """Fit a multiplicative scale k on MC values ``xmc`` to data ``hdat``.

    In ``fit_range`` the MC histogram of k*xmc is normalised to the data area
    and a chi2 with data and MC statistical errors is computed. A coarse scan
    is refined around its minimum and a parabola gives k and its error.

    Returns dict: k, k_err (dchi2 = 1), k_err_scaled (x sqrt(chi2/ndf), use
    this when the shapes do not agree), norm, chi2, ndf, and the scan.

    Scales that leave less than ``min_frac`` of the MC entries inside the
    window are skipped: otherwise the fit can push the MC out of the window,
    where a huge normalisation with huge MC errors gives a tiny chi2.
    """
    kgrid = np.linspace(0.2, 2.0, 361) if kgrid is None else np.asarray(kgrid)
    c = 0.5 * (bins[1:] + bins[:-1])
    s = (c > fit_range[0]) & (c < fit_range[1])
    chi2, _ = _scan(hdat, edat, xmc, bins, s, kgrid, min_frac)
    if not np.isfinite(chi2).any():
        raise ValueError(f"no scale puts {min_frac:.0%} of the MC inside {fit_range}; check the fit range")
    k0 = kgrid[np.argmin(chi2)]
    step = kgrid[1] - kgrid[0] if len(kgrid) > 1 else 0.01
    # The chi2 is jagged on a fine k grid (MC entries jump between bins), so the
    # parabola is fitted over a wide window rather than at the very minimum.
    fine = np.linspace(k0 - 10 * step, k0 + 10 * step, 201)
    fchi2, fnorm = _scan(hdat, edat, xmc, bins, s, fine, min_frac)
    cmin = np.nanmin(np.where(np.isfinite(fchi2), fchi2, np.nan))
    ok = np.isfinite(fchi2) & (fchi2 < cmin + max(25.0, 0.2 * cmin))
    a2, a1, a0 = np.polyfit(fine[ok], fchi2[ok], 2)
    ndf = int(s.sum()) - 2
    if a2 > 0:
        k = -a1 / (2 * a2)
        k_err = 1.0 / np.sqrt(a2)
        chi2_min = a0 - a1 ** 2 / (4 * a2)
    else:                       # flat or ill-defined: fall back to the scan minimum
        i = np.nanargmin(np.where(ok, fchi2, np.inf))
        k, k_err, chi2_min = fine[i], np.nan, fchi2[i]
    i = np.nanargmin(np.where(ok, fchi2, np.inf))
    return dict(k=float(k), k_err=float(k_err),
                k_err_scaled=float(k_err * np.sqrt(max(chi2_min / ndf, 1.0))) if ndf > 0 else np.nan,
                norm=float(fnorm[i]), chi2=float(chi2_min), ndf=ndf,
                scan_k=np.r_[kgrid, fine], scan_chi2=np.r_[chi2, fchi2])


def auto_range(x, lo_pct=5.0, hi_pct=99.0):
    """Fit window from percentiles of the (source-run) data values."""
    return tuple(float(v) for v in np.percentile(x, [lo_pct, hi_pct]))


def log_ratio(table, a="Qsum_0", b="Qsum_1"):
    """log10(a/b), e.g. the PMT A/B charge balance."""
    return np.log10(np.maximum(table[a], 1) / np.maximum(table[b], 1))


def mean_pulse(files, ch, hmin, hmax, cfg=None, max_events=50000, pre=20, post=80, fadc_only=True):
    """Peak-aligned mean pulse, normalised to the peak, for pulses with
    hmin < height < hmax (height as defined in compute_channel).

    Returns (t_ns relative to the peak, mean shape, number of pulses).
    """
    cfg = cfg or QSumConfig()
    acc, n = np.zeros(pre + post), 0
    for _, _, _, arr in prd.iterate(files, ["EventType", f"F_Waveform_{ch}"], entry_stop=max_events):
        et = np.asarray(arr["EventType"])
        sel = (et == prd.ET_FADC) | (et == prd.ET_BOTH) if fadc_only else np.ones(len(et), bool)
        if not sel.any():
            continue
        w = prd.waveform(arr[sel], ch)
        r = compute_channel(w, 1e9, cfg)
        ok = (r["height"] > hmin) & (r["height"] < hmax) & (r["peak"] >= pre) & (r["peak"] + post <= w.shape[1])
        if not ok.any():
            continue
        ws = w[ok] - r["ped"][ok, None]
        idx = r["peak"][ok, None] + np.arange(-pre, post)[None, :]
        seg = np.take_along_axis(ws, idx, axis=1)
        acc += (seg / r["height"][ok, None]).sum(axis=0)
        n += int(ok.sum())
    t = np.arange(-pre, post) * prd.SAMPLE_NS
    return t, (acc / n if n else acc), n


def fwhm(t, y):
    """Full width at half maximum of a peak-normalised shape (same unit as t)."""
    above = np.where(y >= 0.5 * y.max())[0]
    return float(t[above[-1]] - t[above[0]]) if len(above) else np.nan
