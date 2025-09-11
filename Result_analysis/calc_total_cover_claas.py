#!/usr/bin/env python3
"""
process_claas_cph_daily_parallel.py

- Scans: <base>/<group>/<YYYY>/<MM>/<DD>/CPPinYYYYMMDDHHMMSS*.nc
  where <group> is typically {np, sp}.

- For each day directory, it runs a single CDO call:
    -timmean( -gtc,0( -mergetime( -selvar,cph each_file ... ) ) )

- Runs days in PARALLEL with a fixed number of workers.

Output layout:
  <output_root>/<group>/<YYYY>/<MM>/<YYYYMMDD>_timmean.nc

Usage:
  python process_claas_cph_daily_parallel.py \
      --base /wolke_scratch/dnikolo/CLAAS_Data \
      --output /wolke_scratch/dnikolo/processed_daily \
      --year 2010 \
      --workers 8
"""

import os
import re
import glob
import argparse
import subprocess
from datetime import date, timedelta
from concurrent.futures import ProcessPoolExecutor, as_completed
from functools import partial

# Match CPPin files, e.g. CPPin20100101000000405SVMSG01MD.nc
CPP_RE = re.compile(r"^CPPin(\d{8})\d{6}.*\.nc$")

def iter_days_of_year(year: int):
    d = date(year, 1, 1)
    last = date(year, 12, 31)
    one = timedelta(days=1)
    while d <= last:
        yield d
        d += one

def list_day_files(base_root: str, group: str, day_str: str):
    """
    Return sorted list of CPPin files for the given group and YYYYMMDD.
    It only picks files whose name also embeds the same YYYYMMDD.
    """
    y, m, dd = day_str[:4], day_str[4:6], day_str[6:8]
    day_dir = os.path.join(base_root, group, y, m, dd)
    if not os.path.isdir(day_dir):
        return []
    # Ensure date inside the filename matches the folder day.
    candidates = sorted(glob.glob(os.path.join(day_dir, f"CPPin{day_str}*.nc")))
    # Extra safety in case of stray files:
    return [fp for fp in candidates if CPP_RE.match(os.path.basename(fp))]

def build_cdo_cmd(day_files, out_file, varname="cph", silent=True):
    """
    One-call CDO pipeline:
      cdo [-s] -L -timmean -gtc,0 -mergetime  (-selvar,<varname> f1) ...  out.nc
    """
    cmd = ['cdo']
    if silent:
        cmd.append('-s')
    cmd += ['-L', '-timmean', '-gtc,0', '-mergetime']
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

def process_one_day(task, varname="cph", silent=True, verbose=False, overwrite=False, output_root=None):
    group, day, day_files = task
    y, m = day[:4], day[4:6]
    out_dir = os.path.join(output_root, group, y, m)
    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, f'{day}_timmean.nc')

    if (not overwrite) and os.path.exists(out_file):
        if verbose:
            print(f"SKIP exists: {out_file}")
        return (day, True, "exists")

    cmd = build_cdo_cmd(day_files, out_file, varname=varname, silent=silent)
    run_cdo(cmd, verbose=verbose)
    return (day, True, "ok")

def discover_groups(base_root: str):
    # Prefer the standard np/sp if present; otherwise include all subdirs.
    preferred = [d for d in ['np', 'sp'] if os.path.isdir(os.path.join(base_root, d))]
    if preferred:
        return preferred
    # Fallback: any directory directly under base_root.
    return sorted([os.path.basename(p) for p in glob.glob(os.path.join(base_root, '*')) if os.path.isdir(p)])

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='/wolke_scratch/dnikolo/CLAAS_Data', help='Base CLAAS input root')
    ap.add_argument('--output', default='/wolke_scratch/dnikolo/processed_daily', help='Output root')
    ap.add_argument('--year', required=True, help='Year to process (e.g., 2010)')
    ap.add_argument('--workers', type=int, default=4, help='Parallel CDO jobs')
    ap.add_argument('--verbose', action='store_true', help='Print CDO commands')
    ap.add_argument('--no-silent', action='store_true', help='Disable CDO -s')
    ap.add_argument('--overwrite', action='store_true', help='Overwrite existing outputs')
    ap.add_argument('--var', default='cph', help='Variable name to extract (default: cph)')
    ap.add_argument('--groups', nargs='*', help='Limit to these groups (e.g., np sp). Default: auto-detect.')
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
        silent=silent,
        verbose=args.verbose,
        overwrite=args.overwrite,
        output_root=args.output
    )

    done = 0
    failed = 0
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
