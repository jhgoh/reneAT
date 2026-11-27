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
                 dead_thr=1_000_000):     # Run-tree F_THR above this => channel disabled
        self.ped1, self.ped2 = ped1, ped2
        self.sig1, self.sig_len = sig1, sig_len
        self.sig2 = sig1 + sig_len
        self.tail_mode = tail_mode
        self.tail1, self.tail_off = tail1, tail_off
        self.fired_mode = fired_mode
        self.fired_nsigma = fired_nsigma
        self.dead_thr = dead_thr

    def as_dict(self):
        return {k: getattr(self, k) for k in
                ("ped1", "ped2", "sig1", "sig_len", "sig2", "tail_mode",
                 "tail1", "tail_off", "fired_mode", "fired_nsigma", "dead_thr")}


def compute_channel(wave, thr, cfg):
    """Vectorized QSUM for one channel.

    wave : (N, NDP) float array of raw ADC samples
    thr  : per-channel fixed threshold (ADC, used when fired_mode == "fixed")
    Returns dict of (N,) arrays: ped, ped_rms, qsum, qtail, rtail,
    fired (first sample over threshold, -1 if none), height (max of the
    pedestal-subtracted signal window) and peak (its sample index).
    """
    wave = np.asarray(wave, dtype=np.float64)

    ped = wave[:, cfg.ped1:cfg.ped2].mean(axis=1)
    ped_rms = wave[:, cfg.ped1:cfg.ped2].std(axis=1)

    w = wave - ped[:, None]                      # pedestal-subtracted

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

    return dict(ped=ped, ped_rms=ped_rms, qsum=qsum,
                qtail=qtail, rtail=rtail, fired=fired,
                height=height, peak=peak)


def active_channels(run_tree, cfg):
    """Return list of active FADC channel indices from the Run tree F_THR."""
    rin = run_tree.arrays(["F_THR", "F_PmtID"], library="np", entry_stop=1)
    thr = np.asarray(rin["F_THR"][0])
    pid = np.asarray(rin["F_PmtID"][0])
    act = [i for i in range(len(thr)) if thr[i] < cfg.dead_thr]
    return act, thr, pid
