import numpy as np
import xarray as xr
from numba import njit, typed, types
import pandas as pd
from datetime import datetime
from glaciation_time_estimator.auxiliary_func.config_reader import read_config
from glaciation_time_estimator.data_postprocessing.Single_cloud_analysis import Cloud
from glaciation_time_estimator.data_postprocessing.Job_result_fp_generator import generate_tracking_filenames
from glaciation_time_estimator.data_postprocessing.val_reindexing import build_val_index, match_val_to_cloud
from multiprocessing import Manager, Pool
from glaciation_time_estimator.auxiliary_func.Nestable_multiprocessing import NestablePool
from functools import partial
import os
# from memory_profiler import profile


# ---------- helper Numba types ----------
coord_type = types.UniTuple(types.int16, 2)        # (row, col)
list_type = types.ListType(coord_type)            # list of coordinates
array2d_type = types.int16[:, ::1]                   # (2, n_pts) C-contiguous
dict_lists_t = types.DictType(types.int64, list_type)
dict_arrays_t = types.DictType(types.int64, array2d_type)


@njit
def extract_cloud_coordinates(cloudtracknumber_field,   # 3-D, shape (1, ny, nx)
                              cloud_id_in_field,        # 1-D array of unique IDs
                              max_size):                # per-cloud hard cap
    """
    Returns a Dict[int -> int16[:, ::1]]
        key   : cloud ID
        value : 2×N array with the exact #pixels (N ≤ max_size)
                 row coords in axis=0, col coords in axis=1
    Memory use ≈ Σ( N_cloud × 2 × 2 bytes ) with zero over-allocation.
    """

    # -- first pass: collect coordinates in typed.Lists --------------------
    coord_lists = typed.Dict.empty(                     # type: Dict[int, List[(int16,int16)]]
        key_type=types.int64,
        value_type=list_type
    )

    ny, nx = cloudtracknumber_field.shape[1:]

    for row in range(ny):
        for col in range(nx):
            cid = cloudtracknumber_field[0, row, col]
            if cid == 0:
                continue          # background pixel – ignore

            if cid not in coord_lists:
                coord_lists[cid] = typed.List.empty_list(coord_type)

            lst = coord_lists[cid]
            if len(lst) < max_size:              # honour the user-supplied cap
                lst.append((np.int16(row), np.int16(col)))

    # -- second pass: pack each list into a perfectly-sized 2×N array ------
    result = typed.Dict.empty(                     # type: Dict[int, int16[:,::1]]
        key_type=types.int64,
        value_type=array2d_type
    )

    for cid in coord_lists:
        lst = coord_lists[cid]
        n = len(lst)
        arr = np.empty((2, n), dtype=np.int16)

        for i in range(n):
            rc = lst[i]
            arr[0, i] = rc[0]     # row
            arr[1, i] = rc[1]     # col

        result[cid] = arr

    return result


class CoordinateTransformer:
    def __init__(self, target_shape, agg_fact):
        self.agg_fact = agg_fact
        self.target_shape = target_shape

    def transform(self, lat_ind, lon_ind):
        transformed_lat_ind = np.empty(
            (len(lat_ind)*self.agg_fact**2), dtype=int)
        transformed_lon_ind = np.empty(
            (len(lon_ind)*self.agg_fact**2), dtype=int)
        step = self.agg_fact**2
        for k in range(step):
            i = k//self.agg_fact
            j = k % self.agg_fact
            transformed_lat_ind[k::step] = lat_ind*self.agg_fact+i
            transformed_lon_ind[k::step] = lon_ind*self.agg_fact+j
        mask = (transformed_lat_ind < self.target_shape[0]) & (
            transformed_lon_ind < self.target_shape[1])
        # print(mask)
        transformed_lon_ind = transformed_lon_ind[mask]
        transformed_lat_ind = transformed_lat_ind[mask]
        return transformed_lat_ind.T, transformed_lon_ind.T


def extract_value(val):
    if isinstance(val, xr.DataArray):
        return val.values.item() if val.size == 1 else val.values
    return val

# In wgs84


