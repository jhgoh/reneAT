"""
PRD (data or MC) -> per-trigger feature ntuple with one common definition.

Every FADC trigger gets, per channel c (0 = PMT A, 1 = PMT B):
    Ped_c, PedRMS_c, Qsum_c, Qtail_c, Rtail_c, Fired_c, Height_c, Peak_c
computed by ``qsum.compute_channel`` with one ``QSumConfig``.
Data and MC therefore go through exactly the same code path.

MC files additionally get the truth of the matching trigger
(``MC.Trig_*`` where ``Trig_Entry`` == Event entry): MCEvent, TrigT, Edep,
Equench, NPEA, NPEB, CenX/Y/Z.

Normalisation is kept in the metadata:
    data: ``livetime`` [s] = elapsed TCB time of the entries read (wrap undone, see prd.TCBClock),
          summed over runs; ``livetime_catalog`` = catalog tfadc of the runs, for reference
    MC:   ``n_primary`` = number of generated events (decays) behind the triggers read

Output: ROOT file with tree ``QSum`` and a JSON string ``meta`` (TObjString),
or ``.npz``; ``load()`` reads either back.
"""
import json
import os
from collections import defaultdict

import awkward as ak
import numpy as np
import uproot

import prd
from qsum import QSumConfig, compute_channel

FEATURES = {"ped": "Ped", "ped_rms": "PedRMS", "ped_eo": "PedEO", "ped_max": "PedMax", "qsum": "Qsum", "qtail": "Qtail",
            "rtail": "Rtail", "fired": "Fired", "height": "Height", "peak": "Peak"}
INT_FEATURES = {"fired", "peak"}
MC_TRUTH = {"Trig_T": "TrigT", "Trig_Edep": "Edep", "Trig_Equench": "Equench",
            "Trig_NPEA": "NPEA", "Trig_NPEB": "NPEB",
            "Trig_CenX": "CenX", "Trig_CenY": "CenY", "Trig_CenZ": "CenZ"}


def _run_of(path):
    """Run number from <...>/PRD_<run>.<sub>.root, else None."""
    b = os.path.basename(path)
    if b.startswith("PRD_"):
        try:
            return int(b[4:].split(".")[0])
        except ValueError:
            pass
    return None


def _mc_truth_lookup(path):
    """Event entry -> truth arrays for one MC file."""
    mc = uproot.open(path)["MC"].arrays(["MCEvent", "Trig_Entry"] + list(MC_TRUTH), library="ak")
    n = ak.num(mc["Trig_Entry"])
    entry = ak.to_numpy(ak.flatten(mc["Trig_Entry"]))
    out = {"MCEvent": np.repeat(ak.to_numpy(mc["MCEvent"]), ak.to_numpy(n))}
    for k, v in MC_TRUTH.items():
        out[v] = ak.to_numpy(ak.flatten(mc[k]))
    order = np.argsort(entry)
    return entry[order], {k: v[order] for k, v in out.items()}


