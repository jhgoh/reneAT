"""
Prompt processing: read every entry of a PRD sub-run once and keep what the
run-level data quality monitoring (dqm.py) and the prompt physics need.

One output file per sub-run, ``<out>/<run:06d>/prompt_<run:06d>.<sub:05d>.root``:

  tree ``FADC``   one row per FADC trigger (EventType 1 or 3):
                  SubRun, Entry, TrgNum, EventType, T [s since the first entry of the sub-run],
                  the QSum features of PMT A and B (``_0``, ``_1``; see ntuple.FEATURES),
                  Sat_c (waveform reaches the ADC limit), Qgm = sqrt(Qsum_0 * Qsum_1),
                  NVeto (SADC channels over threshold in the same entry),
                  FTrig_0/1 (FADC channel trigger bits; EventType 3 can have only one of them),
                  DtPrevFADC, DtPrevVeto, DtPrevMuon [us] to the previous FADC trigger,
                  the previous entry with any SADC channel over threshold, and the previous
                  EventType-3 entry (inner + veto) in the same sub-run; -1 if none yet.
  ``summary``     JSON (TObjString): entry counts, clock and trigger-number checks,
                  1 s rate histograms, FADC pedestal / pulse summaries and the SADC
                  (veto) per-channel counts, spectra, multiplicity and pair coincidences.

Data and renesim MC go through the same code (MC has no SADC hits).
"""
import json
import os
import time
import traceback

import awkward as ak
import numpy as np
import uproot

import prd
from ntuple import FEATURES, INT_FEATURES
from qsum import QSumConfig, compute_channel

PROMPT_BASE = os.environ.get("RENE_PROMPT")
ADC_MAX = 4095
# fixed binnings so that sub-run histograms can be summed
QSUM_EDGES = np.r_[0, np.geomspace(100, 1e6, 121)]        # FADC Qsum [ADC*sample]
SADC_EDGES = np.r_[0, np.geomspace(10, 1e5, 81)]          # SADC ADC
DT_EDGES = np.geomspace(0.1, 1e6, 141)                   # us
PEAK_EDGES = np.arange(0, 497)                           # sample
PED_EDGES = np.arange(-0.5, 400.5, 1.0)                   # ADC (inverted pedestal)
RMS_EDGES = np.linspace(0, 20, 201)
RISE_EDGES = np.arange(-0.5, 150.5, 1.0)                 # samples from leading edge to peak


def out_dir(base=None):
    base = base or PROMPT_BASE
    if not base:
        raise RuntimeError("set the output directory with --out or the RENE_PROMPT environment variable")
    return base


def output_path(run, sub, base=None):
    return os.path.join(out_dir(base), f"{run:06d}", f"prompt_{run:06d}.{sub:05d}.root")


def _hist(x, edges):
    return np.histogram(x, edges)[0].astype(np.int64)


def _dt_prev(t_all, mask_src, idx_dst):
    """For entries idx_dst: time [us] since the previous entry (strictly earlier index) in mask_src."""
    src = np.where(mask_src)[0]
    pos = np.searchsorted(src, idx_dst, side="left") - 1
    out = np.full(len(idx_dst), -1.0)
    ok = pos >= 0
    out[ok] = (t_all[idx_dst[ok]] - t_all[src[pos[ok]]]) * 1e-3
    return out