class LatLonCoordinates:
    """
    Class containing the lat lon coordinate pair and that automatically takes into account if the preprocessed data is resampled. 
    """
    def __init__(self, lat, lon, is_resampled, agg_fact, pole, temp_key, tracking_fps):
        try:
            with xr.open_dataset(tracking_fps[pole][temp_key]["cloudtracks"][0]) as cloudtrack_data:
                if is_resampled:
                    lat_1d = cloudtrack_data['lat'].values
                    lon_1d = cloudtrack_data['lon'].values
                    print(f"Resampled lat shape: {lat_1d.shape}, lon shape: {lon_1d.shape}")
                    print(lat_1d)
                    self.lat = np.tile(lat_1d[:, np.newaxis], (1, lon_1d.shape[0]))
                    self.lat = np.tile(self.lat[np.newaxis, :, :], (2, 1, 1))
                    self.lon = np.tile(lon_1d[np.newaxis, :], (lat_1d.shape[0], 1))
                    self.lon = np.tile(self.lon[np.newaxis, :, :], (2, 1, 1))
                    print(f"Tiled array shape lat: {self.lat.shape}, lon shape: {self.lon.shape}")
                    self._extract_resampled_coord()
                else:
                    self.lat = lat.values
                    self.lon = lon.values
                    self.coord_transformer = CoordinateTransformer(
                        lon.shape[1:], agg_fact)
        except Exception as e:
            raise RuntimeError(f"Skipping {pole} {temp_key} due to error: {e}")

    def _extract_resampled_coord(self):
        self.lat_resolution = (self.lat.max()-self.lat.min())/len(self.lat)
        self.lon_resolution = (self.lon.max()-self.lon.min())/len(self.lon)


def extract_tracknumbers_data(pole, temp_key, tracking_fps):
    try:
        with xr.open_dataset(tracking_fps[pole][temp_key]["tracknumbers"]) as tracknumbers_data:
            return pd.to_datetime(tracknumbers_data['basetimes'])
    except Exception as e:
        print(f"Skipping {pole} {temp_key} due to error: {e}")
        return None


def extract_trackstats(pole, temp_key, tracking_fps):
    try:
        with xr.open_dataset(tracking_fps[pole][temp_key]["trackstats_final"]) as trackstats_data:
            return trackstats_data.variables['track_duration'].shape[0]
    except Exception as e:
        print(f"Skipping {pole} {temp_key} due to error: {e}")
        return None


def extract_cloud_number_field(cloudtrack_data):
    cloudtracknumber_field = cloudtrack_data['tracknumber'].data
    cloudtracknumber_field[np.isnan(cloudtracknumber_field)] = 0
    return cloudtracknumber_field.astype(int)


def extract_cpp_vars(time, pole, config):
    if time > config["struct_boundary_date"]:
        cpp_filename = time.strftime(
            "%Y/%m/%d/CPPin%Y%m%d%H%M%S405SVMSGI1MD.nc")
    else:
        cpp_filename = time.strftime(
            "%Y/%m/%d/CPPin%Y%m%d%H%M%S405SVMSG01MD.nc")
    # with xr.open_dataset(os.path.join(config["CLAAS_fp"], pole, cpp_filename), chunks="auto") as cpp_data:
    with xr.open_dataset(os.path.join(config["CLAAS_fp"], pole, cpp_filename)) as cpp_data:
        return cpp_data['cot'].values, cpp_data['cwp'].values


def extract_ctx_vars(time, pole, config):
    if time > config["struct_boundary_date"]:
        ctx_filename = time.strftime(
            "%Y/%m/%d/CTXin%Y%m%d%H%M%S405SVMSGI1MD.nc")
    else:
        ctx_filename = time.strftime(
            "%Y/%m/%d/CTXin%Y%m%d%H%M%S405SVMSG01MD.nc")
    # with xr.open_dataset(os.path.join(config["CLAAS_fp"], pole, ctx_filename),chunks="auto") as ctx_data:
    with xr.open_dataset(os.path.join(config["CLAAS_fp"], pole, ctx_filename)) as ctx_data:
        if (config["validation_mode"] == "dardar") or (config["validation_mode"] == "modis"):
            return ctx_data['ctp'].values, ctx_data['ctt'].values, ctx_data['cth'].values
        else:
            return ctx_data['ctp'].values, ctx_data['ctt'].values, None

def extract_resampled_vars(time,pole, config):
    tag = f"R_Agg_{config['agg_fact']:02}" if config["Resample"] else f"Agg_{config['agg_fact']:02}"
    resampled_filename=time.strftime(
            f"%Y/%m/%d/{tag}_{time.strftime('%Y%m%d%H%M%S')}.nc")
    with xr.open_dataset(os.path.join(config["CLAAS_fp"],"Resampled_Data", pole, resampled_filename)) as resampled_data:
        return resampled_data['ctp_resampled'].values, resampled_data['ctt_resampled'].values, None
            
# def extract_dardar_vars(time, config):
#     dardar_filename = time.strftime("%Y/%m/%d/val_CT_%Y%m%d_%H%M.nc")

#     with xr.open_dataset(os.path.join(config["DARDAR_CPH_fp"], dardar_filename)) as ds:
#         # make them (lat_bin, lon_bin)
#         cph = ds["cph_mean"].isel(time_bin=0).values
#         cth = ds["cth_mean"].isel(time_bin=0).values
#         cth_std = ds["cth_std"].isel(time_bin=0).values
#     return cph, cth, cth_std

