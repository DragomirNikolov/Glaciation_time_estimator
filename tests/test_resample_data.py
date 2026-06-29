import numpy as np
import pytest

pytest.importorskip("pyproj")
pytest.importorskip("pyresample")
xr = pytest.importorskip("xarray")

from glaciation_time_estimator.data_preprocessing.Resample_data import ProjectionTransformer


def _regular_aux_dataset(lat_values=None, lon_values=None):
    if lat_values is None:
        lat_values = np.array([-1.0, 0.0, 1.0])
    if lon_values is None:
        lon_values = np.array([10.0, 11.0, 12.0])

    lat2d = np.tile(lat_values[:, np.newaxis], (1, lon_values.size))
    lon2d = np.tile(lon_values[np.newaxis, :], (lat_values.size, 1))

    return xr.Dataset(
        {
            "lat": (("time", "y", "x"), lat2d[np.newaxis, :, :]),
            "lon": (("time", "y", "x"), lon2d[np.newaxis, :, :]),
        }
    )


def test_generate_lat_lon_prj_sets_bounds_shape_and_target_coordinates():
    aux = _regular_aux_dataset()
    transformer = ProjectionTransformer()

    transformer.generate_lat_lon_prj(aux)

    assert transformer.ny == 3
    assert transformer.nx == 3
    np.testing.assert_allclose(transformer.bounds, [10.0, 12.0, -1.0, 1.0])
    np.testing.assert_allclose(transformer.new_cord_lon, np.array([10.0, 11.0, 12.0]))
    np.testing.assert_allclose(transformer.new_cord_lat, np.array([-1.0, 0.0, 1.0]))


def test_nn_remap_preserves_regular_grid_values_with_current_y_flip():
    aux = _regular_aux_dataset()
    transformer = ProjectionTransformer()
    transformer.generate_lat_lon_prj(aux)

    values = np.array(
        [
            [10.0, 11.0, 12.0],
            [20.0, 21.0, 22.0],
            [30.0, 31.0, 32.0],
        ]
    )
    field = xr.DataArray(
        values[np.newaxis, :, :],
        dims=("time", "y", "x"),
    )

    remapped = transformer.remap_data(
        field,
        n_resample_procs=1,
        radius_of_influence=200000,
        epsilon=0,
        method="nn",
    )

    assert remapped.shape == (1, 3, 3)
    np.testing.assert_allclose(remapped[0], np.flip(values, axis=0))


def test_nn_remap_uses_fill_value_when_radius_is_too_small():
    aux = _regular_aux_dataset()
    transformer = ProjectionTransformer()
    transformer.generate_lat_lon_prj(aux)

    field = xr.DataArray(
        np.arange(9.0).reshape(1, 3, 3),
        dims=("time", "y", "x"),
    )

    remapped = transformer.remap_data(
        field,
        n_resample_procs=1,
        radius_of_influence=1,
        epsilon=0,
        method="nn",
    )

    assert remapped.shape == (1, 3, 3)
    assert np.count_nonzero(remapped == -1) > 0
