#!/usr/bin/env python3
"""
process_claas_cloud_classes_parallel.py

Re-implements your day-by-day CDO workflow (merging CTX+CPP, AUX merge,
filters, category areas, fldsum, fractions, timmean) in Python using
multiprocessing (ProcessPoolExecutor).

New: per-group AUX support
--------------------------
- You can provide different AUX files for np and sp via --aux-np and --aux-sp.
- If not provided, the script falls back to --aux (same for all groups).
- If none are provided, it tries <base>/<group>/CM_SAF_CLAAS3_L2_AUX.nc.

Key features
------------
- Scans <base>/<group>/<YYYY>/<MM>/<DD>/ for CTXin* and CPPin* files.
- Runs each *day* as an independent job in parallel.
- Uses temporary intermediates per day and cleans them up (unless --keep-intermediate).
- Skips days that already have an output unless --overwrite is used.
- Lets you pick groups (e.g., np sp) or auto-detect from <base>.

Output layout
-------------
  <output_root>/<group>/<YYYY>_<MM>_<DD>.nc

Examples
--------
# Different AUX for np and sp
python process_claas_cloud_classes_parallel.py \
  --base /wolke_scratch/dnikolo/CLAAS_Data \
  --output /wolke_scratch/dnikolo/Cloud_cover_by_class \
  --year 2009 --groups sp np --workers 8 --verbose \
  --aux-np /wolke_scratch/dnikolo/CLAAS_Data/np/CM_SAF_CLAAS3_L2_AUX.nc \
  --aux-sp /wolke_scratch/dnikolo/CLAAS_Data/sp/CM_SAF_CLAAS3_L2_AUX.nc

# Single AUX for all groups
python process_claas_cloud_classes_parallel.py \
  --base /wolke_scratch/dnikolo/CLAAS_Data \
  --output /wolke_scratch/dnikolo/Cloud_cover_by_class \
  --aux /wolke_scratch/dnikolo/CLAAS_Data/sp/CM_SAF_CLAAS3_L2_AUX.nc \
  --year 2009 --groups sp np --workers 8

Notes
-----
- Requires CDO available on PATH. Mirrors your bash pipeline semantics.
- Sets OMP_NUM_THREADS=1 and HDF5_USE_FILE_LOCKING=FALSE to avoid oversubscription
  and HDF5 locking issues on parallel filesystems.
"""

from __future__ import annotations
import os
import re
import glob
import argparse
import shutil
import subprocess
from datetime import date, timedelta
from concurrent.futures import ProcessPoolExecutor, as_completed
from functools import partial
from tempfile import TemporaryDirectory

# Regex to validate filenames and pin the YYYYMMDD embedded in the name
CTX_RE = re.compile(r"^CTXin(\d{8})\d{6}.*\.nc$")
CPP_RE = re.compile(r"^CPPin(\d{8})\d{6}.*\.nc$")


def iter_days_of_year(year: int):
    d = date(year, 1, 1)
    last = date(year, 12, 31)
    one = timedelta(days=1)
    while d <= last:
        yield d
        d += one


def list_day_files(base_root: str, group: str, day_str: str):
    """Return sorted (ctx_files, cpp_files) for given group and YYYYMMDD.
    Only picks files whose names embed the same YYYYMMDD.
    """
    y, m, dd = day_str[:4], day_str[4:6], day_str[6:8]
    day_dir = os.path.join(base_root, group, y, m, dd)
    if not os.path.isdir(day_dir):
        return [], []

    ctx_candidates = sorted(glob.glob(os.path.join(day_dir, f"CTXin{day_str}*.nc")))
    cpp_candidates = sorted(glob.glob(os.path.join(day_dir, f"CPPin{day_str}*.nc")))

    ctx = [fp for fp in ctx_candidates if CTX_RE.match(os.path.basename(fp))]
    cpp = [fp for fp in cpp_candidates if CPP_RE.match(os.path.basename(fp))]
    return ctx, cpp


def discover_groups(base_root: str):
    preferred = [d for d in ["np", "sp"] if os.path.isdir(os.path.join(base_root, d))]
    if preferred:
        return preferred
    return sorted([os.path.basename(p) for p in glob.glob(os.path.join(base_root, "*"))
                   if os.path.isdir(p)])


def run(cmd, verbose=False):
    env = dict(os.environ)
    # Avoid runaway threading when running many CDO jobs
    env.setdefault("OMP_NUM_THREADS", "1")
    # Common HDF5 issue on parallel filesystems
    env.setdefault("HDF5_USE_FILE_LOCKING", "FALSE")
    if verbose:
        print("CMD:", " ".join(cmd))
    subprocess.run(cmd, check=True, env=env)