def extract_val_vars(time, config, lat , lon):
    n_lon, n_lat =  len(lon), len(lat)
    shp = ( n_lat, n_lon)

    def nan_out():
        return (np.full(shp, np.nan, np.float32),
                np.full(shp, np.nan, np.float32),
                np.full(shp, np.nan, np.float32))
    if config["validation_mode"]=="dardar":
        rel = time.strftime("%Y/%m/%d/DD_CT_%Y%m%d_%H%M.nc")
    elif config["validation_mode"]=="modis":
        rel = time.strftime("%Y/%m/%d/MOD_CT_%Y%m%d_%H%M.nc")
    fp = os.path.join(config["val_CPH_fp"], rel)
    if not os.path.isfile(fp):
        return nan_out()
    
    with xr.open_dataset(fp) as ds:
        cph = ds["cph_mean"].isel(time_bin=0).values
        cth = ds["cth_mean"].isel(time_bin=0).values
        cth_std = ds["cth_std"].isel(time_bin=0).values
    return cph, cth, cth_std

def extract_val_cords(time, config):
    if config["validation_mode"]=="dardar":
        val_filename = time.strftime(
                "%Y/%m/%d/DD_CT_%Y%m%d_%H%M.nc")
    elif config["validation_mode"]=="modis":
        val_filename = time.strftime(
                "%Y/%m/%d/MOD_CT_%Y%m%d_%H%M.nc")
        
    val_path = os.path.join(config["val_CPH_fp"], val_filename)
    if not os.path.exists(val_path):
        return None, None
    with xr.open_dataset(val_path) as val_data:
        return val_data["lat_bin"].values, val_data["lon_bin"].values

def extract_aux_vars(aux_ind, cloud_location_ind_non_agg, pix_arr, lat_arr, lon_arr):
    ind1 = cloud_location_ind_non_agg[0]
    ind2 = cloud_location_ind_non_agg[1]
    return pix_arr[aux_ind, ind1, ind2], lat_arr[aux_ind, ind1, ind2], lon_arr[aux_ind, ind1, ind2]

def extract_agg_aux_vars(aux_ind, cloud_location_ind_agg, pix_arr, lat_arr, lon_arr):
    ind1 = cloud_location_ind_agg[0].T
    ind2 = cloud_location_ind_agg[1].T
    return pix_arr[aux_ind, ind1, ind2], lat_arr[aux_ind, ind1, ind2], lon_arr[aux_ind, ind1, ind2]

def extract_additional_values(cot_arr, ctp_arr, ctt_arr, cloud_location_ind_non_agg):
    ind1 = cloud_location_ind_non_agg[0]
    ind2 = cloud_location_ind_non_agg[1]
    return cot_arr[0, ind1, ind2], ctp_arr[0, ind1, ind2], ctt_arr[0, ind1, ind2]

def extract_additional_values_agg(cot_arr, ctp_arr, ctt_arr, cloud_location_ind_agg):
    ind1 = cloud_location_ind_agg[0].T
    ind2 = cloud_location_ind_agg[1].T
    return cot_arr[0, ind1, ind2], ctp_arr[0, ind1, ind2], ctt_arr[0, ind1, ind2]

def extract_claas_cth(cth_arr, cloud_location_ind_non_agg):
    ind1 = cloud_location_ind_non_agg[0]
    ind2 = cloud_location_ind_non_agg[1]
    return cth_arr[0, ind1, ind2]


