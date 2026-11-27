"""
The offline good-run sheet (Google Sheets): one tab per dataset with one row per run
(Source, Detector, HV, THR, Description, Data issue, ...) and a "Dataset" tab with the
run ranges. Read through its public CSV export and cached locally, so analysis jobs on
nodes without internet use the last downloaded copy.

    RENE_RUNSHEET        sheet URL (setup.sh sets the default; a bit.ly link works too)
    RENE_RUNSHEET_CACHE  cache directory (default <reneAT>/cache/runsheet, not in git)

``RunSheet()[run]`` gives a dict with the sheet columns as written plus ``dataset`` and
``type``: source / no source / LED / laser / veto test / blank (Source left empty) / other.
"""
import csv
import io
import json
import os
import re
import time
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
CACHE = os.environ.get("RENE_RUNSHEET_CACHE", os.path.join(REPO, "cache", "runsheet"))
_SOURCE_RE = re.compile(r"(cs|co|na|zn|th|ge|eu|cf|am-?be|duran)\s*-?\d*", re.I)


def _get(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": "reneat"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.geturl(), r.read().decode("utf-8")


def _sheet_id(url):
    m = re.search(r"/spreadsheets/d/([A-Za-z0-9_-]+)", url)
    if m:
        return m.group(1)
    final, _ = _get(url)                         # short link: follow the redirect
    m = re.search(r"/spreadsheets/d/([A-Za-z0-9_-]+)", final)
    if not m:
        raise ValueError(f"{url} does not lead to a Google sheet")
    return m.group(1)


def _clean(h):
    return " ".join(h.replace("\n", " ").split())


def update(url=None, cache=None, verbose=True):
    """Download every tab as CSV into the cache and rebuild runs.json."""
    url = url or os.environ.get("RENE_RUNSHEET")
    if not url:
        raise RuntimeError("set RENE_RUNSHEET (source setup.sh) to the run sheet URL")
    cache = cache or CACHE
    os.makedirs(cache, exist_ok=True)
    sid = _sheet_id(url)
    _, page = _get(f"https://docs.google.com/spreadsheets/d/{sid}/htmlview")
    gids = sorted(set(re.findall(r"gid=(\d+)", page)), key=int)
    tabs = {}
    for gid in gids:
        _, text = _get(f"https://docs.google.com/spreadsheets/d/{sid}/export?format=csv&gid={gid}")
        tabs[gid] = text
        with open(os.path.join(cache, f"tab_{gid}.csv"), "w", encoding="utf-8") as fh:
            fh.write(text)
    runs, datasets = parse(tabs)
    with open(os.path.join(cache, "runs.json"), "w", encoding="utf-8") as fh:
        json.dump({"updated": time.strftime("%Y-%m-%d %H:%M:%S"), "sheet": sid,
                   "datasets": datasets, "runs": runs}, fh, ensure_ascii=False, indent=0)
    if verbose:
        print(f"[reneat] run sheet: {len(tabs)} tabs, {len(datasets)} datasets, {len(runs)} runs -> {cache}")
    return runs, datasets


def parse(tabs):
    """{gid: csv text} -> ({run: row}, [dataset rows])."""
    datasets, run_tabs = [], []
    for gid, text in tabs.items():
        rows = list(csv.reader(io.StringIO(text)))
        if not rows:
            continue
        head = [_clean(h) for h in rows[0]]
        if head and head[0] == "Dataset":
            for r in rows[1:]:
                if r and r[0].strip():
                    d = dict(zip(head, (x.strip() for x in r)))
                    datasets.append({"name": d["Dataset"], "first": _int(d.get("BeginRun")),
                                     "last": _int(d.get("EndRun")), "location": d.get("Location", ""),
                                     "detector": next((v for k, v in d.items() if k.startswith("Detector")), ""),
                                     "description": next((v for k, v in d.items() if k.startswith("Description")), "")})
        elif head and head[0] == "Run" and any(h.startswith("Start Date") for h in head) \
                and any(h.startswith("Source") for h in head):
            run_tabs.append((gid, head, rows[1:]))
    runs = {}
    for gid, head, rows in run_tabs:
        for r in rows:
            if not r or not r[0].strip().isdigit():
                continue
            d = {k: " ".join(v.split()) for k, v in zip(head, r) if k}
            run = int(r[0])
            src_key = next(k for k in d if k.startswith("Source"))
            d["source"] = d.pop(src_key)
            d["source_column"] = src_key
            d["tab"] = gid
            ds = dataset_of(run, datasets)
            d["dataset"] = ds["name"] if ds else ""
            d["type"] = run_type(d, ds)
            runs[str(run)] = d
    return runs, datasets


def _int(x):
    try:
        return int(str(x).strip())
    except (TypeError, ValueError):
        return None


def dataset_of(run, datasets):
    for d in datasets:
        if d["first"] is not None and run >= d["first"] and (d["last"] is None or run <= d["last"]):
            return d
    return None


def run_type(row, ds=None):
    s = row.get("source", "")
    text = " ".join([(ds or {}).get("detector", ""), (ds or {}).get("description", "")]).lower()
    if "veto test" in text or "veto study" in text:
        return "veto test"
    if row.get("source_column", "").lower().startswith("source (laser") or s.lower().startswith("laser"):
        return "laser"
    if s.upper().startswith("LED"):
        return "LED"
    if _SOURCE_RE.search(s):
        return "source"
    if s == "-" or s.upper().startswith("BKG"):
        return "no source"
    if s == "":
        return "blank"
    return "other"


class RunSheet:
    """Cached run sheet. ``update=True`` downloads first; with no cache it downloads once."""

    def __init__(self, cache=None, update_now=False):
        self.cache = cache or CACHE
        path = os.path.join(self.cache, "runs.json")
        if update_now or not os.path.exists(path):
            update(cache=self.cache, verbose=False)
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        self.updated = data["updated"]
        self.datasets = data["datasets"]
        self._runs = data["runs"]

    def __contains__(self, run):
        return str(run) in self._runs

    def __getitem__(self, run):
        return self._runs[str(run)]

    def get(self, run, default=None):
        return self._runs.get(str(run), default)

    def runs(self, type=None, dataset=None):
        out = []
        for k, v in self._runs.items():
            if (type is None or v["type"] == type) and (dataset is None or v["dataset"] == dataset):
                out.append(int(k))
        return sorted(out)


def try_sheet():
    """RunSheet or None (no cache and no network): callers treat the sheet as optional."""
    try:
        return RunSheet()
    except Exception:
        return None