def process_subrun(fn, cfg=None, chunk=100_000, channels=(0, 1)):
    """Return (fadc_table, summary) for one PRD file."""
    cfg = cfg or QSumConfig()
    run = prd_run_of(fn)
    sub = prd.subrun_of(fn)
    t0 = time.time()
    summ = {"file": fn, "run": run, "subrun": sub, "error": None, "qsum_config": cfg.as_dict()}
    cols = {}

    try:
        f = uproot.open(fn)
        tree = f["Event"]
    except Exception as e:                      # unreadable / empty file
        summ["error"] = f"{type(e).__name__}: {e}"
        summ["proc_seconds"] = time.time() - t0
        return {}, summ

    n = tree.num_entries
    has_sadc = "S_Triggered" in tree
    has_ftrig = "F_Triggered" in tree
    base_br = (["TrgNum", "EventType", "TCBTRGTime"] + (["F_Triggered"] if has_ftrig else [])
               + (["S_Triggered", "S_ADC"] if has_sadc else []))
    clock = prd.TCBClock()
    pieces = {k: [] for k in ("trg", "et", "t", "nveto", "ftrig")}
    sadc = None
    try:
        first = tree.arrays(["F_THR"] + (["S_THR", "S_PmtID"] if has_sadc else []), entry_stop=1, library="ak")
        thr = ak.to_numpy(first["F_THR"][0]).astype(float) if n else np.full(4, 80.0)
        if has_sadc and n:
            s_thr = ak.to_numpy(first["S_THR"][0]).astype(int)
            s_pid = ak.to_numpy(first["S_PmtID"][0]).astype(int)
            nch = len(s_thr)
            sadc = {"thr": s_thr.tolist(), "pmt_id": s_pid.tolist(), "n_hit": np.zeros(nch, np.int64),
                    "adc_hit": np.zeros((nch, len(SADC_EDGES) - 1), np.int64),
                    "ped_sum": np.zeros(nch), "ped_sum2": np.zeros(nch), "ped_n": np.zeros(nch, np.int64),
                    "mult": np.zeros(nch + 1, np.int64), "pair": np.zeros((nch, nch), np.int64)}

        fadc_rows = []
        for start in range(0, n, chunk):
            stop = min(n, start + chunk)
            a = tree.arrays(base_br, entry_start=start, entry_stop=stop, library="ak")
            et = ak.to_numpy(a["EventType"]).astype(np.int32)
            pieces["trg"].append(ak.to_numpy(a["TrgNum"]).astype(np.int64))
            pieces["et"].append(et)
            pieces["t"].append(clock.times(ak.to_numpy(a["TCBTRGTime"])))
            if has_ftrig:
                pieces["ftrig"].append(ak.to_numpy(a["F_Triggered"])[:, :2].astype(np.int8))
            else:                                   # no trigger bits (old files): EventType 1/3 = both
                both = ((et == prd.ET_FADC) | (et == prd.ET_BOTH)).astype(np.int8)
                pieces["ftrig"].append(np.stack([both, both], axis=1))
            if sadc is not None:
                trig = ak.to_numpy(a["S_Triggered"]).astype(bool)
                adc = ak.to_numpy(a["S_ADC"]).astype(np.float64)
                nv = trig.sum(axis=1)
                pieces["nveto"].append(nv)
                sadc["n_hit"] += trig.sum(axis=0)
                for c in range(trig.shape[1]):
                    sadc["adc_hit"][c] += _hist(adc[trig[:, c], c], SADC_EDGES)
                q = np.where(trig, 0.0, adc)
                sadc["ped_sum"] += q.sum(axis=0)
                sadc["ped_sum2"] += (q * q).sum(axis=0)
                sadc["ped_n"] += (~trig).sum(axis=0)
                sadc["mult"] += np.bincount(nv, minlength=len(sadc["mult"]))[:len(sadc["mult"])]
                tt = trig[nv >= 2].astype(np.int64)
                sadc["pair"] += tt.T @ tt
            else:
                pieces["nveto"].append(np.zeros(len(et), np.int64))

            sel = np.where((et == prd.ET_FADC) | (et == prd.ET_BOTH))[0]
            if len(sel) == 0:
                continue
            # waveforms only for the entry range that holds FADC triggers
            w0, w1 = start + sel[0], start + sel[-1] + 1
            wa = tree.arrays([f"F_Waveform_{c}" for c in channels], entry_start=w0, entry_stop=w1, library="ak")
            row = {"Entry": start + sel}
            for c in channels:
                w = prd.waveform(wa, c)[sel - (w0 - start)]
                r = compute_channel(w, thr[c] if c < len(thr) else 80.0, cfg)
                for k, name in FEATURES.items():
                    row[f"{name}_{c}"] = r[k].astype(np.int32 if k in INT_FEATURES else np.float32)
                row[f"Sat_{c}"] = (w.max(axis=1) >= ADC_MAX).astype(np.int32)
            fadc_rows.append(row)
    except Exception as e:
        summ["error"] = f"{type(e).__name__}: {e}"
        summ["traceback"] = traceback.format_exc(limit=3)

    trg = np.concatenate(pieces["trg"]) if pieces["trg"] else np.zeros(0, np.int64)
    et = np.concatenate(pieces["et"]) if pieces["et"] else np.zeros(0, np.int32)
    t = np.concatenate(pieces["t"]) if pieces["t"] else np.zeros(0)
    nveto = np.concatenate(pieces["nveto"]) if pieces["nveto"] else np.zeros(0, np.int64)
    ftrig = np.concatenate(pieces["ftrig"]) if pieces["ftrig"] else np.zeros((0, 2), np.int8)
    n_read = len(et)

    # ---- FADC table with the time / veto context of each trigger
    if fadc_rows:
        for k in fadc_rows[0]:
            cols[k] = np.concatenate([r[k] for r in fadc_rows])
        idx = cols["Entry"]
        fadc_mask = (et == prd.ET_FADC) | (et == prd.ET_BOTH)
        cols = {"SubRun": np.full(len(idx), sub, np.int32), "Entry": idx.astype(np.int64),
                "TrgNum": trg[idx], "EventType": et[idx], "T": t[idx] * 1e-9,
                **{k: v for k, v in cols.items() if k != "Entry"}}
        cols["Qgm"] = np.sqrt(np.clip(cols["Qsum_0"], 0, None) * np.clip(cols["Qsum_1"], 0, None)).astype(np.float32)
        cols["NVeto"] = nveto[idx].astype(np.int32)
        cols["FTrig_0"] = ftrig[idx, 0].astype(np.int32)       # FADC channel trigger bits (F_Triggered)
        cols["FTrig_1"] = ftrig[idx, 1].astype(np.int32)
        cols["DtPrevFADC"] = _dt_prev(t, fadc_mask, idx).astype(np.float32)
        cols["DtPrevVeto"] = _dt_prev(t, nveto > 0, idx).astype(np.float32)
        cols["DtPrevMuon"] = _dt_prev(t, et == prd.ET_BOTH, idx).astype(np.float32)

    # ---- summary
    dur = float(t[-1] * 1e-9) if n_read else 0.0
    et_counts = {str(k): int(v) for k, v in zip(*np.unique(et, return_counts=True))}
    d_trg = np.diff(trg)
    sec_edges = np.arange(0, np.ceil(dur) + 1.0)
    rate = {str(k): _hist(t[et == k] * 1e-9, sec_edges).tolist() for k in (1, 2, 3)}
    dt_all = np.diff(t) * 1e-3
    summ.update({
        "n_entries": int(n), "n_read": int(n_read), "eventtype": et_counts,
        "duration": dur, "tcb_wraps": clock.n_wrap, "tcb_backward": clock.n_back,
        # EventType 3 (FADC + SADC) does not always mean A AND B fired: split it by the trigger bits
        "et3_ab": int(((et == prd.ET_BOTH) & (ftrig[:, 0] == 1) & (ftrig[:, 1] == 1)).sum()) if n_read else 0,
        "et3_single": int(((et == prd.ET_BOTH) & ((ftrig[:, 0] + ftrig[:, 1]) == 1)).sum()) if n_read else 0,
        "dt_min_us": float(np.diff(t).min() * 1e-3) if n_read > 1 else None,
        "tcb_first": None, "max_gap": float(dt_all.max() * 1e-6) if len(dt_all) else 0.0,
        "trgnum_first": int(trg[0]) if n_read else None, "trgnum_last": int(trg[-1]) if n_read else None,
        "trgnum_dup": int((d_trg == 0).sum()), "trgnum_back": int((d_trg < 0).sum()),
        "trgnum_skip": int(np.clip(d_trg - 1, 0, None).sum()) if len(d_trg) else 0,
        "rate_1s": rate,
        "proc_seconds": None,
    })
    if n_read:
        with uproot.open(fn) as f2:
            tt = f2["Event"]["TCBTRGTime"].array(library="np", entry_stop=1)
            tl = f2["Event"]["TCBTRGTime"].array(library="np", entry_start=n_read - 1, entry_stop=n_read)
        summ["tcb_first"], summ["tcb_last"] = float(tt[0]), float(tl[0])

    if cols:
        fs = {"n_trig": int(len(cols["T"])),
              "n_sat": [int(cols[f"Sat_{c}"].sum()) for c in channels]}
        for c in channels:
            fs[f"ped_{c}"] = _hist(cols[f"Ped_{c}"], PED_EDGES).tolist()
            fs[f"pedrms_{c}"] = _hist(cols[f"PedRMS_{c}"], RMS_EDGES).tolist()
            fs[f"peak_{c}"] = _hist(cols[f"Peak_{c}"], PEAK_EDGES).tolist()
            fs[f"qsum_{c}"] = _hist(cols[f"Qsum_{c}"], QSUM_EDGES).tolist()
            fs[f"ped_median_{c}"] = float(np.median(cols[f"Ped_{c}"]))
            fs[f"pedrms_median_{c}"] = float(np.median(cols[f"PedRMS_{c}"]))
            fs[f"peak_median_{c}"] = float(np.median(cols[f"Peak_{c}"]))
            fs[f"qsum_median_{c}"] = float(np.median(cols[f"Qsum_{c}"]))
            fs[f"pedeo_median_{c}"] = float(np.median(cols[f"PedEO_{c}"]))
            # pulse shape: rise (peak - leading edge) and effective width Qsum / height, pulses well above THR
            ok = (cols[f"Fired_{c}"] >= 0) & (cols[f"Height_{c}"] > 200) & (cols[f"Sat_{c}"] == 0)
            rise = (cols[f"Peak_{c}"] - cols[f"Fired_{c}"])[ok]
            fs[f"rise_{c}"] = _hist(rise, RISE_EDGES).tolist()
            fs[f"rise_median_{c}"] = float(np.median(rise)) if ok.any() else None
            fs[f"width_median_{c}"] = float(np.median(cols[f"Qsum_{c}"][ok] / cols[f"Height_{c}"][ok])) if ok.any() else None
            fs[f"fired_median_{c}"] = float(np.median(cols[f"Fired_{c}"][cols[f"Fired_{c}"] >= 0])) if (cols[f"Fired_{c}"] >= 0).any() else None
        fs["qgm"] = _hist(cols["Qgm"], QSUM_EDGES).tolist()
        lr = np.log10(np.clip(cols["Qsum_0"], 1, None) / np.clip(cols["Qsum_1"], 1, None))
        fs["log_ab_median"] = float(np.median(lr))
        fs["dt_prev_fadc"] = _hist(cols["DtPrevFADC"][cols["DtPrevFADC"] > 0], DT_EDGES).tolist()
        fs["dt_prev_muon"] = _hist(cols["DtPrevMuon"][cols["DtPrevMuon"] > 0], DT_EDGES).tolist()
        summ["fadc"] = fs
    if sadc is not None:
        pn = np.maximum(sadc["ped_n"], 1)
        mean = sadc["ped_sum"] / pn
        summ["sadc"] = {"thr": sadc["thr"], "pmt_id": sadc["pmt_id"], "n_hit": sadc["n_hit"].tolist(),
                        "adc_hit": sadc["adc_hit"].tolist(), "ped_mean": mean.tolist(),
                        "ped_rms": np.sqrt(np.maximum(sadc["ped_sum2"] / pn - mean ** 2, 0)).tolist(),
                        "mult": sadc["mult"].tolist(), "pair": sadc["pair"].tolist()}
    summ["proc_seconds"] = time.time() - t0
    return cols, summ