def save_single_temp_range_results(cloud_arr, pole, min_temp, max_temp, config):
    columns = ["tracknumber","is_large_pix_cloud", "is_cot_valid_cloud", "is_ctp_valid_cloud", "is_liq", "is_mix", "is_ice", "max_water_frac",
               "max_ice_fraction", "avg_size[km]", "max_size[km]",
               "min_size[km]", "avg_size[px]", "max_size[px]",
               "min_size[px]", "track_start_time", "track_length", "avg_cot", "avg_ctp", "avg_ctt",
               "glaciation_start_time", "glaciation_end_time", "avg_lat",
               "avg_lon", "start_ice_fraction", "end_ice_fraction",
               "ice_frac_hist", "cot_hist", "cot_std_hist",  "cot_nan_frac_hist", "ctp_hist", "ctp_std_hist", "ctp_nan_frac_hist", "ctt_hist", "ctt_std_hist" , "lat_hist", "lon_hist",
               "size_hist_km"]
    additional_validation_variables = (config["validation_mode"] == "dardar") or (config["validation_mode"] == "modis")
    if additional_validation_variables:
        #               Data from Dardar-Mask
        #               IF = Ice Fraction (Function of clopud top phase (cph))
        columns.extend(["val_ice_frac_hist", "val_ice_frac_std_hist","val_ice_frac_dev_hist", "val_pix_claas_if_hist", "val_pix_claas_if_std_hist",
                        # CTH = Cloud top height
                        "val_cth_hist", "val_cth_std_hist", "val_cth_dev_hist", "val_pix_claas_cth_hist", "val_pix_claas_cth_std_hist",
                        # Data from claas
                        # CTH
                        "is_cth_valid_cloud", "avg_cth", "cth_hist", "cth_std_hist",  "cth_nan_frac_hist"])
    if config["validation_mode"] == "dardar":
        columns.extend(["val_intersec_lon","val_intersec_lat"])
    datapoints_per_cloud = len(columns)
    cloudinfo_df = pd.DataFrame(
        index=range(len(cloud_arr)), columns=columns)
    for cloud_ind in range(len(cloud_arr)):
        current_cloud = cloud_arr[cloud_ind]
        if current_cloud is not None:
            if not current_cloud.deactivate_cloud:
                variable_list = [
                    current_cloud.id,
                    current_cloud.large_pixel_cloud,
                    current_cloud.valid_cot_cloud,
                    current_cloud.valid_ctp_cloud,
                    current_cloud.is_liq,
                    current_cloud.is_mix,
                    current_cloud.is_ice,
                    current_cloud.max_water_fraction,
                    current_cloud.max_ice_fraction,
                    extract_value(current_cloud.avg_cloud_size_km),
                    extract_value(current_cloud.max_size_km),
                    extract_value(current_cloud.min_size_km),
                    extract_value(current_cloud.avg_cloud_size_px),
                    extract_value(current_cloud.max_size_px),
                    extract_value(current_cloud.min_size_px),
                    current_cloud.track_start_time,
                    current_cloud.track_length,
                    current_cloud.avg_cot,
                    current_cloud.avg_ctp,
                    current_cloud.avg_ctt,
                    current_cloud.glaciation_start_time,
                    current_cloud.glaciation_end_time,
                    extract_value(current_cloud.avg_cloud_lat),
                    extract_value(current_cloud.avg_cloud_lon),
                    current_cloud.start_ice_fraction_arr,
                    current_cloud.end_ice_fraction_arr,
                    current_cloud.ice_fraction_list,
                    current_cloud.mean_cot_list,
                    current_cloud.std_cot_list,
                    current_cloud.cot_nan_frac_list,
                    current_cloud.mean_ctp_list,
                    current_cloud.std_ctp_list,
                    current_cloud.ctp_nan_frac_list,
                    current_cloud.mean_ctt_list,
                    current_cloud.std_ctt_list,
                    current_cloud.lat_list,
                    current_cloud.lon_list,
                    current_cloud.cloud_size_km_list
                ]
                if additional_validation_variables:
                    variable_list.extend([
                        current_cloud.val_cph_list,
                        current_cloud.val_cph_std_list,
                        current_cloud.val_cph_deviation,
                        current_cloud.val_pix_claas_cph_meas,
                        current_cloud.val_pix_claas_cph_std,
                        current_cloud.val_cth_list,
                        current_cloud.val_cth_std_list,
                        current_cloud.val_cth_deviation,
                        current_cloud.val_pix_claas_cth_meas,
                        current_cloud.val_pix_claas_cph_std,
                        current_cloud.valid_cth_cloud,
                        current_cloud.avg_cth,
                        current_cloud.mean_cth_list,
                        current_cloud.std_cth_list,
                        current_cloud.cth_nan_frac_list
                    ])
                if config["validation_mode"] == "dardar":
                    variable_list.extend([current_cloud.val_intersec_lon,current_cloud.val_intersec_lat])
                cloudinfo_df.iloc[cloud_ind] = variable_list


    # Ensure output directory exists
    if config["Resample"]:
        output_dir = os.path.join(
            config['postprocessing_output_dir'], pole,
            config['time_folder_name'],
            f"R_Agg_{config['agg_fact']:02}_T_{abs(round(min_temp)):02}_{abs(round(max_temp)):02}"
        )
    else:
        output_dir = os.path.join(
            config['postprocessing_output_dir'], pole,
            config['time_folder_name'],
            f"Agg_{config['agg_fact']:02}_T_{abs(round(min_temp)):02}_{abs(round(max_temp)):02}"
        )

    os.makedirs(os.path.dirname(output_dir), exist_ok=True)

    # Save DataFrame to Parquet
    output_dir_parq = output_dir + ".parquet"
    print("Writing to ", output_dir_parq)
    cloudinfo_df.to_parquet(output_dir_parq)

    # Optionally save as CSV
    if config['write_csv']:
        output_dir_csv = output_dir + ".csv"
        cloudinfo_df.to_csv(output_dir_csv)


