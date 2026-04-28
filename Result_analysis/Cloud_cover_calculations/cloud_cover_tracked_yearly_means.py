#!/usr/bin/env python3
import os
import re
import glob
import argparse
import subprocess
from concurrent.futures import ProcessPoolExecutor, as_completed
from functools import partial

# Match Agg names like Agg_03_T_06_00 (captures 06 and 00)
AGG_NAME_RE = re.compile(r"^Agg_03_T_(\d+)_([0-9]+)$")

def should_include_agg(name: str, diff_required = 6) -> bool:
    m = AGG_NAME_RE.match(name)
    if not m:
        return False
    if diff_required is None:
        return True
    a, b = int(m.group(1)), int(m.group(2))
    return (a - b) == diff_required

def cdo(cmd, verbose=False):
    env = dict(os.environ)
    env.setdefault('OMP_NUM_THREADS', '1')  # avoid oversubscription when parallel
    if verbose:
        print("CMD:", " ".join(cmd))
    subprocess.run(cmd, check=True, env=env)

def per_agg_mean(agg_dir: str, silent=True, overwrite=False, verbose=False):
    """
    Do: cdo -L -timmean -mergetime <all daily files> -> <agg_mean.nc>
    Returns path to the agg_mean file or None if skipped.
    """
    group = os.path.basename(os.path.dirname(agg_dir))  # np or sp
    agg = os.path.basename(agg_dir)

    daily_files = sorted(glob.glob(os.path.join(agg_dir, '*_timmean.nc')))
    if not daily_files:
        if verbose:
            print(f"NO DAILY FILES: {group}/{agg}")
        return None

    out_file = os.path.join(agg_dir, 'agg_period_mean.nc')
    if (not overwrite) and os.path.exists(out_file):
        if verbose:
            print(f"SKIP exists: {out_file}")
        return out_file

    # cdo -L -timmean -mergetime daily* -> agg_period_mean.nc
    cmd = ['cdo']
    if silent:
        cmd.append('-s')
    cmd += ['-L', '-timmean', '-mergetime']
    cmd += daily_files
    cmd += [out_file]
    cdo(cmd, verbose=verbose)
    return out_file

def sum_group_means(group_dir: str, output_path: str, diff_required=6, silent=True, overwrite=False, verbose=False):
    """
    Sum all agg_period_mean.nc files under group_dir (np or sp) that pass the filter.
    """
    agg_dirs = [d for d in sorted(glob.glob(os.path.join(group_dir, 'Agg_*')))
                if os.path.isdir(d) and should_include_agg(os.path.basename(d), diff_required)]
    mean_files = []
    for d in agg_dirs:
        mf = os.path.join(d, 'agg_period_mean.nc')
        if os.path.exists(mf):
            mean_files.append(mf)

    if not mean_files:
        if verbose:
            print(f"NO MEANS to sum in {group_dir}")
        return None

    if (not overwrite) and os.path.exists(output_path):
        if verbose:
            print(f"SKIP exists: {output_path}")
        return output_path

    # cdo -L enssum <agg1_mean> <agg2_mean> ... -> <output_path>
    cmd = ['cdo']
    if silent:
        cmd.append('-s')
    cmd += ['-L', 'enssum']
    cmd += mean_files
    cmd += [output_path]
    cdo(cmd, verbose=verbose)
    return output_path

def main():
    ap = argparse.ArgumentParser(description="Reduce daily timmeans to per-Agg period means, then sum per group.")
    ap.add_argument('--base', default='/wolke_scratch/dnikolo/processed_daily', help='Base directory with np/ and sp/')
    ap.add_argument('--groups', default='np,sp', help='Comma-separated groups to process (default: np,sp)')
    ap.add_argument('--workers', type=int, default=4, help='Parallel jobs for per-Agg means')
    ap.add_argument('--diff', type=int, default=6, help='Keep Aggs where first-second == diff (set to -1 to disable filter)')
    ap.add_argument('--overwrite', action='store_true', help='Overwrite existing outputs')
    ap.add_argument('--no-silent', action='store_true', help='Disable CDO -s')
    ap.add_argument('--verbose', action='store_true', help='Print commands')
    args = ap.parse_args()

    groups = [g.strip() for g in args.groups.split(',') if g.strip()]
    silent = (not args.no_silent)
    diff_required = None if args.diff < 0 else args.diff

    # Collect Agg dirs (filtered)
    jobs = []
    for g in groups:
        group_dir = os.path.join(args.base, g)
        if not os.path.isdir(group_dir):
            continue
        for agg_dir in sorted(glob.glob(os.path.join(group_dir, 'Agg_*'))):
            agg_name = os.path.basename(agg_dir)
            if should_include_agg(agg_name, diff_required):
                jobs.append(agg_dir)

    if not jobs:
        print("No matching Agg_* directories found.")
        return

    # Compute per-Agg means in parallel
    worker = partial(per_agg_mean, silent=silent, overwrite=args.overwrite, verbose=args.verbose)
    done = 0
    produced = []
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(worker, d): d for d in jobs}
        for fut in as_completed(futs):
            agg_dir = futs[fut]
            try:
                out = fut.result()
                done += 1
                tag = out if out else "SKIPPED"
                print(f"[{done}/{len(jobs)}] {agg_dir} -> {tag}")
                if out:
                    produced.append(out)
            except subprocess.CalledProcessError as e:
                done += 1
                print(f"[{done}/{len(jobs)}] {agg_dir} -> ERROR: {e}")

    # Sum per-group
    for g in groups:
        group_dir = os.path.join(args.base, g)
        if not os.path.isdir(group_dir):
            continue
        group_sum = os.path.join(group_dir, 'group_sum_timmean.nc')
        out = sum_group_means(group_dir, group_sum, diff_required=diff_required,
                              silent=silent, overwrite=args.overwrite, verbose=args.verbose)
        if out:
            print(f"{g}: summed means -> {out}")
        else:
            print(f"{g}: nothing to sum.")

if __name__ == '__main__':
    main()