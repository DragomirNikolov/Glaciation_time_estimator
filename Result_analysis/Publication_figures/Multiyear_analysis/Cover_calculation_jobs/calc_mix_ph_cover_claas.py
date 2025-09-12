#!/usr/bin/env python3
"""
process_claas_cttmask_daily_parallel.py

Usage:
  python process_claas_cph_daily_parallel.py \
      --base /wolke_scratch/dnikolo/CLAAS_Data \
      --output /wolke_scratch/dnikolo/processed_daily \
      --year 2010 \
      --workers 8

- Scans: <base>/<group>/<YYYY>/<MM>/<DD>/Agg_*_YYYYMMDDHHMMSS.nc
  where <group> is typically {np, sp}.

- For each day directory, builds a binary mask where
    ctt_resampled ∈ [ctt_min, ctt_max]  (inclusive)
  using CDO:
    cdo -L -timmean -setrtoc,ctt_min,ctt_max,1,0 \
        -mergetime (-selvar,ctt_resampled each_file ...) out.nc

- Runs days in PARALLEL with a fixed number of workers.

Output layout:
  <output_root>/<group>/<YYYY>/<MM>/<YYYYMMDD>_timmean.nc
  (values are fractions in [0,1] representing daily time fraction in-range)
"""

import os
import re
import glob
import argparse
import subprocess
from datetime import date, timedelta
from concurrent.futures import ProcessPoolExecutor, as_completed
from functools import partial

# Match Agg files, e.g. Agg_01_20100201003000.nc
# Capture the YYYYMMDD part to sanity-check the folder day.
AGG_RE = re.compile(r"^Agg_01_(\d{8})\d{6}\.nc$")

def iter_days_of_year(year: int):
    d = date(year, 1, 1)
    last = date(year, 12, 31)
    one = timedelta(days=1)
    while d <= last:
        yield d
        d += one

def list_day_files(base_root: str, group: str, day_str: str):
    """
    Return sorted list of Agg_* files for the given group and YYYYMMDD.
    It only picks files whose name embeds the same YYYYMMDD.
    Directory: <base>/<group>/<YYYY>/<MM>/<DD>/
    Files:     Agg_*_<YYYYMMDD><HHMMSS>.nc
    """
    y, m, dd = day_str[:4], day_str[4:6], day_str[6:8]
    day_dir = os.path.join(base_root, group, y, m, dd)
    if not os.path.isdir(day_dir):
        return []
    candidates = sorted(glob.glob(os.path.join(day_dir, f"Agg_01_{day_str}*.nc")))
    return [fp for fp in candidates if AGG_RE.match(os.path.basename(fp))]

def build_cdo_cmd(day_files, out_file, varname="ctt_resampled",
                  ctt_min=235.15, ctt_max=273.15, silent=True):
    """
    One-call CDO pipeline:
      cdo [-s] -L -timmean -setrtoc,<min>,<max>,1,0 -mergetime  (-selvar,<varname> f1) ...  out.nc
    This yields the daily time-mean of a 0/1 mask where var ∈ [min,max].
    """
    cmd = ['cdo']
    if silent:
        cmd.append('-s')
    cmd += ['-L', '-timmean', f'-setrtoc2,{ctt_min},{ctt_max},1,0', '-mergetime']
    for f in day_files:
        cmd += [f'-selvar,{varname}', f]
    cmd.append(out_file)
    return cmd

def run_cdo(cmd, verbose=False):
    env = dict(os.environ)
    env.setdefault('OMP_NUM_THREADS', '1')  # avoid oversubscription with parallel jobs
    if verbose:
        print("CMD:", ' '.join(cmd))
    subprocess.run(cmd, check=True, env=env)