# Latitude and Longitude arrays to pixel area array
def lat_lon_to_pix_arr(lat_arr,lon_arr):
    """
    Convert latitude and longitude arrays to pixel areas based on a Spherical earth model
    
    Parameters:
    lat_arr (array-like): 2D Array of latitude values.
    lon_arr (array-like): 2D Array of longitude values.

    Returns:
    tuple: Two arrays containing the pixel indices for latitude and longitude.
    """
    res_lat = np.pad(abs(lat_arr[0,1:,0] - lat_arr[0,:-1,0]),(0,1), 'edge')  # degrees per pixel latitude direction
    res_lon = np.pad(abs(lon_arr[0,0,1:] - lon_arr[0,0,:-1]),(0,1), 'edge')   # degrees per pixel longitude direction
    return 110*110*np.outer(res_lat,res_lon)[np.newaxis,:,:]*np.cos(np.deg2rad(lat_arr)) 


# @profile
def analyze_single_temp_range(temp_ind: int, tracking_fps: dict, pole: str, config: dict, pix_area: np.array = None, pix_area_agg: np.array  = None,  lon: np.array =None, lat: np.array =None, lat_agg: np.array  = None, lon_agg: np.array =None) -> None:
    """
    Analises a given cloud top temperature range and saves the results in a dataframe.
    
    Parameters:
        temp_ind (int): Index of the temperature range to analyze.
        tracking_fps (dict): Dictionary containing file paths for the tracking data (PyFlexTrkr output).
        pole (str): Pole to analyze ("N" or "S", also known as hemisphere :)).
        config (dict): Configuration dictionary containing parameters for the analysis. Those are the gte_config.yaml conntents .
        pix_area (array-like, optional): 3D (x,y,1) Array of pixel area values for non-resampled data. Required if config["Resample"] is False.
        pix_area_agg (array-like, optional): 3D (x,y,1) Array of pixel area values on the aggregated grid. Required if config["Resample"] is False.
        lon (array-like, optional): 3D (x,y,1) Array of cell longitude values. Required if config["Resample"] is False.
        lat (array-like, optional): 3D (x,y,1) Array of cell latitude values. Required if config["Resample"] is False.
    Returns:
        Nothing
    """
    # Load configuration parameters
    min_temp, max_temp = config['min_temp_arr'][temp_ind], config['max_temp_arr'][temp_ind]
    abs_min_temp, abs_max_temp = abs(round(min_temp)), abs(round(max_temp))
    is_resampled = config["Resample"]
    collect_aval_properties = config["collect_additional_properties"]
    temp_key = f"{abs_min_temp}_{abs_max_temp}"
    validation_mode = config["validation_mode"]

    # Load datasets
    try:
        cords = LatLonCoordinates(
            lat, lon, is_resampled, config['agg_fact'], pole, temp_key, tracking_fps)
        lat_arr = cords.lat if cords.lat is not None else None
        lon_arr = cords.lon if cords.lon is not None else None
        assert ((lat_arr is None) or (len(lat_arr.shape) == 3)), f"Latitude array is not 3-D, it is {len(lat_arr.shape)}D"
        assert ((lon_arr is None) or (len(lon_arr.shape) == 3)), f"Longitude array is not 3-D, it is {len(lon_arr.shape)}D"
    except Exception as e:
        print(f"Exception in coordinate creation: {e}")
        return None
    basetimes = extract_tracknumbers_data(pole, temp_key, tracking_fps)
    n_tracks = extract_trackstats(pole, temp_key, tracking_fps)
    if basetimes is None or n_tracks is None:
        return None

    print(f"Analyzing {pole} {temp_key} with {n_tracks} tracks")

    cloud_arr = np.empty((n_tracks), dtype=Cloud)
    for i in range(n_tracks):
        cloud_arr[i] = None

    # Cloud(f'{temp_ind}_{i}') for i in range(n_tracks)])
    # print(f"Analyzing T: {min_temp} to {max_temp} Agg={config['agg_fact']}")

    pix_arr = pix_area.values if pix_area is not None else lat_lon_to_pix_arr(lat_arr, lon_arr)
    pix_arr_agg = pix_area_agg.values if pix_area_agg is not None else lat_lon_to_pix_arr(lat_arr, lon_arr)
    # So later there is no mismatch between the sizing of the grids for lat/lon/pix and the additional variables
    if validation_mode == "model":
        lat_arr_agg = lat_agg.values if lat_agg is not None else None
        lon_arr_agg = lon_agg.values if lon_agg is not None else None
        assert lat_arr_agg is not None, "lat_arr_agg is somehow none"
        assert ((lon_arr_agg is None) or (len(lon_arr_agg.shape) == 3)), f"Aggregated Latitude array is not 3-D, it is {len(lat_arr.shape)}D"
        assert ((lon_arr_agg is None) or (len(lon_arr_agg.shape) == 3)), f"Aggregated Longitude array is not 3-D, it is {len(lon_arr.shape)}D"
    elif (validation_mode == "dardar") or (validation_mode == "modis"):
        val_lat , val_lon = None, None
        lat_arr_agg = lat_agg.values if lat_agg is not None else None
        lon_arr_agg = lon_agg.values if lon_agg is not None else None
        assert lat_arr_agg is not None, "lat_arr_agg is somehow none"
        
        for time in basetimes:
            if val_lon is None or val_lat is None:
                val_lat, val_lon = extract_val_cords(time, config)
            if (val_lon is not None) and (val_lat is not None):
                val_index = build_val_index(val_lat, val_lon)
                break
            
    for fp_ind in range(len(basetimes)):
        time = basetimes[fp_ind]
        time_str = time.strftime("%Y%m%d_%H%M%S")
        # print(f'{min_temp} to {max_temp} Loading {time_str}')

        aux_ind = 1 if time > config["struct_boundary_date"] else 0

        if collect_aval_properties:
            if is_resampled or validation_mode=="model":
                ctp_arr, ctt_arr, cth_arr = extract_resampled_vars(time, pole, config)
                cot_arr = np.ones(ctp_arr.shape)
                cwp_arr = np.array([])
            else:
                cot_arr, cwp_arr = extract_cpp_vars(time, pole, config)
                ctp_arr, ctt_arr, cth_arr = extract_ctx_vars(time, pole, config)
        
        if (validation_mode == "dardar") or (validation_mode == "modis"):
            val_cph, val_cth, val_cth_std = extract_val_vars(time, config, val_lat, val_lon)

        cloudtrack_fp = tracking_fps[pole][temp_key]['cloudtracks'][fp_ind]

        with xr.open_dataset(cloudtrack_fp) as cloudtrack_data:
            cph_arr = cloudtrack_data['cph_filtered'].values
            cloudtracknumber_field = extract_cloud_number_field(
                cloudtrack_data)
            cloud_id_in_field, counts = np.unique(
                cloudtracknumber_field, return_counts=True)
            counts = counts[cloud_id_in_field != 0]
            if len(counts) == 0:
                print(
                    f"{pole} - {min_temp} to {max_temp}: No cloud timestep: {time_str}")
                continue
            cloud_id_in_field = cloud_id_in_field[cloud_id_in_field != 0]
            max_allowed_cloud_size_px = config['fast_mode_arr_size'] if config['postprocessing_fast_mode'] else counts.max(
            )
            hash_map_cloud_numbers = extract_cloud_coordinates(
                cloudtracknumber_field, cloud_id_in_field, max_allowed_cloud_size_px)  # counts.max())
            del cloudtracknumber_field

        # print(f"N_clouds in frame {len(cloud_id_in_field)}", flush=True)
        # if max_allowed_cloud_size_px > 1000000:
        #     print(np.where(counts, counts == counts.max()))
        # print(cloud_id_in_field)

        for track_number in cloud_id_in_field:
            try:
                if cloud_arr[track_number-1] is None:
                    cloud_arr[track_number-1] = Cloud(track_number, is_resampled, config['agg_fact'])
            except:
                print(
                    f"Error: {temp_ind,track_number,len(cloud_arr)}")
                continue

            cloud_val_cph_agg=None
            cloud_val_cth_agg=None
            cloud_val_cth_std_agg=None
            cloud_cth_values=None
            cloud_val_cth_non_agg=None
            cloud_val_cth_std_non_agg=None
            
            if (not cloud_arr[track_number-1].terminate_cloud):
                cord = hash_map_cloud_numbers[track_number]
                cloud_location_ind = [cord[0, :], cord[1, :]]

                if cloud_location_ind[0].size != 0:
                    cloud_cph_values = cph_arr[0,
                                               cloud_location_ind[0].T, cloud_location_ind[1].T]
                    # print(f"Cloud cph values size: {cloud_cph_values.shape}")
                    # print(f"Cloud loc ind 0 size: {cloud_location_ind[0].shape}")
                    # print(f"Cloud loc ind 1 size: {cloud_location_ind[1].shape}")
                    if is_resampled:
                        # avg_lat_ind = int(
                        #     round(np.mean(cloud_location_ind[0])))
                        # avg_lon_ind = int(
                        #     round(np.mean(cloud_location_ind[1])))
                        cloud_pix_area_values, cloud_lat_values, cloud_lon_values = extract_aux_vars(
                            aux_ind, cloud_location_ind, pix_arr, lat_arr, lon_arr)
                        agg_pix_area_values = pix_arr_agg[aux_ind, cloud_location_ind[0].T, cloud_location_ind[1].T]
                        if collect_aval_properties:
                            cloud_cot_values, cloud_ctp_values, cloud_ctt_values = extract_additional_values_agg(
                                cot_arr, ctp_arr, ctt_arr, cloud_location_ind)
                        else:
                            cloud_cot_values, cloud_ctp_values, cloud_ctt_values = np.array(
                                []), np.array([]), np.array([])
                        # cloud_arr[track_number-1].update_status(
                        #     time, cloud_cph_values, cloud_cot_values, cloud_ctp_values, cloud_ctt_values, cloud_lat_values, cloud_lon_values, cloud_pix_area_values, agg_pix_area_values)
                        cloud_arr[track_number-1].update_status(time,
                            cloud_cph_values, cloud_cot_values, cloud_ctp_values, cloud_ctt_values,
                            cloud_lat_values, cloud_lon_values, cloud_pix_area_values, agg_pix_area_values)
                    else:
                        cloud_location_ind_non_agg = cords.coord_transformer.transform(
                            cloud_location_ind[0], cloud_location_ind[1])
                        if validation_mode=="model":
                            cloud_pix_area_values, cloud_lat_values, cloud_lon_values = extract_agg_aux_vars(
                                aux_ind, cloud_location_ind, pix_arr_agg, lat_arr_agg, lon_arr_agg)
                        else:
                            cloud_pix_area_values, cloud_lat_values, cloud_lon_values = extract_aux_vars(
                                aux_ind, cloud_location_ind_non_agg, pix_arr, lat_arr, lon_arr)
                        agg_pix_area_values = pix_arr_agg[aux_ind, cloud_location_ind[0].T, cloud_location_ind[1].T]
                        # if not (agg_pix_area_values > 0).all():
                        #     print(f"0 or negative values in aggregated pixel area array {agg_pix_area_values}")
                        #     print(len(agg_pix_area_values))
                        #     print(pix_arr_agg.shape)
                        #     print(cloud_location_ind)
                        # print(f"Cloud location ind non agg 0: {cloud_location_ind_non_agg[0].shape}")
                        # print(f"Cloud pix area values: {cloud_pix_area_values[::9].shape}")
                        # assert (cloud_pix_area_values[::9].shape == cloud_cph_values.shape), f"Pixel area size array mismatch\npix_area:{cloud_pix_area_values[::9].shape}\n{cloud_cph_values.shape}\ncloud_location_ind 0: {cloud_location_ind[0]}\ncloud_location_ind 1: {cloud_location_ind[1]}\ncloud_location_ind_non_agg 0: {cloud_location_ind_non_agg[0][:-20]}\ncloud_location_ind_non_agg 1: {cloud_location_ind_non_agg[1][:-20]}"
                        if collect_aval_properties:
                            if validation_mode=="model":
                                if pix_arr_agg.shape != lat_arr_agg.shape or pix_arr_agg.shape != lon_arr_agg.shape:
                                    raise ValueError(
                                        f"Shape mismatch: pix_arr_agg={pix_arr_agg.shape}, "
                                        f"lat_arr_agg={lat_arr_agg.shape}, lon_arr_agg={lon_arr_agg.shape}"
                                    )
                                cloud_cot_values, cloud_ctp_values, cloud_ctt_values = extract_additional_values_agg(
                                    cot_arr, ctp_arr, ctt_arr, cloud_location_ind)
                            else:
                                cloud_cot_values, cloud_ctp_values, cloud_ctt_values = extract_additional_values(
                                    cot_arr, ctp_arr, ctt_arr, cloud_location_ind_non_agg)
                        else:
                            cloud_cot_values, cloud_ctp_values, cloud_ctt_values = np.array(
                                []), np.array([]), np.array([])
                        # print(np.info(cloud_cot_values))
                        # assert (cloud_pix_area_values.size >= ((cloud_cph_values.size-1) * (config['agg_fact'] ** 2))),  "Pixel area size array mismatch"
                        
                        if (validation_mode == "dardar") or (validation_mode == "modis"):
                            # Match DARDAR to EACH cloud pixel location
                            cloud_cth_values = extract_claas_cth(cth_arr, cloud_location_ind_non_agg)
                            agg_lat_values = lat_arr_agg[aux_ind, cloud_location_ind[0].T, cloud_location_ind[1].T]
                            agg_lon_values = lon_arr_agg[aux_ind, cloud_location_ind[0].T, cloud_location_ind[1].T]
                            # bad_coord = ~np.isfinite(cloud_lat_values) | ~np.isfinite(cloud_lon_values)
                            # if np.any(bad_coord):
                            #     print(
                            #         f"{time_str} {temp_key} track_nr - {track_number} : "
                            #         f"Non-finite cloud coordinates: {np.count_nonzero(bad_coord)} of {bad_coord.size}; "
                            #         f"Bad indices: {np.where(bad_coord)}; "
                            #         f"Bad lat values: {cloud_lat_values[bad_coord][:20]}; "
                            #         f"Bad lon values: {cloud_lon_values[bad_coord][:20]}",
                            #         flush=True,
                            #     )
                            cloud_val_cph_agg, _ , _ = match_val_to_cloud(
                                val_index,
                                val_cph, val_cth, val_cth_std,
                                agg_lat_values, agg_lon_values,
                                max_km=config.get("val_max_match_km", None),  # optional
                                fill_value=np.nan
                                )
                            _ , cloud_val_cth_non_agg, cloud_val_cth_std_non_agg = match_val_to_cloud(
                                val_index,
                                val_cph, val_cth, val_cth_std,
                                cloud_lat_values, cloud_lon_values,
                                max_km=config.get("val_max_match_km", None),  # optional
                                fill_value=np.nan
                                )
                        if validation_mode == "model":
                            cloud_arr[track_number-1].update_status(
                                time,
                                cloud_cph_values, cloud_cot_values, cloud_ctp_values, cloud_ctt_values,
                                cloud_lat_values, cloud_lon_values, agg_pix_area_values, agg_pix_area_values, is_input_agg = True)
                        else:
                            cloud_arr[track_number-1].update_status(
                                time,
                                cloud_cph_values, cloud_cot_values, cloud_ctp_values, cloud_ctt_values,
                                cloud_lat_values, cloud_lon_values, cloud_pix_area_values, agg_pix_area_values,
                                val_cph=cloud_val_cph_agg, val_cth=cloud_val_cth_non_agg, val_cth_std=cloud_val_cth_std_non_agg, claas_cth_values=cloud_cth_values)
                else:
                    cloud_arr[track_number-1].update_missing_cloud()
        if collect_aval_properties:
            del ctp_arr, cwp_arr, cot_arr, ctt_arr
        del cph_arr
        del cloud_cot_values, cloud_ctp_values, cloud_cph_values, cloud_ctt_values
        del hash_map_cloud_numbers
        if not is_resampled:
            del cloud_location_ind_non_agg
        del cloud_location_ind
        del cloud_pix_area_values, cloud_lat_values, cloud_lon_values
 
    save_single_temp_range_results(cloud_arr, pole, min_temp, max_temp, config)



