"""
QSUM: pedestal subtraction + charge summation for the active FADC channels.

Ports the validated numeric algorithm of W.J. Lee's ChargeSum (Qsum / Qtail /
pedestal / fired-bin) to a vectorized uproot+numpy implementation. The two
active inner FADC channels are processed SEPARATELY (no summing); summing was
the first-version approach and is intentionally dropped so that downstream
vertex / energy-correction work keeps per-channel information.

No NPE/MeV conversion is applied here: calibration is still ongoing, so QSUM
stays calibration-free and emits raw-ADC Qsum/Qtail/Rtail. The conversion
belongs to a later RECO step that loads calibration constants externally.

Windows, threshold and tail definition are all configuration (not hardcoded),
so the window/offset/threshold scans needed to choose them are just repeated
runs with different config.
"""
import numpy as np


class QSumConfig:
    """All sample indices are in waveform-sample units (FADC: 2 ns/sample)."""

    def __init__(self,
                 ped1=0, ped2=100,        # pedestal window [ped1, ped2)
                 sig1=100, sig_len=250,   # signal window [sig1, sig1+sig_len)
                 tail_mode="fixed",       # "fixed": tail from tail1; "fired": from fired+tail_off
                 tail1=300, tail_off=15,
                 fired_mode="fixed",      # "fixed": (wave-ped) >= thr ; "nsigma": >= n*ped_rms
                 fired_nsigma=5.0,
                 ped_mode="parity",       # "parity": even and odd samples get their own pedestal; "single"
                 ped_reject=None,         # e.g. 4.0: drop pedestal samples > 4 sigma (MAD) from the median
                 dead_thr=1_000_000):     # Run-tree F_THR above this => channel disabled
        self.ped1, self.ped2 = ped1, ped2
        self.sig1, self.sig_len = sig1, sig_len
        self.sig2 = sig1 + sig_len
        self.tail_mode = tail_mode
        self.tail1, self.tail_off = tail1, tail_off
        self.fired_mode = fired_mode
        self.fired_nsigma = fired_nsigma
        self.ped_mode = ped_mode
        self.ped_reject = ped_reject
        self.dead_thr = dead_thr

    def as_dict(self):
        return {k: getattr(self, k) for k in
                ("ped1", "ped2", "sig1", "sig_len", "sig2", "tail_mode",
                 "tail1", "tail_off", "fired_mode", "fired_nsigma", "ped_mode", "ped_reject", "dead_thr")}


def _clipped_mean(x, k):
    """Per-row mean of the values within k * 1.4826 * MAD (>= 0.5) of the row median."""
    m = np.median(x, axis=1, keepdims=True)
    s = np.maximum(1.4826 * np.median(np.abs(x - m), axis=1, keepdims=True), 0.5)
    keep = np.abs(x - m) <= k * s
    return (x * keep).sum(axis=1) / np.maximum(keep.sum(axis=1), 1)