def process_one_day(task, varname="ctt_resampled", ctt_min=235.15, ctt_max=273.15,
                    silent=True, verbose=False, overwrite=False, output_root=None):
    group, day, day_files = task
    y, m = day[:4], day[4:6]
    out_dir = os.path.join(output_root, group, y, m)
    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, f'{day}_timmean.nc')

    if (not overwrite) and os.path.exists(out_file):
        if verbose:
            print(f"SKIP exists: {out_file}")
        return (day, True, "exists")

    cmd = build_cdo_cmd(day_files, out_file, varname=varname,
                        ctt_min=ctt_min, ctt_max=ctt_max, silent=silent)
    run_cdo(cmd, verbose=verbose)
    return (day, True, "ok")

def discover_groups(base_root: str):
    # Prefer the standard np/sp if present; otherwise include all subdirs.
    preferred = [d for d in ['np', 'sp'] if os.path.isdir(os.path.join(base_root, d))]
    if preferred:
        return preferred
    return sorted([os.path.basename(p) for p in glob.glob(os.path.join(base_root, '*')) if os.path.isdir(p)])

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='/wolke_scratch/dnikolo/CLAAS_Data/Resampled_Data',
                    help='Base input root (Resampled_Data)')
    ap.add_argument('--output', default='/wolke_scratch/dnikolo/processed_daily', help='Output root')
    ap.add_argument('--year', required=True, help='Year to process (e.g., 2010)')
    ap.add_argument('--workers', type=int, default=4, help='Parallel CDO jobs')
    ap.add_argument('--verbose', action='store_true', help='Print CDO commands')
    ap.add_argument('--no-silent', action='store_true', help='Disable CDO -s')
    ap.add_argument('--overwrite', action='store_true', help='Overwrite existing outputs')
    ap.add_argument('--groups', nargs='*', help='Limit to these groups (e.g., np sp). Default: auto-detect.')
    ap.add_argument('--var', default='ctt_resampled', help='Variable to threshold (default: ctt_resampled)')
    ap.add_argument('--ctt-min', type=float, default=235.15, help='Lower inclusive threshold in Kelvin')
    ap.add_argument('--ctt-max', type=float, default=273.15, help='Upper inclusive threshold in Kelvin')
    args = ap.parse_args()

    try:
        year_int = int(args.year)
    except ValueError:
        raise SystemExit(f"--year must be an integer like 2010, got: {args.year}")

    groups = args.groups if args.groups else discover_groups(args.base)
    if not groups:
        print(f"No group directories found under {args.base}")
        return

    tasks = []
    for group in groups:
        for d in iter_days_of_year(year_int):
            day = d.strftime('%Y%m%d')
            files = list_day_files(args.base, group, day)
            if files:
                tasks.append((group, day, files))

    total = len(tasks)
    print(f"Discovered {total} day-jobs across groups: {', '.join(groups)}.")
    if total == 0:
        return

    silent = (not args.no_silent)
    worker = partial(
        process_one_day,
        varname=args.var,
        ctt_min=args.ctt_min,
        ctt_max=args.ctt_max,
        silent=silent,
        verbose=args.verbose,
        overwrite=args.overwrite,
        output_root=args.output
    )

    done = 0
    failed = 0
    from concurrent.futures import ProcessPoolExecutor, as_completed
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(worker, t): t for t in tasks}
        for fut in as_completed(futures):
            group, day, _ = futures[fut]
            try:
                _, ok, msg = fut.result()
                done += 1
                tag = "OK" if ok else "SKIP"
                y, m, dd = day[:4], day[4:6], day[6:8]
                print(f"[{done}/{total}] {group}/{y}/{m}/{dd}: {tag} ({msg})")
            except subprocess.CalledProcessError as e:
                failed += 1
                done += 1
                y, m, dd = day[:4], day[4:6], day[6:8]
                print(f"[{done}/{total}] {group}/{y}/{m}/{dd}: ERROR -> {e}")

    if failed:
        print(f"Completed with {failed} failures.")
    else:
        print("All done.")

if __name__ == '__main__':
    main()
