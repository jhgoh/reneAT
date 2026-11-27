"""
Run catalog (DAQ sqlite db), bad-run list and run config, all read-only.

    cat = RunCatalog()            # newest runcatalog.*.db under RENE_DB
    info = cat[4185]              # dict: runnum, rundesc, config, stime, etime, nfadc, tfadc, ...
    cat.source(4185)              # 'Cs137'
    cat.runs(source='Co60')       # run numbers with that source in the description
    cat.is_bad(4185)
"""
import glob
import os
import re
import sqlite3

DB_DIR = os.environ.get("RENE_DB", "/store/cpnr-data/RENE/db")
CONFIG_DIR = os.environ.get("RENE_CONFIG", "/store/cpnr-data/RENE/config")

# rundesc text -> source label
_SOURCES = [
    ("Cs137", r"cs[\s_-]*137"),
    ("Co60", r"co[\s_-]*60"),
    ("AmBe", r"am[\s_-]*be"),
    ("Cf252", r"cf[\s_-]*252"),
    ("Zn65", r"zn[\s_-]*65"),
    ("Na22", r"na[\s_-]*22"),
    ("none", r"no\s*source|background"),
]

# Any other "<element><mass>" written in the description is taken as written (e.g. Th232, Ge68,
# and also Ge60 or Zn60 if that is what the shift log says). Case-sensitive, no space inside;
# B is left out because veto panels are called B1, B30, ...
_ELEMENTS = ("He Li Be C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn Ga Ge As Se "
             "Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy "
             "Ho Er Tm Yb Lu Hf Ta W Re Os Ir Pt Au Hg Tl Pb Bi Po At Rn Fr Ra Ac Th Pa U Np Pu Am Cm Bk Cf").split()
_ISOTOPE = re.compile(r"(?<![A-Za-z0-9])(%s)[_-]?(\d{2,3})(?![\d.])" % "|".join(sorted(_ELEMENTS, key=len, reverse=True)))


def latest_db(db_dir=None):
    dbs = sorted(glob.glob(os.path.join(db_dir or DB_DIR, "runcatalog.20*.db")))
    dbs = [d for d in dbs if not d.endswith(".ori.db")]
    if not dbs:
        raise FileNotFoundError(f"no runcatalog.*.db in {db_dir or DB_DIR}")
    return dbs[-1]


def source_of(desc):
    """Source label from a run description; several sources are joined by '+'
    (e.g. 'Co60+AmBe' for runs with sources on the veto). Names are taken as written in the
    shift log, not corrected. None if not stated."""
    d = (desc or "").lower()
    hit = [name for name, pat in _SOURCES if re.search(pat, d)]
    for m in _ISOTOPE.finditer(desc or ""):
        name = m.group(1) + m.group(2)
        if name not in hit:
            hit.append(name)
    if len(hit) > 1 and "none" in hit:
        hit.remove("none")
    return "+".join(hit) if hit else None


class RunCatalog:
    def __init__(self, path=None, badrun_list=None):
        self.path = path or latest_db()
        self._db = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True)
        self._db.row_factory = sqlite3.Row
        self._bad = None
        self._badrun_list = badrun_list or os.path.join(os.path.dirname(self.path), "badrun_list.txt")

    def __getitem__(self, run):
        r = self._db.execute("select * from runcatalog where runnum=?", (int(run),)).fetchone()
        if r is None:
            raise KeyError(f"run {run} not in {self.path}")
        return dict(r)

    def __contains__(self, run):
        return self._db.execute("select 1 from runcatalog where runnum=?", (int(run),)).fetchone() is not None

    def source(self, run):
        return source_of(self[run]["rundesc"])

    def runs(self, first=None, last=None, source=None, good_only=True):
        q, a = "select runnum, rundesc from runcatalog where 1", []
        if first is not None:
            q += " and runnum>=?"; a.append(int(first))
        if last is not None:
            q += " and runnum<=?"; a.append(int(last))
        out = []
        for run, desc in self._db.execute(q + " order by runnum", a):
            if source is not None and source_of(desc) != source:
                continue
            if good_only and self.is_bad(run):
                continue
            out.append(run)
        return out

    # --- bad runs -------------------------------------------------------
    def badruns(self):
        """{run: category} from badrun_list.txt (run, date, time, category, subruns, memo)."""
        if self._bad is None:
            self._bad = {}
            if os.path.exists(self._badrun_list):
                for line in open(self._badrun_list, encoding="utf-8"):
                    tok = line.split()
                    if tok and not line.lstrip().startswith("#") and tok[0].isdigit():
                        self._bad[int(tok[0])] = tok[3] if len(tok) > 3 else ""
        return self._bad

    def is_bad(self, run):
        return int(run) in self.badruns()

    # --- config ---------------------------------------------------------
    def config_text(self, run):
        p = os.path.join(CONFIG_DIR, f"{int(run):06d}.config")
        return open(p, encoding="utf-8", errors="replace").read() if os.path.exists(p) else None