def compute_channel(wave, thr, cfg):
    """Vectorized QSUM for one channel.

    wave : (N, NDP) float array of raw ADC samples
    thr  : per-channel fixed threshold (ADC, used when fired_mode == "fixed")
    Returns dict of (N,) arrays: ped, ped_rms, ped_eo, qsum, qtail, rtail,
    fired (first sample over threshold, -1 if none), height (max of the
    pedestal-subtracted signal window) and peak (its sample index).

    The FADC writes even samples (0, 2, 4, ...) higher than odd ones by a fixed offset
    (PMT A about +1.5 to +5, B about +0.4 to +1.3 counts, from the two sample paths of the ADC).
    ped_mode "parity" takes a pedestal for even and one for odd samples in every event and
    subtracts each from its own samples; ped is their mean, ped_eo = even - odd, and ped_rms
    is the random noise left. Sums over windows of even length starting on an even sample
    (the default Qsum and Qtail windows) are the same in both modes. The offset is not an
    integer and changes between runs, within a run and from event to event, so it is taken
    from every event; the two sample paths have the same gain (even/odd charge ratio 1.000).

    ped_reject = k averages only the pedestal samples within k * 1.4826 * MAD (at least
    0.5 count) of their median, per parity, so that a stray pulse in the pedestal window does
    not pull the pedestal up. Use it for per-sample quantities on random or veto triggers
    (thresholds, single p.e.). For Qsum the plain mean is the better default: stray pulses
    come at a steady rate (e.g. ~MHz single p.e. from the Am-241 gammas of the AmBe source),
    so the plain mean also removes, on average, the pile-up they add to the signal window.
    ped_max is the largest excursion in the pedestal window above the pedestal (pile-up tag).
    """
    wave = np.asarray(wave, dtype=np.float64)

    pw = wave[:, cfg.ped1:cfg.ped2]
    avg = (lambda x: x.mean(axis=1)) if not cfg.ped_reject else (lambda x: _clipped_mean(x, cfg.ped_reject))
    if cfg.ped_mode == "parity":
        k = cfg.ped1 % 2                        # pw[:, k::2] are the even samples of the record
        pe, po = avg(pw[:, k::2]), avg(pw[:, 1 - k::2])
        even = (np.arange(wave.shape[1]) % 2 == 0)[None, :]
        pedv = np.where(even, pe[:, None], po[:, None])
        ped, ped_eo = 0.5 * (pe + po), pe - po
        ped_rms = (pw - pedv[:, cfg.ped1:cfg.ped2]).std(axis=1)
        ped_max = (pw - pedv[:, cfg.ped1:cfg.ped2]).max(axis=1)
        w = wave - pedv
    else:
        ped = avg(pw)
        ped_eo = pw[:, 0::2].mean(axis=1) - pw[:, 1::2].mean(axis=1)
        if cfg.ped1 % 2:
            ped_eo = -ped_eo
        ped_rms = pw.std(axis=1)
        ped_max = (pw - ped[:, None]).max(axis=1)
        w = wave - ped[:, None]                  # pedestal-subtracted

    qsum = w[:, cfg.sig1:cfg.sig2].sum(axis=1)

    # fired bin: first sample crossing the threshold (leading edge, WJ parity)
    if cfg.fired_mode == "nsigma":
        thr_arr = cfg.fired_nsigma * ped_rms     # per-event, data-driven
        over = w >= thr_arr[:, None]
    else:
        over = w >= float(thr)
    has = over.any(axis=1)
    fired = np.where(has, over.argmax(axis=1), -1)

    # tail window for PSD
    if cfg.tail_mode == "fired":
        t1 = fired + cfg.tail_off                # per-event, anchored to pulse start
        idx = np.arange(w.shape[1])[None, :]
        tail_mask = (idx >= t1[:, None]) & (idx < cfg.sig2) & (fired[:, None] >= 0)
        qtail = np.where(tail_mask, w, 0.0).sum(axis=1)
    else:
        qtail = w[:, cfg.tail1:cfg.sig2].sum(axis=1)

    rtail = np.divide(qtail, qsum, out=np.full_like(qsum, -1.0), where=qsum > 0)

    # pulse height and its sample inside the signal window
    ws = w[:, cfg.sig1:cfg.sig2]
    peak = ws.argmax(axis=1)
    height = np.take_along_axis(ws, peak[:, None], axis=1)[:, 0]
    peak = peak + cfg.sig1

    return dict(ped=ped, ped_rms=ped_rms, ped_eo=ped_eo, ped_max=ped_max, qsum=qsum,
                qtail=qtail, rtail=rtail, fired=fired,
                height=height, peak=peak)


def active_channels(run_tree, cfg):
    """Return list of active FADC channel indices from the Run tree F_THR."""
    rin = run_tree.arrays(["F_THR", "F_PmtID"], library="np", entry_stop=1)
    thr = np.asarray(rin["F_THR"][0])
    pid = np.asarray(rin["F_PmtID"][0])
    act = [i for i in range(len(thr)) if thr[i] < cfg.dead_thr]
    return act, thr, pid
