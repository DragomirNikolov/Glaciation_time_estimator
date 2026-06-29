import numpy as np

from glaciation_time_estimator.data_postprocessing.val_reindexing import (
    build_val_index,
    match_val_to_cloud,
)


def test_match_val_to_cloud_1d_grid_uses_expected_row_column_values():
    val_lat = np.array([10.0, 20.0])
    val_lon = np.array([30.0, 40.0, 50.0])
    val_cph = np.array([[101.0, 102.0, 103.0], [201.0, 202.0, 203.0]])
    val_cth = val_cph + 1000.0
    val_cth_std = val_cph + 2000.0

    index = build_val_index(val_lat, val_lon)
    cph, cth, cth_std = match_val_to_cloud(
        index,
        val_cph,
        val_cth,
        val_cth_std,
        cloud_lat=np.array([10.1, 19.9]),
        cloud_lon=np.array([49.8, 30.2]),
    )

    np.testing.assert_array_equal(cph, np.array([103.0, 201.0]))
    np.testing.assert_array_equal(cth, np.array([1103.0, 1201.0]))
    np.testing.assert_array_equal(cth_std, np.array([2103.0, 2201.0]))


def test_match_val_to_cloud_2d_grid_preserves_validation_array_orientation():
    val_lat = np.array([[0.0, 0.0], [1.0, 1.0]])
    val_lon = np.array([[10.0, 20.0], [10.0, 20.0]])
    val_cph = np.array([[11.0, 12.0], [21.0, 22.0]])
    val_cth = val_cph + 100.0
    val_cth_std = val_cph + 200.0

    index = build_val_index(val_lat, val_lon)
    cph, cth, cth_std = match_val_to_cloud(
        index,
        val_cph,
        val_cth,
        val_cth_std,
        cloud_lat=np.array([[0.05, 0.95], [1.1, -0.1]]),
        cloud_lon=np.array([[19.9, 20.1], [9.9, 10.2]]),
    )

    np.testing.assert_array_equal(cph, np.array([[12.0, 22.0], [21.0, 11.0]]))
    np.testing.assert_array_equal(cth, np.array([[112.0, 122.0], [121.0, 111.0]]))
    np.testing.assert_array_equal(cth_std, np.array([[212.0, 222.0], [221.0, 211.0]]))


def test_match_val_to_cloud_wraps_longitudes_around_dateline():
    val_lat = np.array([0.0])
    val_lon = np.array([-179.0, 179.0])
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
        cloud_lon=np.array([181.0, -179.2, 178.8]),
    )

    np.testing.assert_array_equal(cph, np.array([10.0, 10.0, 20.0]))


def test_match_val_to_cloud_returns_fill_for_non_finite_queries():
    val_lat = np.array([0.0])
    val_lon = np.array([0.0])
    val_cph = np.array([[1.0]])
    val_cth = np.array([[2.0]])
    val_cth_std = np.array([[3.0]])

    index = build_val_index(val_lat, val_lon)
    cph, cth, cth_std = match_val_to_cloud(
        index,
        val_cph,
        val_cth,
        val_cth_std,
        cloud_lat=np.array([np.nan, 0.0]),
        cloud_lon=np.array([0.0, np.inf]),
        fill_value=-99.0,
    )

    np.testing.assert_array_equal(cph, np.array([-99.0, -99.0]))
    np.testing.assert_array_equal(cth, np.array([-99.0, -99.0]))
    np.testing.assert_array_equal(cth_std, np.array([-99.0, -99.0]))


def test_match_val_to_cloud_applies_max_km_gate():
    val_lat = np.array([0.0])
    val_lon = np.array([0.0])
    val_cph = np.array([[1.0]])
    val_cth = np.array([[2.0]])
    val_cth_std = np.array([[3.0]])

    index = build_val_index(val_lat, val_lon)
    cph, cth, cth_std = match_val_to_cloud(
        index,
        val_cph,
        val_cth,
        val_cth_std,
        cloud_lat=np.array([0.0, 1.0]),
        cloud_lon=np.array([0.0, 0.0]),
        max_km=50.0,
        fill_value=-1.0,
    )

    np.testing.assert_array_equal(cph, np.array([1.0, -1.0]))
    np.testing.assert_array_equal(cth, np.array([2.0, -1.0]))
    np.testing.assert_array_equal(cth_std, np.array([3.0, -1.0]))
