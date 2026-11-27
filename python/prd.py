"""
PRD file access, identical for detector data and renesim MC.

Both carry the same ``Event`` tree (TrgNum, EventType, TCBTRGTime, F_*, S_*).
MC files add ``MC`` (per decay/primary truth, one row per Geant4 event) and
``MCInfo`` (one row per job). Data files from the official production have
no ``Run`` tree in the 2026 commissioning runs, so nothing here relies on it.

FADC channel map (commissioning 2026, data and MC):
    F_Waveform_0 = PMT A (x = -910 mm), F_Waveform_1 = PMT B (x = +910 mm, DAQ side)
Waveforms are positive pulses above the pedestal, 2 ns per sample.
"""
import glob
import os

import awkward as ak
import numpy as np
import uproot

PRD_BASE = os.environ.get("RENE_PRD", "/store/cpnr-data/RENE/PRD")
SAMPLE_NS = 2.0
CHANNELS = {0: "A", 1: "B"}

# EventType: which digitiser fired
ET_NONE, ET_FADC, ET_SADC, ET_BOTH = 0, 1, 2, 3


def run_files(run, base=None, subruns=None):
    """Sorted PRD files of a run: <base>/<run:06d>/[PRD/]PRD_<run:06d>.<sub:05d>.root
    (a few runs keep their files in an extra PRD/ sub-directory)."""
    base = base or PRD_BASE
    name = f"PRD_{run:06d}.*.root"
    files = sorted(glob.glob(os.path.join(base, f"{run:06d}", name)) +
                   glob.glob(os.path.join(base, f"{run:06d}", "PRD", name)), key=subrun_of)
    if subruns is not None:
        keep = {int(s) for s in subruns}
        files = [f for f in files if subrun_of(f) in keep]
    if not files:
        raise FileNotFoundError(f"no PRD files for run {run} under {base}")
    return files


def subrun_of(path):
    """Sub-run number from a PRD file name, -1 if it does not follow the pattern."""
    try:
        return int(os.path.basename(path).split(".")[-2])
    except (IndexError, ValueError):
        return -1


def is_mc(path):
    with uproot.open(path) as f:
        return "MC" in f and "MCInfo" in f


def expand(inputs, base=None):
    """Turn a mix of run numbers and file names/globs into a list of files."""
    files = []
    for x in inputs:
        x = str(x)
        if x.isdigit():
            files += run_files(int(x), base)
        else:
            hit = sorted(glob.glob(x))
            if not hit:
                raise FileNotFoundError(x)
            files += hit
    return files


def iterate(files, branches, step_size="200 MB", entry_stop=None):
    """Yield (file_index, path, entry_start, arrays) over the Event tree.

    ``arrays`` is an awkward record array of ``branches``; ``entry_start`` is
    the Event-tree entry of its first row inside ``path``.
    ``entry_stop`` caps the total number of entries read over all files.
    """
    left = entry_stop
    for i, fn in enumerate(files):
        if left is not None and left <= 0:
            return
        with uproot.open(fn) as f:
            tree = f["Event"]
            stop = tree.num_entries if left is None else min(left, tree.num_entries)
            start = 0
            for arr in tree.iterate(branches, step_size=step_size, entry_stop=stop, library="ak"):
                yield i, fn, start, arr
                start += len(arr)
            if left is not None:
                left -= stop


def waveform(arr, ch, dtype=np.float64):
    """(N, NDP) array of channel ``ch`` raw ADC samples."""
    return ak.to_numpy(arr[f"F_Waveform_{ch}"]).astype(dtype)


# TCBTRGTime is in ns and wraps every 2^24 us (16.78 s); TrgNum is not usable as a clock
# either (it restarts within long runs, e.g. 4099).
TCB_WRAP_NS = float(2 ** 24 * 1000)


class TCBClock:
    """Accumulates elapsed time over consecutive entries, undoing the TCB wrap.

    A backward step larger than half the wrap period counts as one wrap; a small
    backward step (out-of-order entries) adds nothing. Gaps longer than one wrap
    period (16.8 s without any trigger) cannot be seen and are lost.
    """

    def __init__(self):
        self.prev = None
        self.elapsed_ns = 0.0
        self.n_wrap = 0
        self.n_back = 0              # backward steps that are not a wrap (out-of-order entries)

    def add(self, t):
        self.times(t)

    def times(self, t):
        """Add entries and return their elapsed time [ns] since the first entry ever added."""
        t = np.asarray(t, dtype=np.float64)
        if len(t) == 0:
            return np.zeros(0)
        first = self.prev is None
        t = np.r_[t[0] if first else self.prev, t]
        d = np.diff(t)
        wrap = d < -0.5 * TCB_WRAP_NS
        self.n_back = getattr(self, "n_back", 0) + int(((d < 0) & ~wrap).sum())
        d = np.where(wrap, d + TCB_WRAP_NS, np.maximum(d, 0.0))
        el = self.elapsed_ns + np.cumsum(d)
        self.elapsed_ns = float(el[-1])
        self.n_wrap += int(wrap.sum())
        self.prev = t[-1]
        return el

    @property
    def seconds(self):
        return self.elapsed_ns * 1e-9


def last_trgnum(files):
    """Largest TrgNum in the last file (the run's trigger count if all files are given)."""
    with uproot.open(files[-1]) as f:
        t = f["Event"]
        return int(t["TrgNum"].array(library="np", entry_start=max(t.num_entries - 1000, 0)).max())


def mc_info(files):
    """Concatenated MCInfo rows of MC files (dict of numpy arrays)."""
    rows = [uproot.open(fn)["MCInfo"].arrays(library="np") for fn in files]
    return {k: np.concatenate([r[k] for r in rows]) for k in rows[0]}
