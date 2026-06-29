import numpy as np
import ast
from pathlib import Path
from glaciation_time_estimator.data_postprocessing.Tracking_result_analysis import CoordinateTransformer



def test_coordinate_transform_expands_agg_fact_2_in_current_value_order():
    transformer = CoordinateTransformer(target_shape=(4, 4), agg_fact=2)

    lat_ind, lon_ind = transformer.transform(
        lat_ind=np.array([0, 1]),
        lon_ind=np.array([0, 1]),
    )

    np.testing.assert_array_equal(lat_ind, np.array([0, 0, 1, 1, 2, 2, 3, 3]))
    np.testing.assert_array_equal(lon_ind, np.array([0, 1, 0, 1, 2, 3, 2, 3]))


def test_coordinate_transform_expands_single_agg_fact_3_block():
    transformer = CoordinateTransformer(target_shape=(6, 6), agg_fact=3)

    lat_ind, lon_ind = transformer.transform(
        lat_ind=np.array([1]),
        lon_ind=np.array([1]),
    )

    np.testing.assert_array_equal(lat_ind, np.array([3, 3, 3, 4, 4, 4, 5, 5, 5]))
    np.testing.assert_array_equal(lon_ind, np.array([3, 4, 5, 3, 4, 5, 3, 4, 5]))


def test_coordinate_transform_clips_edge_blocks_to_target_shape():
    transformer = CoordinateTransformer(target_shape=(5, 5), agg_fact=3)

    lat_ind, lon_ind = transformer.transform(
        lat_ind=np.array([1]),
        lon_ind=np.array([1]),
    )

    valid = (lat_ind < 5) & (lon_ind < 5)
    np.testing.assert_array_equal(lat_ind[valid], np.array([3, 3, 4, 4]))
    np.testing.assert_array_equal(lon_ind[valid], np.array([3, 4, 3, 4]))
    assert np.all(lat_ind < 5)
    assert np.all(lon_ind < 5)
