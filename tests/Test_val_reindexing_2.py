#!/usr/bin/env python3
"""
Diagnostic checks for data_postprocessing.val_reindexing.

Run synthetic checks:
    python runscripts/Test_val_reindexing.py

Run synthetic checks plus a real validation NetCDF file:
    python runscripts/Test_val_reindexing.py --validation-file /path/to/DD_CT_YYYYMMDD_HHMM.nc
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

try:
    from glaciation_time_estimator.data_postprocessing.val_reindexing import (  # noqa: E402
        build_val_index,
        match_val_to_cloud,
    )
except ModuleNotFoundError as exc:
    if exc.name == "scipy":
        raise SystemExit(
            "Missing dependency: scipy. Install the project dependencies first, for example:\n"
            "    python -m pip install -e .\n"
            "or, with test extras:\n"
            "    python -m pip install -e '.[test]'"
        ) from exc
    raise


def assert_array_equal(name, actual, expected):
    np.testing.assert_array_equal(actual, expected)
    print(f"PASS {name}")


def assert_equal(name, actual, expected):
    if actual != expected:
        raise AssertionError(f"{name}: expected {expected!r}, got {actual!r}")
    print(f"PASS {name}")


def run_synthetic_checks():
    print("Synthetic rectilinear-grid checks")

    val_lat = np.array([10.0, 20.0])
    val_lon = np.array([30.0, 40.0, 50.0])
    val_cph = np.array([[101.0, 102.0, 103.0], [201.0, 202.0, 203.0]])
    val_cth = val_cph + 1000.0
    val_cth_std = val_cph + 2000.0

    index = build_val_index(val_lat, val_lon)
    assert_equal("1D lat/lon axes become a 2D validation grid", index["shape"], val_cph.shape)

    cph, cth, cth_std = match_val_to_cloud(
        index,
        val_cph,
        val_cth,
        val_cth_std,
        cloud_lat=np.array([10.1, 19.9]),
        cloud_lon=np.array([49.8, 30.2]),
    )

    assert_array_equal("CPH nearest cells preserve row/column orientation", cph, np.array([103.0, 201.0]))
    assert_array_equal("CTH nearest cells preserve row/column orientation", cth, np.array([1103.0, 1201.0]))
    assert_array_equal("CTH std nearest cells preserve row/column orientation", cth_std, np.array([2103.0, 2201.0]))

    val_lat = np.array([0.0])
    val_lon = np.array([179.0, 181.0])
    val_cph = np.array([[10.0, 20.0]])
    val_cth = val_cph + 100.0
    val_cth_std = val_cph + 200.0

    index = build_val_index(val_lat, val_lon)
    cph, _, _ = match_val_to_cloud(
        index,
        val_cph,
        val_cth,
        val_cth_std,
        cloud_lat=np.array([0.0, 0.0, 0.0]),
        cloud_lon=np.array([179.2, -179.2, 180.8]),
    )
    assert_array_equal("0..360 validation lon matches wrapped cloud lon", cph, np.array([10.0, 20.0, 20.0]))

    cph, cth, cth_std = match_val_to_cloud(
        index,
        val_cph,
        val_cth,
        val_cth_std,
        cloud_lat=np.array([np.nan, 0.0]),
        cloud_lon=np.array([0.0, np.inf]),
        fill_value=-99.0,
    )
    assert_array_equal("non-finite CPH queries use fill value", cph, np.array([-99.0, -99.0]))
    assert_array_equal("non-finite CTH queries use fill value", cth, np.array([-99.0, -99.0]))
    assert_array_equal("non-finite CTH std queries use fill value", cth_std, np.array([-99.0, -99.0]))

    cph, _, _ = match_val_to_cloud(
        index,
        val_cph,
        val_cth,
        val_cth_std,
        cloud_lat=np.array([0.0, 1.0]),
        cloud_lon=np.array([179.0, 179.0]),
        max_km=50.0,
        fill_value=-1.0,
    )
    assert_array_equal("max_km gate rejects distant matches", cph, np.array([10.0, -1.0]))


def _nearest_direct(lat_axis, lon_axis, query_lat, query_lon):
    lat2d, lon2d = np.meshgrid(lat_axis, ((lon_axis + 180.0) % 360.0) - 180.0, indexing="ij")
    query_lon = ((query_lon + 180.0) % 360.0) - 180.0
    d2 = (lat2d - query_lat) ** 2 + (lon2d - query_lon) ** 2
    return np.unravel_index(np.argmin(d2), d2.shape)


def run_real_file_checks(validation_file):
    try:
        import xarray as xr
    except ImportError as exc:
        raise RuntimeError("xarray is required for --validation-file checks") from exc

    print(f"\nReal validation-file checks: {validation_file}")
    with xr.open_dataset(validation_file) as ds:
        lat = ds["lat_bin"].values
        lon = ds["lon_bin"].values
        cph = ds["cph_mean"].isel(time_bin=0).values
        cth = ds["cth_mean"].isel(time_bin=0).values
        cth_std = ds["cth_std"].isel(time_bin=0).values

        print(f"lat_bin dims/shape: {ds['lat_bin'].dims} {lat.shape}")
        print(f"lon_bin dims/shape: {ds['lon_bin'].dims} {lon.shape}")
        print(f"cph_mean dims/shape: {ds['cph_mean'].dims} {ds['cph_mean'].shape}")
        print(f"lon_bin range: {np.nanmin(lon):.6g} to {np.nanmax(lon):.6g}")

    if lat.ndim != 1 or lon.ndim != 1:
        raise AssertionError("This script expects 1D lat_bin/lon_bin axes for the real-file check")

    assert_equal("validation data shape matches lat/lon axes", cph.shape, (lat.size, lon.size))

    index = build_val_index(lat, lon)
    assert_equal("real validation index shape", index["shape"], cph.shape)

    sample_indices = [
        (0, 0),
        (lat.size // 2, lon.size // 2),
        (lat.size - 1, lon.size - 1),
    ]
    query_lat = np.array([lat[i] for i, _ in sample_indices], dtype=np.float64)
    query_lon = np.array([lon[j] for _, j in sample_indices], dtype=np.float64)

    got_cph, got_cth, got_cth_std = match_val_to_cloud(index, cph, cth, cth_std, query_lat, query_lon)
    expected_cph = np.array([cph[i, j] for i, j in sample_indices], dtype=np.float64)
    expected_cth = np.array([cth[i, j] for i, j in sample_indices], dtype=np.float64)
    expected_cth_std = np.array([cth_std[i, j] for i, j in sample_indices], dtype=np.float64)

    np.testing.assert_allclose(got_cph, expected_cph, equal_nan=True)
    print("PASS exact-grid CPH lookup")
    np.testing.assert_allclose(got_cth, expected_cth, equal_nan=True)
    print("PASS exact-grid CTH lookup")
    np.testing.assert_allclose(got_cth_std, expected_cth_std, equal_nan=True)
    print("PASS exact-grid CTH std lookup")

    probe_lat = np.array([lat[0] + 0.01, lat[lat.size // 2] - 0.01])
    probe_lon = np.array([lon[0] + 0.01, lon[lon.size // 2] - 0.01])
    got_cph, _, _ = match_val_to_cloud(index, cph, cth, cth_std, probe_lat, probe_lon)
    expected = []
    for qlat, qlon in zip(probe_lat, probe_lon):
        i, j = _nearest_direct(lat, lon, qlat, qlon)
        expected.append(cph[i, j])
    np.testing.assert_allclose(got_cph, np.array(expected), equal_nan=True)
    print("PASS nearest-cell CPH lookup matches direct brute-force check")


def parse_args():
    parser = argparse.ArgumentParser(description="Test val_reindexing on synthetic data and optionally one real validation file.")
    parser.add_argument(
        "--validation-file",
        type=Path,
        help="Optional DD_CT_*.nc or MOD_CT_*.nc file to verify against.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    run_synthetic_checks()
    if args.validation_file is not None:
        run_real_file_checks(args.validation_file)
    print("\nAll val_reindexing checks passed.")


if __name__ == "__main__":
    main()
