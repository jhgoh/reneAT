"""
Running prompt processing + DQM for whole runs: locally with a process pool, or on SLURM,
and ``watch`` for runs whose PRD transfer is finished (meant for cron).
"""
import glob
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

import prd
import prompt
import dqm

REPO = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


def _one(args):
    fn, base, overwrite = args
    out, s = prompt.run_subrun(fn, base, overwrite=overwrite)
    return fn, (s or {}).get("error"), (s or {}).get("proc_seconds")


def prompt_run(run, base=None, jobs=8, subruns=None, task=None, ntask=None, overwrite=False, verbose=True):
    """Process the sub-runs of a run that have no prompt output yet. ``task/ntask``: every ntask-th file."""
    files = prd.run_files(run, subruns=subruns)
    if task is not None:
        files = files[task::ntask]
    todo = [(f, base, overwrite) for f in files]
    t0, n_err = time.time(), 0
    if jobs <= 1:
        it = map(_one, todo)
    else:
        ex = ProcessPoolExecutor(jobs)
        it = (f.result() for f in as_completed([ex.submit(_one, x) for x in todo]))
    for i, (fn, err, sec) in enumerate(it, 1):
        n_err += err is not None
        if verbose and (err or i % 50 == 0 or i == len(todo)):
            print(f"[reneat] run {run}: {i}/{len(todo)} sub-runs, {time.time() - t0:.0f} s"
                  + (f"  ERROR {os.path.basename(fn)}: {err.splitlines()[0]}" if err else ""), flush=True)
    return len(todo), n_err


def _sbatch(args, script, dependency=None):
    cmd = ["sbatch", "--parsable", "--export=ALL"] + args + ([f"--dependency=afterany:{dependency}"] if dependency else []) + [script]
    out = subprocess.run(cmd, check=True, capture_output=True, text=True).stdout.strip()
    return out.split(";")[0]


def submit(run, base=None, ntask=32, partition=None, logdir=None):
    """SLURM: an array of prompt tasks, then one DQM + trend job after them."""
    base = prompt.out_dir(base)
    logdir = logdir or os.path.join(base, "log")
    os.makedirs(logdir, exist_ok=True)
    exe = f"{sys.executable} {os.path.join(REPO, 'bin', 'reneat')}"
    env = f"export PYTHONPATH={os.path.join(REPO, 'python')}${{PYTHONPATH:+:$PYTHONPATH}}\nexport RENE_PROMPT={base}\n"
    p_script = os.path.join(logdir, f"prompt_{run:06d}.sh")
    with open(p_script, "w") as fh:
        fh.write(f"#!/bin/bash\n{env}{exe} prompt {run} -j 1 --task $SLURM_ARRAY_TASK_ID --ntask {ntask}\n")
    d_script = os.path.join(logdir, f"dqm_{run:06d}.sh")
    with open(d_script, "w") as fh:
        fh.write(f"#!/bin/bash\n{env}{exe} dqm {run} && {exe} trend\n")
    part = [f"--partition={partition}"] if partition else []
    jid = _sbatch(part + [f"--array=0-{ntask - 1}", f"--job-name=prompt_{run}",
                          f"--output={logdir}/prompt_{run:06d}_%a.out"], p_script)
    did = _sbatch(part + [f"--job-name=dqm_{run}", f"--output={logdir}/dqm_{run:06d}.out"], d_script, dependency=jid)
    return jid, did


def run_state(run, base=None):
    """(n_prd_files, newest PRD mtime, dqm summary mtime or None, n_processed in the summary)."""
    try:
        files = prd.run_files(run)
    except FileNotFoundError:
        return 0, None, None, 0
    newest = max(os.path.getmtime(f) for f in files)
    sj = os.path.join(dqm.dqm_dir(run, base), "summary.json")
    if os.path.exists(sj):
        with open(sj) as fh:
            n_proc = json.load(fh).get("n_processed", 0)
        return len(files), newest, os.path.getmtime(sj), n_proc
    return len(files), newest, None, 0


def ready_runs(base=None, first=None, min_age_h=2.0, catalog=None):
    """Runs whose PRD files stopped changing ``min_age_h`` hours ago and whose DQM is missing or older.

    A run counts as finished at the DAQ when the catalog has its end time; runs not in the
    catalog are taken on file age alone.
    """
    if catalog is None:
        from catalog import RunCatalog
        catalog = RunCatalog()
    now = time.time()
    out = []
    for d in sorted(glob.glob(os.path.join(prd.PRD_BASE, "[0-9]" * 6))):
        run = int(os.path.basename(d))
        if first is not None and run < first:
            continue
        n, newest, done, n_proc = run_state(run, base)
        if n == 0 or now - newest < min_age_h * 3600:
            continue
        if run in catalog and not catalog[run].get("etime"):
            continue
        if done is not None and done > newest and n_proc >= n:
            continue
        out.append(run)
    return out


def watch(base=None, first=None, min_age_h=2.0, mode="local", jobs=16, ntask=32, partition=None, dry=False):
    runs = ready_runs(base, first, min_age_h)
    print(f"[reneat] ready: {runs}")
    if dry:
        return runs
    for run in runs:
        if mode == "slurm":
            print(f"[reneat] run {run}: submitted", submit(run, base, ntask, partition))
        else:
            prompt_run(run, base, jobs)
            dqm.run_report(run, base)
    if runs and mode != "slurm":
        dqm.trend(base)
    return runs