def analize_single_pole(pole, cloud_dict, tracking_fps, config):
    print(f"Analyzing {pole}")
    aux_ds = xr.load_dataset(config["aux_fps"][pole], decode_times=False)
    aux_ds_agg = xr.load_dataset(config["aux_fps_agg"][pole], decode_times=False)
    n_procs = config.get("n_postproc_cores",4)
    if config["Resample"]:
        with Pool(n_procs) as pool:
            part_single_temp_range = partial(
                analyze_single_temp_range, tracking_fps=tracking_fps, pole=pole, config=config)
            pool.map(part_single_temp_range, range(
                len(config['min_temp_arr'])))
            pool.close()
            pool.join()
    if not config["Resample"]:
        lat_mat = aux_ds["lat"].load()
        lon_mat = aux_ds["lon"].load()
        pix_area = aux_ds["pixel_area"].load()
        pix_area_agg = aux_ds_agg["pixel_area"].load()
        lat_agg = aux_ds_agg["lat"].load()
        lon_agg = aux_ds_agg["lon"].load()
        # assert (~np.isnan(pix_area_agg.values).any()), "NaN values in aggregated pixel area array"
        # assert (~np.isnan(lat_agg.values).any()), "NaN values in aggregated pixel area array"
        validation_mode = config.get("validation_mode", None)
        if validation_mode in ["model","dardar","modis"] :
            part_single_temp_range = partial(analyze_single_temp_range, tracking_fps=tracking_fps,
                                            pole=pole, config=config, pix_area=pix_area, pix_area_agg = pix_area_agg, lon=lon_mat, lat=lat_mat, lat_agg = lat_agg, lon_agg = lon_agg)
        else: 
            part_single_temp_range = partial(analyze_single_temp_range, tracking_fps=tracking_fps,
                                            pole=pole, config=config, pix_area=pix_area, pix_area_agg = pix_area_agg, lon=lon_mat, lat=lat_mat)
        with Pool(n_procs) as pool:
            pool.map(part_single_temp_range, range(
                len(config['min_temp_arr'])))
            pool.close()
            pool.join()
        # for ind in range(len(config['min_temp_arr'])):
        #     part_single_temp_range(ind)



def analyze_tracked_clouds(config):
    tracking_fps=generate_tracking_filenames(config)
    with Manager() as manager:
        cloud_dict=manager.dict()
        # TODO: Paralelize here
        part_analize_single_pole=partial(
            analize_single_pole, cloud_dict=cloud_dict, tracking_fps=tracking_fps, config=config)
        # with NestablePool(2) as pool:
        #     pool.map(part_analize_single_pole, config['pole_folders'])
        #     pool.close()
        #     pool.join()
        for pole in config['pole_folders']:
            part_analize_single_pole(pole)



if __name__ == "__main__":
    config=read_config()
    analyze_tracked_clouds(config)

