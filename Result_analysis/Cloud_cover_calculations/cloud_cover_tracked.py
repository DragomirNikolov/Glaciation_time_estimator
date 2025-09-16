#!/usr/bin/env python3
"""
process_cloudtracks_daily_parallel.py

- Scans: /wolke_scratch/dnikolo/Euler_backup/{np,sp}/Agg_*/
- For each date-range dir (e.g. 20100101.0000_20100115.0000):
    - Groups cloudtracks_YYYYMMDD_HHMMSS.nc by day
    - For each day, runs: timmean(gtc(mergetime(selvar(feature_number, each file))))
      using a single CDO call (no intermediates)

- Runs days in PARALLEL with a fixed number of workers.

Output layout:
  <output_root>/<group>/<agg_name>/<range_name>/<YYYYMMDD>_timmean.nc

Usage:
  python process_cloudtracks_daily_parallel.py \
      --base /wolke_scratch/dnikolo/Euler_backup \
      --output /wolke_scratch/dnikolo/processed_daily \
      --year 2010 \
      --workers 8
"""

import os
import re
import glob
import argparse
import subprocess
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from functools import partial

DATE_RE = re.compile(r"cloudtracks_(\d{8})_\d{6}\.nc$")
# Match only names like Agg_03_T_06_00 etc.
AGG_NAME_RE = re.compile(r"^Agg_03_T_(\d+)_([0-9]+)$")

def should_include_agg_dir(agg_path: str) -> bool:
    """
    Keep only directories whose name looks like Agg_03_T_A_B and (A - B) == 6.
    """
    name = os.path.basename(agg_path)
    m = AGG_NAME_RE.match(name)
    if not m:
        return False
    a, b = int(m.group(1)), int(m.group(2))
    return (a - b) == 6

def find_agg_dirs(base_root: str):
    # e.g. /.../Euler_backup/{np,sp}/Agg_03_T_06_00
    pattern = os.path.join(base_root, '*', 'Agg_*')
    all_dirs = sorted(d for d in glob.glob(pattern) if os.path.isdir(d))
    return [d for d in all_dirs if should_include_agg_dir(d)]

def list_day_files_in_range(range_dir: str, year_prefix: str):
    range_name = os.path.basename(range_dir)
    pixel_dir = os.path.join(range_dir, 'pixel_path_tracking', range_name)
    if not os.path.isdir(pixel_dir):
        return {}
    nc_files = sorted(glob.glob(os.path.join(pixel_dir, f'cloudtracks_{year_prefix}*.nc')))
    files_by_day = defaultdict(list)
    for fp in nc_files:
        m = DATE_RE.search(os.path.basename(fp))
        if m:
            files_by_day[m.group(1)].append(fp)
    return files_by_day

def build_cdo_cmd(day_files, out_file, silent=True):
    """
    One-call CDO pipeline:
      cdo [-s] -L -timmean -gtc,0 -mergetime  (-selvar,feature_number f1) ...  out.nc
    Apply -selvar per input stream to avoid metadata mismatches.
    """
    cmd = ['cdo']
    if silent:
        cmd.append('-s')
    cmd += ['-L', '-timmean', '-gtc,0', '-mergetime']
    for f in day_files:
        cmd += ['-selvar,cph_filtered', f]
    cmd.append(out_file)
    return cmd

def run_cdo(cmd, verbose=False):
    env = dict(os.environ)
    env.setdefault('OMP_NUM_THREADS', '1')  # no oversubscription when parallel
    if verbose:
        print("CMD:", ' '.join(cmd))
    subprocess.run(cmd, check=True, env=env)

def process_one_day(task, silent=True, verbose=False, overwrite=False):
    group, agg_name, range_name, day, day_files, output_root = task
    out_dir = os.path.join(output_root, group, agg_name)
    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, f'{day}_timmean.nc')

    if (not overwrite) and os.path.exists(out_file):
        if verbose:
            print(f"SKIP exists: {out_file}")
        return (day, True, "exists")

    cmd = build_cdo_cmd(day_files, out_file, silent=silent)
    run_cdo(cmd, verbose=verbose)
    return (day, True, "ok")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='/nfs/n2o/wolke_scratch/dnikolo/Euler_backup', help='Base input root')
    ap.add_argument('--output', default='/nfs/n2o/wolke_scratch/dnikolo/processed_daily', help='Output root')
    ap.add_argument('--year', default='2010', help='Year prefix to process (e.g., 2010)')
    ap.add_argument('--workers', type=int, default=4, help='Parallel CDO jobs')
    ap.add_argument('--verbose', action='store_true', help='Print CDO commands')
    ap.add_argument('--no-silent', action='store_true', help='Disable CDO -s')
    ap.add_argument('--overwrite', action='store_true', help='Overwrite existing outputs')
    args = ap.parse_args()

    agg_dirs = find_agg_dirs(args.base)
    if not agg_dirs:
        print(f"No matching Agg_03_T_*_* (A-B=6) directories under {args.base}")
        return

    tasks = []
    for agg_dir in agg_dirs:
        group = os.path.basename(os.path.dirname(agg_dir))  # np or sp
        agg_name = os.path.basename(agg_dir)
        range_dirs = sorted(glob.glob(os.path.join(agg_dir, f'{args.year}*_*')))
        for range_dir in range_dirs:
            range_name = os.path.basename(range_dir)
            files_by_day = list_day_files_in_range(range_dir, args.year)
            for day, day_files in sorted(files_by_day.items()):
                if not day_files:
                    continue
                tasks.append((group, agg_name, range_name, day, day_files, args.output))

    total = len(tasks)
    print(f"Discovered {total} day-jobs in {len(agg_dirs)} filtered Agg dirs.")
    if total == 0:
        return

    silent = (not args.no_silent)
    worker = partial(process_one_day, silent=silent, verbose=args.verbose, overwrite=args.overwrite)

    done = 0
    failed = 0
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(worker, t): t for t in tasks}
        for fut in as_completed(futures):
            group, agg_name, range_name, day, *_ = futures[fut]
            try:
                _, ok, msg = fut.result()
                done += 1
                tag = "OK" if ok else "SKIP"
                print(f"[{done}/{total}] {group}/{agg_name}/{range_name}/{day}: {tag} ({msg})")
            except subprocess.CalledProcessError as e:
                failed += 1
                done += 1
                print(f"[{done}/{total}] {group}/{agg_name}/{range_name}/{day}: ERROR -> {e}")

    if failed:
        print(f"Completed with {failed} failures.")
    else:
        print("All done.")

if __name__ == '__main__':
    main()