def build_day_output(output_root: str, group: str, day_str: str) -> str:
    y, m, d = day_str[:4], day_str[4:6], day_str[6:8]
    os.makedirs(os.path.join(output_root, group), exist_ok=True)
    return os.path.join(output_root, group, f"{y}_{m}_{d}.nc")


def resolve_aux_for_group(base_root: str, group: str, aux: str | None, aux_np: str | None, aux_sp: str | None) -> str:
    # Priority: group-specific flag -> global --aux -> default location under base/group
    if group == 'np' and aux_np:
        return aux_np
    if group == 'sp' and aux_sp:
        return aux_sp
    if aux:
        return aux
    candidate = os.path.join(base_root, group, 'CM_SAF_CLAAS3_L2_AUX.nc')
    return candidate


def process_one_day(task, *, output_root: str, overwrite: bool,
                    keep_intermediate: bool = False, verbose: bool = False):
    """Run the full CDO chain for a single (group, day, ctx_files, cpp_files, aux_path) task."""
    group, day_str, ctx_files, cpp_files, aux_path = task

    # Sanity checks
    if not ctx_files:
        return (group, day_str, False, "no CTX files")
    if not cpp_files:
        return (group, day_str, False, "no CPP files")
    if not os.path.isfile(aux_path):
        return (group, day_str, False, f"AUX not found: {aux_path}")

    out_file = build_day_output(output_root, group, day_str)
    if (not overwrite) and os.path.exists(out_file):
        return (group, day_str, True, "exists")

    # Work in a temporary folder for intermediates; same filesystem as outputs if possible
    work_parent = os.path.dirname(out_file)
    os.makedirs(work_parent, exist_ok=True)

    with TemporaryDirectory(prefix=f"claas_tmp_{group}_{day_str}_", dir=work_parent) as tmpdir:
        tmp_ctx = os.path.join(tmpdir, "combined_ctx.nc")
        tmp_cpp = os.path.join(tmpdir, "combined_cpp.nc")
        tmp_total = os.path.join(tmpdir, "combined_total.nc")
        tmp_aux = os.path.join(tmpdir, "combined_aux.nc")
        tmp_class = os.path.join(tmpdir, "classification_fields.nc")
        tmp_area = os.path.join(tmpdir, "area_fields.nc")
        tmp_sum = os.path.join(tmpdir, "class_cover_area.nc")
        tmp_cover = os.path.join(tmpdir, "class_cover.nc")

        # 1) Merge CTX and CPP selections over time
        run(['cdo', '-O', '-L', '-setmissval,0', '-mergetime', '-apply,-selname,ctt,ctp','[',
             *ctx_files,']', tmp_ctx], verbose)
        run(['cdo', '-O', '-L', '-setmissval,0', '-mergetime', '-apply,-selname,cot','[',
             *cpp_files,']', tmp_cpp], verbose)

        # 2) Merge CTX+CPP then AUX
        run(['cdo', '-O', 'merge', tmp_ctx, tmp_cpp, tmp_total], verbose)
        run(['cdo', '-O', 'merge', aux_path, tmp_total, tmp_aux], verbose)

        # 3) Filter / prepare fields
        expr1 = (
            'ctp_filtered=(ctt>237.15)*(ctt<273.15)*(pixel_area<66)*ctp; '
            'cot=cot; '
            'pixel_area=pixel_area'
        )
        run(['cdo', '-O', 'expr', expr1, tmp_aux, tmp_class], verbose)

        # 4) Category areas
        expr2 = (
            'total=(ctp_filtered>0)*(cot>0)*pixel_area; '
            'ci=(ctp_filtered<440)*(ctp_filtered>0)*(cot>0)*(cot<3.6)*pixel_area; '
            'cs=(ctp_filtered<440)*(ctp_filtered>0)*(cot>3.6)*(cot<23)*pixel_area; '
            'dc=(ctp_filtered<440)*(ctp_filtered>0)*(cot>23)*(cot<379)*pixel_area; '
            'ac=(ctp_filtered>=440)*(ctp_filtered<680)*(cot>0)*(cot<3.6)*pixel_area; '
            'as=(ctp_filtered>=440)*(ctp_filtered<680)*(cot>3.6)*(cot<23)*pixel_area; '
            'ns=(ctp_filtered>=440)*(ctp_filtered<680)*(cot>23)*(cot<379)*pixel_area; '
            'cu=(ctp_filtered>=680)*(ctp_filtered<1000)*(cot>0)*(cot<3.6)*pixel_area; '
            'sc=(ctp_filtered>=680)*(ctp_filtered<1000)*(cot>3.6)*(cot<23)*pixel_area; '
            'st=(ctp_filtered>=680)*(ctp_filtered<1000)*(cot>23)*(cot<379)*pixel_area'
        )
        run(['cdo', '-O', 'expr', expr2, tmp_class, tmp_area], verbose)

        # 5) Sum spatially
        run(['cdo', '-O', 'fldsum', tmp_area, tmp_sum], verbose)

        # 6) Fractions
        expr3 = (
            'ci_frac=ci/total; cs_frac=cs/total; dc_frac=dc/total; '
            'ac_frac=ac/total; as_frac=as/total; ns_frac=ns/total; '
            'cu_frac=cu/total; sc_frac=sc/total; st_frac=st/total'
        )
        run(['cdo', '-O', 'expr', expr3, tmp_sum, tmp_cover], verbose)

        # 7) Daily mean over time dimension
        run(['cdo', '-O', '-L', 'timmean', tmp_cover, out_file], verbose)

        if keep_intermediate:
            # Optionally preserve intermediates for debugging
            keep_dir = os.path.join(work_parent, f"debug_{group}_{day_str}")
            os.makedirs(keep_dir, exist_ok=True)
            for p in [tmp_ctx, tmp_cpp, tmp_total, tmp_aux, tmp_class, tmp_area, tmp_sum, tmp_cover]:
                try:
                    shutil.copy2(p, keep_dir)
                except Exception:
                    pass

    return (group, day_str, True, "ok")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='/wolke_scratch/dnikolo/CLAAS_Data', help='Base CLAAS input root')
    ap.add_argument('--output', default='/wolke_scratch/dnikolo/Cloud_cover_by_class', help='Output root')
    ap.add_argument('--aux', help='Single AUX path used for all groups (fallback if group-specific not given)')
    ap.add_argument('--aux-np', dest='aux_np', help='AUX path for the np group')
    ap.add_argument('--aux-sp', dest='aux_sp', help='AUX path for the sp group')
    ap.add_argument('--year', required=True, type=int, help='Year to process (e.g., 2009)')
    ap.add_argument('--groups', nargs='*', help='Limit to these groups, e.g., np sp. Default: auto-detect under --base')
    ap.add_argument('--workers', type=int, default=4, help='Parallel day-jobs')
    ap.add_argument('--overwrite', action='store_true', help='Overwrite existing outputs')
    ap.add_argument('--keep-intermediate', action='store_true', help='Keep per-day temp NetCDFs for debugging')
    ap.add_argument('--verbose', action='store_true', help='Print CDO commands as they run')
    args = ap.parse_args()

    groups = args.groups if args.groups else discover_groups(args.base)
    if not groups:
        raise SystemExit(f"No group directories found under {args.base}")

    # Discover day jobs + resolve AUX per task
    tasks = []
    for group in groups:
        # Determine AUX for this group
        aux_for_group = resolve_aux_for_group(args.base, group, args.aux, args.aux_np, args.aux_sp)
        for d in iter_days_of_year(args.year):
            day = d.strftime('%Y%m%d')
            ctx, cpp = list_day_files(args.base, group, day)
            if ctx and cpp:
                tasks.append((group, day, ctx, cpp, aux_for_group))
    total = len(tasks)
    print(f"Discovered {total} day-jobs across groups: {', '.join(groups)}.")
    if total == 0:
        return

    worker = partial(
        process_one_day,
        output_root=args.output,
        overwrite=args.overwrite,
        keep_intermediate=args.keep_intermediate,
        verbose=args.verbose,
    )

    done = 0
    failed = 0
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(worker, t): t for t in tasks}
        for fut in as_completed(futures):
            group, day, *_ = futures[fut]
            try:
                g, dstr, ok, msg = fut.result()
                done += 1
                y, m, dd = dstr[:4], dstr[4:6], dstr[6:8]
                tag = "OK" if ok and msg == "ok" else ("SKIP" if ok else "MISS")
                print(f"[{done}/{total}] {g}/{y}/{m}/{dd}: {tag} ({msg})")
            except subprocess.CalledProcessError as e:
                failed += 1
                done += 1
                y, m, dd = day[:4], day[4:6], day[6:8]
                print(f"[{done}/{total}] {group}/{y}/{m}/{dd}: ERROR -> {e}")
            except Exception as e:
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

# python process_claas_cloud_classes_parallel.py \
#   --base /wolke_scratch/dnikolo/CLAAS_Data \
#   --output /wolke_scratch/dnikolo/dump/Cloud_cover_by_class \
#   --year 2009 --groups sp np --workers 8 \
#   --aux-np /wolke_scratch/dnikolo/CLAAS_Data/np/CM_SAF_CLAAS3_L2_AUX.nc \
#   --aux-sp /wolke_scratch/dnikolo/CLAAS_Data/sp/CM_SAF_CLAAS3_L2_AUX.nc