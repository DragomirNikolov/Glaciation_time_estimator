import os
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest

yaml = pytest.importorskip("yaml")
pytest.importorskip("pyproj")
pytest.importorskip("pyresample")
xr = pytest.importorskip("xarray")

from glaciation_time_estimator.auxiliary_func.config_reader import read_config
from glaciation_time_estimator.data_postprocessing.val_reindexing import (
    build_val_index,
    match_val_to_cloud,
)
from glaciation_time_estimator.data_preprocessing.Resample_data import ProjectionTransformer


def _config_from_env():
    config_fp = os.environ.get("GTE_TEST_CONFIG")
    if not config_fp:
        pytest.skip("Set GTE_TEST_CONFIG to enable real-data smoke tests.")
    config_path = Path(config_fp)
    if not config_path.is_file():
        pytest.skip(f"GTE_TEST_CONFIG does not point to a readable file: {config_fp}")
    return read_config(str(config_path))


def _existing_first_path(paths_by_pole):
    for path in paths_by_pole.values():
        if Path(path).is_file():
            return path
    pytest.skip("No readable auxiliary file found in config.")


def _claas_paths_for_start_time(config, pole):
    time = config["start_time"]
    if time > config["struct_boundary_date"]:
        suffix = "405SVMSGI1MD.nc"
    else:
        suffix = "405SVMSG01MD.nc"
    cpp = Path(config["CLAAS_fp"]) / pole / time.strftime(f"%Y/%m/%d/CPPin%Y%m%d%H%M%S{suffix}")
    ctx = Path(config["CLAAS_fp"]) / pole / time.strftime(f"%Y/%m/%d/CTXin%Y%m%d%H%M%S{suffix}")
    return cpp, ctx


def _validation_path_for_start_time(config):
    mode = config.get("validation_mode", "")
    if mode == "dardar":
        rel = config["start_time"].strftime("%Y/%m/%d/DD_CT_%Y%m%d_%H%M.nc")
    elif mode == "modis":
        rel = config["start_time"].strftime("%Y/%m/%d/MOD_CT_%Y%m%d_%H%M.nc")
    else:
        pytest.skip("Config has no DARDAR/MODIS validation mode.")
    return Path(config["val_CPH_fp"]) / rel


def test_real_aux_file_builds_projection_geometry():
    config = _config_from_env()
    aux_fp = _existing_first_path(config["aux_fps"])

    with xr.open_dataset(aux_fp) as aux:
        transformer = ProjectionTransformer()
        transformer.generate_lat_lon_prj(aux)

    assert transformer.nx > 0
    assert transformer.ny > 0
    assert np.isfinite(transformer.bounds).all()
    assert transformer.new_cord_lon.shape == (transformer.nx,)
    assert transformer.new_cord_lat.shape == (transformer.ny,)


def test_real_one_timestep_nearest_neighbor_remap_smoke():
    config = _config_from_env()
    pole = config["pole_folders"][0]
    aux_fp = config["aux_fps"][pole]
    cpp_fp, ctx_fp = _claas_paths_for_start_time(config, pole)

    missing = [str(path) for path in (Path(aux_fp), cpp_fp, ctx_fp) if not path.is_file()]
    if missing:
        pytest.skip(f"Missing real-data smoke input(s): {missing}")

    with xr.open_dataset(aux_fp) as aux, xr.open_dataset(ctx_fp) as ctx:
        transformer = ProjectionTransformer()
        transformer.generate_lat_lon_prj(aux)
        remapped = transformer.remap_data(
            ctx["ctt"].isel(time=slice(0, 1)),
            n_resample_procs=1,
            method="nn",
        )

    assert remapped.shape == (1, transformer.ny, transformer.nx)
    finite_fraction = np.count_nonzero(np.isfinite(remapped) & (remapped != -1)) / remapped.size
    assert finite_fraction > 0.01
    assert np.nanmin(transformer.new_cord_lat) >= min(transformer.bounds[2], transformer.bounds[3])
    assert np.nanmax(transformer.new_cord_lat) <= max(transformer.bounds[2], transformer.bounds[3])


def test_real_validation_colocation_smoke():
    config = _config_from_env()
    val_fp = _validation_path_for_start_time(config)
    if not val_fp.is_file():
        pytest.skip(f"Missing validation smoke input: {val_fp}")

    with xr.open_dataset(val_fp) as val:
        lat_name = "lat_bin"
        lon_name = "lon_bin"
        required = {lat_name, lon_name, "cph_mean", "cth_mean", "cth_std"}
        missing = required.difference(val.variables)
        if missing:
            pytest.skip(f"Validation file is missing expected variables: {sorted(missing)}")

        val_lat = val[lat_name].values
        val_lon = val[lon_name].values
        val_cph = val["cph_mean"].isel(time_bin=0).values
        val_cth = val["cth_mean"].isel(time_bin=0).values
        val_cth_std = val["cth_std"].isel(time_bin=0).values

    index = build_val_index(val_lat, val_lon)
    if np.asarray(val_lat).ndim == 1 and np.asarray(val_lon).ndim == 1:
        sample_lat = np.asarray(val_lat)[:5]
        sample_lon = np.asarray(val_lon)[:5]
        if sample_lat.size != sample_lon.size:
            n = min(sample_lat.size, sample_lon.size)
            sample_lat = sample_lat[:n]
            sample_lon = sample_lon[:n]
    else:
        sample_lat = np.asarray(val_lat).ravel()[:5]
        sample_lon = np.asarray(val_lon).ravel()[:5]

    cph, cth, cth_std = match_val_to_cloud(
        index,
        val_cph,
        val_cth,
        val_cth_std,
        sample_lat,
        sample_lon,
    )

    assert cph.shape == sample_lat.shape
    assert cth.shape == sample_lat.shape
    assert cth_std.shape == sample_lat.shape