def prd_run_of(fn):
    b = os.path.basename(fn)
    try:
        return int(b.split("_")[1].split(".")[0])
    except (IndexError, ValueError):
        return -1


def write(path, cols, summ):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with uproot.recreate(tmp) as f:
        if cols:
            f["FADC"] = cols
        f["summary"] = json.dumps(summ)
    os.replace(tmp, path)                      # a finished file is always complete
    return path


def run_subrun(fn, base=None, cfg=None, overwrite=False):
    run, sub = prd_run_of(fn), prd.subrun_of(fn)
    out = output_path(run, sub, base)
    if os.path.exists(out) and not overwrite and os.path.getmtime(out) >= os.path.getmtime(fn):
        return out, None                       # done, and the PRD file has not been replaced since
    cols, summ = process_subrun(fn, cfg)
    write(out, cols, summ)
    return out, summ


def read_summaries(run, base=None):
    """{subrun: summary dict} of the prompt outputs of a run."""
    d = os.path.join(out_dir(base), f"{run:06d}")
    out = {}
    for fn in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        if fn.startswith("prompt_") and fn.endswith(".root"):
            with uproot.open(os.path.join(d, fn)) as f:
                s = json.loads(str(f["summary"]))
            out[s["subrun"]] = s
    return out


def read_fadc(run, base=None, branches=None):
    """Concatenated FADC tables of a run (dict of numpy arrays)."""
    d = os.path.join(out_dir(base), f"{run:06d}")
    parts = []
    for fn in sorted(os.listdir(d)):
        if fn.startswith("prompt_") and fn.endswith(".root"):
            with uproot.open(os.path.join(d, fn)) as f:
                if "FADC" in f:
                    a = f["FADC"].arrays(branches, library="ak")
                    parts.append({k: ak.to_numpy(a[k]) for k in a.fields})
    if not parts:
        return {}
    return {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}