def make(inputs, cfg=None, channels=(0, 1), fadc_only=True, max_events=None,
         catalog=None, base=None, step_size="200 MB", verbose=True):
    """Build the feature table. ``inputs``: run numbers and/or PRD file names.

    Returns (table, meta): table is a dict of equal-length numpy arrays.
    """
    cfg = cfg or QSumConfig()
    files = prd.expand(inputs, base)
    mc = prd.is_mc(files[0])

    branches = ["TrgNum", "EventType", "TCBTRGTime", "F_THR"] + [f"F_Waveform_{c}" for c in channels]
    with uproot.open(files[0]) as f0:
        if "F_Triggered" in f0["Event"]:
            branches.append("F_Triggered")
    if mc:
        branches += ["MCRun", "MCEvent"]

    cols = defaultdict(list)
    n_read = 0
    clocks = {}                    # data: run -> TCBClock
    mc_seen = {}                   # MC: file -> max MCEvent read
    lookup_file, lookup = None, None
    thr = None

    last_file = None
    for ifile, fn, start, arr in prd.iterate(files, branches, step_size, max_events):
        if fn != last_file:        # check only the files actually read (a run can have >10k files)
            if ifile > 0 and prd.is_mc(fn) != mc:
                raise ValueError(f"{fn}: do not mix data and MC files in one ntuple")
            last_file = fn
        n = len(arr)
        n_read += n
        trg = ak.to_numpy(arr["TrgNum"]).astype(np.int64)
        et = ak.to_numpy(arr["EventType"]).astype(np.int32)
        if thr is None:
            thr = ak.to_numpy(arr["F_THR"][0]).astype(float)
        if mc:
            mce = ak.to_numpy(arr["MCEvent"])
            mc_seen[fn] = max(mc_seen.get(fn, -1), int(mce.max()) if n else -1)
        else:
            clocks.setdefault(_run_of(fn), prd.TCBClock()).add(ak.to_numpy(arr["TCBTRGTime"]))

        sel = (et == prd.ET_FADC) | (et == prd.ET_BOTH) if fadc_only else np.ones(n, bool)
        if not sel.any():
            continue
        entry = np.arange(start, start + n)[sel]

        cols["Run"].append(np.full(sel.sum(), ak.to_numpy(arr["MCRun"])[0] if mc else (_run_of(fn) or -1), np.int32))
        cols["SubRun"].append(np.full(sel.sum(), ifile if mc else prd.subrun_of(fn), np.int32))
        cols["Entry"].append(entry.astype(np.int64))
        cols["TrgNum"].append(trg[sel])
        cols["EventType"].append(et[sel])
        cols["TCBTRGTime"].append(ak.to_numpy(arr["TCBTRGTime"])[sel])
        if "F_Triggered" in arr.fields:
            ftr = ak.to_numpy(arr["F_Triggered"])[sel]
            for c in channels:
                cols[f"FTrig_{c}"].append(ftr[:, c].astype(np.int32))
        for c in channels:
            w = prd.waveform(arr[sel], c)
            r = compute_channel(w, thr[c] if c < len(thr) else 80.0, cfg)
            for k, name in FEATURES.items():
                cols[f"{name}_{c}"].append(r[k].astype(np.int32 if k in INT_FEATURES else np.float32))

        if mc:
            if lookup_file != fn:
                lookup_file, lookup = fn, _mc_truth_lookup(fn)
            keys, truth = lookup
            pos = np.searchsorted(keys, entry)
            ok = (pos < len(keys)) & (keys[np.minimum(pos, len(keys) - 1)] == entry)
            pos = np.minimum(pos, len(keys) - 1)
            for name, v in truth.items():
                x = v[pos].astype(np.float64 if v.dtype.kind == "f" else np.int64)
                if x.dtype.kind == "f":
                    x[~ok] = np.nan
                else:
                    x[~ok] = -1
                cols[name].append(x)

        if verbose:
            print(f"[reneat] {os.path.basename(fn)} +{n} entries, {sel.sum()} FADC triggers")

    table = {k: np.concatenate(v) for k, v in cols.items()}
    meta = {"is_mc": mc, "files": files, "n_read": n_read,
            "n_trig": int(len(table.get("TrgNum", []))), "channels": list(channels),
            "fadc_only": fadc_only, "qsum_config": cfg.as_dict(),
            "thr": None if thr is None else thr.tolist()}

    if mc:
        info = prd.mc_info(sorted(mc_seen))
        nev = dict(zip(sorted(mc_seen), info["NEvents"].tolist()))
        # whole file read -> its NEvents; truncated -> last MCEvent seen + 1
        full = max_events is None or n_read < max_events
        meta["n_primary"] = int(sum(nev[f] if full else mc_seen[f] + 1 for f in mc_seen))
        meta["mc_info"] = {k: (v.tolist() if v.dtype.kind in "iuf" else [str(x) for x in v])
                           for k, v in info.items() if k in ("MCRun", "Seed", "NEvents", "NTriggers",
                                                               "RenesimVersion", "RatVersion", "TargetMaterial")}
    else:
        cat = catalog
        if cat is None:
            from catalog import RunCatalog
            cat = RunCatalog()
        live = {run: ck.seconds for run, ck in clocks.items()}
        meta["livetime"] = float(sum(live.values()))
        meta["livetime_by_run"] = {str(k): v for k, v in live.items()}
        meta["tcb_wraps_by_run"] = {str(k): ck.n_wrap for k, ck in clocks.items()}
        meta["livetime_catalog"] = {str(k): (cat[k]["tfadc"] if k in cat else None) for k in clocks}
        meta["catalog"] = cat.path
    return table, meta


def save(path, table, meta):
    if path.endswith(".npz"):
        np.savez_compressed(path, __meta__=json.dumps(meta), **table)
        return path
    with uproot.recreate(path) as f:
        f["QSum"] = table
        f["meta"] = json.dumps(meta)
    return path


def load(path):
    """(table, meta) from a file written by ``save``."""
    if path.endswith(".npz"):
        z = np.load(path, allow_pickle=False)
        return {k: z[k] for k in z.files if k != "__meta__"}, json.loads(str(z["__meta__"]))
    with uproot.open(path) as f:
        return f["QSum"].arrays(library="np"), json.loads(str(f["meta"]))
