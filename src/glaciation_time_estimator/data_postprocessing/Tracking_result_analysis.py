import numpy as np
import xarray as xr
from numba import njit, typed, types
import pandas as pd
from datetime import datetime
from glaciation_time_estimator.auxiliary_func.config_reader import read_config
from glaciation_time_estimator.data_postprocessing.Single_cloud_analysis import Cloud
from glaciation_time_estimator.data_postprocessing.Job_result_fp_generator import generate_tracking_filenames
from multiprocessing import Manager, Pool
from glaciation_time_estimator.auxiliary_func.Nestable_multiprocessing import NestablePool
from functools import partial
import os
from memory_profiler import profile



# ---------- helper Numba types ----------
coord_type    = types.UniTuple(types.int16, 2)        # (row, col)
list_type     = types.ListType(coord_type)            # list of coordinates
array2d_type  = types.int16[:, ::1]                   # (2, n_pts) C-contiguous
dict_lists_t  = types.DictType(types.int64, list_type)
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
        key_type   = types.int64,
        value_type = list_type
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
        key_type   = types.int64,
        value_type = array2d_type
    )

    for cid in coord_lists:
        lst = coord_lists[cid]
        n   = len(lst)
        arr = np.empty((2, n), dtype=np.int16)

        for i in range(n):
            rc = lst[i]
            arr[0, i] = rc[0]     # row
            arr[1, i] = rc[1]     # col

        result[cid] = arr

    return result


# @nb.njit
# def extract_cloud_coordinates(cloudtracknumber_field, cloud_id_in_field, max_size):
#     # Define the dictionary with the appropriate types
#     loc_hash_map_cloud_numbers = {
#         j: (0, np.zeros((2, max_size), dtype=np.int16)) for j in cloud_id_in_field}
#     # # Traverse the 3D array
#     # for i in cloud_id_in_field:
#     #     loc_hash_map_cloud_numbers[val] = (0,np.empty((2,max_size),dtype=np.int16))
#     for row in range(cloudtracknumber_field.shape[1]):
#         for col in range(cloudtracknumber_field.shape[2]):
#             val = cloudtracknumber_field[0, row, col]
#             if val != 0:
#                 ind, cord = loc_hash_map_cloud_numbers[val]
#                 if ind <= max_size:
#                     cord[:, ind] = np.asarray([row, col], dtype=np.int16)
#                     ind += 1
#                     # print(ind)
#                     loc_hash_map_cloud_numbers[val] = (ind, cord)
#     return loc_hash_map_cloud_numbers
#     # return loc_hash_map_cloud_numbers


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


# def extract_cpp_vars(time, pole, config):
#     if time>config["struct_boundary_date"]:
#         cpp_filename = time.strftime("CPPin%Y%m%d%H%M%S405SVMSGI1MD.nc")
#     else:
#         cpp_filename = time.strftime("CPPin%Y%m%d%H%M%S405SVMSG01MD.nc")
#     with xr.load_dataset(os.path.join(os.environ["TMPDIR"], "Data", pole, cpp_filename)) as cpp_data:
#         return cpp_data['cot'],cpp_data['cwp']

def extract_cpp_vars(time, pole, config):
    if time>config["struct_boundary_date"]:
        cpp_filename = time.strftime("%Y/%m/%d/CPPin%Y%m%d%H%M%S405SVMSGI1MD.nc")
    else:
        cpp_filename = time.strftime("%Y/%m/%d/CPPin%Y%m%d%H%M%S405SVMSG01MD.nc")
    # with xr.open_dataset(os.path.join(config["CLAAS_fp"], pole, cpp_filename), chunks="auto") as cpp_data:
    with xr.open_dataset(os.path.join(config["CLAAS_fp"], pole, cpp_filename)) as cpp_data:
        return cpp_data['cot'],cpp_data['cwp']


# def extract_ctx_vars(time, pole, config):
#     if time>config["struct_boundary_date"]:
#         ctx_filename = time.strftime("CTXin%Y%m%d%H%M%S405SVMSGI1MD.nc")
#     else:
#         ctx_filename = time.strftime("CTXin%Y%m%d%H%M%S405SVMSG01MD.nc")
#     with xr.load_dataset(os.path.join(os.environ["TMPDIR"], "Data", pole, ctx_filename)) as ctx_data:
#         return ctx_data['ctp']
    # print(f'{min_temp} to {max_temp} Loading {time_str}')
# /cluster/work/climate/dnikolo/dump/Data/np/CPPin20210101000000405SVMSGI1MD.nc

def extract_ctx_vars(time, pole, config):
    if time>config["struct_boundary_date"]:
        ctx_filename = time.strftime("%Y/%m/%d/CTXin%Y%m%d%H%M%S405SVMSGI1MD.nc")
    else:
        ctx_filename = time.strftime("%Y/%m/%d/CTXin%Y%m%d%H%M%S405SVMSG01MD.nc")
    # with xr.open_dataset(os.path.join(config["CLAAS_fp"], pole, ctx_filename),chunks="auto") as ctx_data:
    with xr.open_dataset(os.path.join(config["CLAAS_fp"], pole, ctx_filename)) as ctx_data:
        return ctx_data['ctp']


def extract_cloud_number_field(cloudtrack_data):
    cloudtracknumber_field = cloudtrack_data['tracknumber'].data
    cloudtracknumber_field[np.isnan(cloudtracknumber_field)] = 0
    return cloudtracknumber_field.astype(int)


def save_single_temp_range_results(cloud_arr, pole, min_temp, max_temp, config):
    columns = ["is_large_pix_cloud", "is_cot_valid_cloud","is_ctp_valid_cloud", "is_liq", "is_mix", "is_ice", "max_water_frac",
               "max_ice_fraction", "avg_size[km]", "max_size[km]",
               "min_size[km]", "avg_size[px]", "max_size[px]",
               "min_size[px]", "track_start_time", "track_length", "avg_cot","avg_ctp",
               "glaciation_start_time", "glaciation_end_time", "avg_lat",
               "avg_lon", "start_ice_fraction", "end_ice_fraction",
               "ice_frac_hist", "cot_hist", "cot_nan_frac_hist","ctp_hist", "ctp_nan_frac_hist", "lat_hist", "lon_hist",
               "size_hist_km"]
    datapoints_per_cloud = len(columns)
    cloudinfo_df = pd.DataFrame(
        index=range(len(cloud_arr)), columns=columns)
    for cloud_ind in range(len(cloud_arr)):
        current_cloud = cloud_arr[cloud_ind]
        if current_cloud is not None:
            cloudinfo_df.iloc[cloud_ind] = [
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
                current_cloud.glaciation_start_time,
                current_cloud.glaciation_end_time,
                extract_value(current_cloud.avg_cloud_lat),
                extract_value(current_cloud.avg_cloud_lon),
                current_cloud.start_ice_fraction_arr,
                current_cloud.end_ice_fraction_arr,
                current_cloud.ice_fraction_list,
                current_cloud.mean_cot_list,
                current_cloud.cot_nan_frac_list,
                current_cloud.mean_ctp_list,
                current_cloud.ctp_nan_frac_list,
                current_cloud.lat_list,
                current_cloud.lon_list,
                current_cloud.cloud_size_km_list
            ]

    # Ensure output directory exists
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

@profile
def analize_single_temp_range(temp_ind: int, tracking_fps: dict, pole: str, config: dict, pix_area=None,  lon=None, lat=None) -> None:
    # loop_start_time=dt.datetime.now()
    min_temp, max_temp = config['min_temp_arr'][temp_ind], config['max_temp_arr'][temp_ind]
    is_resampled = config["Resample"]
    collect_cot = config["collect_additional_properties"]
    
    # Load datasets
    temp_key = f'{abs(round(min_temp))}_{abs(round(max_temp))}'
    print(f"Analyzing {pole} {temp_key}")
    # print(tracking_fps[pole][temp_key]["cloudtracks"][0])
    # print(tracking_fps[pole][temp_key]["trackstats_final"])
    # print(tracking_fps[pole][temp_key]["tracknumbers"])
    try:
        # print(tracking_fps[pole][temp_key]["cloudtracks"][0])
        cloudtrack_data = xr.load_dataset(
            tracking_fps[pole][temp_key]["cloudtracks"][0])
        trackstats_data = xr.load_dataset(
            tracking_fps[pole][temp_key]["trackstats_final"])
        tracknumbers_data = xr.load_dataset(
            tracking_fps[pole][temp_key]["tracknumbers"])
    except Exception as e:
        print(f"Skipping {pole} {min_temp} to {max_temp} due to error: {e}")
        # cloud_dict[temp_key] = np.array([])
        return None
    # Load relevant data from datasets into local variables
    n_tracks = trackstats_data.variables['track_duration'].shape[0]
    basetimes = pd.to_datetime(tracknumbers_data['basetimes'])
    if is_resampled:
        lat = cloudtrack_data['lat']
        lon = cloudtrack_data['lon']
        lat_resolution = (lat.max()-lat.min())/len(lat)
        lon_resolution = (lon.max()-lon.min())/len(lon)
    else:
        coord_transformer = CoordinateTransformer(
            lon.shape[1:], config["agg_fact"])
    trackstats_data.close()
    tracknumbers_data.close()
    cloudtrack_data.close()
    # print(append_start_time-loop_start_time)
    cloud_arr = np.empty((n_tracks), dtype=Cloud)
    for i in range(n_tracks):
        cloud_arr[i] = None
    # Cloud(f'{temp_ind}_{i}') for i in range(n_tracks)])
    # print(append_end_time-append_start_time)
    # print(f"Analyzing T: {min_temp} to {max_temp} Agg={config['agg_fact']}")
    for fp_ind in range(len(basetimes)):
        time = basetimes[fp_ind]
        time_str = time.strftime("%Y%m%d_%H%M%S")
        if time>config["struct_boundary_date"]:
            aux_ind = 1
        else:
            aux_ind = 0
        print(f'{min_temp} to {max_temp} Loading {time_str}')
        if collect_cot:
            cot_field,cwp_field = extract_cpp_vars(time, pole, config)
            ctp_field  = extract_ctx_vars(time, pole, config)
        cloudtrack_fp = tracking_fps[pole][temp_key]['cloudtracks'][fp_ind]
        cloudtrack_data = xr.load_dataset(cloudtrack_fp)
        cloudtracknumber_field = extract_cloud_number_field(cloudtrack_data)
        cph_field = cloudtrack_data['cph_filtered']
        cloud_id_in_field, counts = np.unique(
            cloudtracknumber_field, return_counts=True)
        counts = counts[cloud_id_in_field != 0]
        if len(counts) == 0:
            print(f"{pole} - {min_temp} to {max_temp}: No cloud timestep: {time_str}")
            continue
        cloud_id_in_field = cloud_id_in_field[cloud_id_in_field != 0]
        max_allowed_cloud_size_px = config['fast_mode_arr_size'] if config['postprocessing_fast_mode'] else counts.max(
        )
        hash_map_cloud_numbers = extract_cloud_coordinates(
            cloudtracknumber_field, cloud_id_in_field, max_allowed_cloud_size_px)  # counts.max())
        cloudtrack_data.close()
        if max_allowed_cloud_size_px > 1000000:
            print(np.where(counts, counts == counts.max()))
        # print(cloud_id_in_field)
        for track_number in cloud_id_in_field:

            try:
                if cloud_arr[track_number-1] is None:
                    cloud_arr[track_number-1] = Cloud(temp_key, is_resampled)
            except:
                print(
                    f"Error: {temp_ind,track_number,len(cloud_arr)}")
                continue

            if (not cloud_arr[track_number-1].terminate_cloud):
                # TODO:SPEED UP NEXT TWO LINES (set_cloud_values and update_status)
                cord = hash_map_cloud_numbers[track_number]

                cloud_location_ind = [cord[0, :], cord[1, :]]
                if cloud_location_ind[0].size != 0:
                    # cloud_cph_values = cph_field.values[0,
                                                        # cloud_location_ind[0].T, cloud_location_ind[1].T]
                    cloud_cph_values = cph_field.isel(time=0,
                                  lat=xr.DataArray(cloud_location_ind[0].T, dims="points"),
                                  lon=xr.DataArray(cloud_location_ind[1].T, dims="points")).values
                    if is_resampled:
                        avg_lat_ind = int(
                            round(np.mean(cloud_location_ind[0])))
                        avg_lon_ind = int(
                            round(np.mean(cloud_location_ind[1])))
                        # TODO:SPEED UP NEXT TWO LINES (set_cloud_values and update_status)
                        cloud_arr[track_number-1].update_status(
                            time, cloud_cph_values, extract_value(lat[avg_lat_ind]), extract_value(lon[avg_lon_ind]), pixel_area=lat_resolution.values*lon_resolution.values)
                    else:
                        cloud_location_ind_non_agg = coord_transformer.transform(
                            cloud_location_ind[0], cloud_location_ind[1])
                        
                        cloud_pix_area_values = pix_area.values[aux_ind,
                                                                cloud_location_ind_non_agg[0], cloud_location_ind_non_agg[1]]
                        # cloud_pix_area_values = pix_area.isel(time=0,
                        #     lat=xr.DataArray(cloud_location_ind_non_agg[0], dims="points"),
                        #     lon=xr.DataArray(cloud_location_ind_non_agg[1], dims="points")).values
                        cloud_lat_values = lat.values[aux_ind,
                                                      cloud_location_ind_non_agg[0], cloud_location_ind_non_agg[1]]
                        cloud_lon_values = lon.values[aux_ind,
                                                      cloud_location_ind_non_agg[0], cloud_location_ind_non_agg[1]]
                        if collect_cot:
                            # cloud_cot_values = cot_field.values[0,
                            #                                     cloud_location_ind_non_agg[0], cloud_location_ind_non_agg[1]]
                            cloud_cot_values = cot_field.isel(time=0,
                                y=xr.DataArray(cloud_location_ind_non_agg[0], dims="points"),
                                x=xr.DataArray(cloud_location_ind_non_agg[1], dims="points")).values
                            # cloud_ctp_values = ctp_field.values[0,
                            #                                     cloud_location_ind_non_agg[0], cloud_location_ind_non_agg[1]]
                            cloud_ctp_values = ctp_field.isel(time=0,
                                y=xr.DataArray(cloud_location_ind_non_agg[0], dims="points"),
                                x=xr.DataArray(cloud_location_ind_non_agg[1], dims="points")).values
                        else:
                            cloud_cot_values = np.array([0])
                            cloud_ctp_values = np.array([0])
                        # print(np.info(cloud_cot_values))
                        cloud_arr[track_number-1].update_status(
                            time, cloud_cph_values, cloud_cot_values, cloud_ctp_values, cloud_lat_values, cloud_lon_values, cloud_pix_area_values)
                        
                else:
                    cloud_arr[track_number-1].update_missing_cloud()
        del ctp_field
        del cph_field
        del cwp_field
        del cot_field
        del cloud_cot_values
        del cloud_ctp_values
        del cloud_pix_area_values
        del cloud_lat_values
        del cloud_lon_values
        del cloud_location_ind
        del cloud_location_ind_non_agg
        del cloud_cph_values
    save_single_temp_range_results(cloud_arr, pole, min_temp, max_temp, config)


def analize_single_pole(pole, cloud_dict, tracking_fps, config, n_procs=6):
    print(f"Analyzing {pole}")
    aux_ds = xr.load_dataset(config["aux_fps_eu"][pole], decode_times=False)
    if config["Resample"]:
        with Pool(n_procs) as pool:
            part_single_temp_range = partial(
                analize_single_temp_range, tracking_fps=tracking_fps, pole=pole, config=config)
            pool.map(part_single_temp_range, range(
                len(config['min_temp_arr'])))
            pool.close()
            pool.join()
    if not config["Resample"]:
        lat_mat = aux_ds["lat"].load()
        lon_mat = aux_ds["lon"].load()
        pix_area = aux_ds["pixel_area"].load()
        with Pool(n_procs) as pool:
            part_single_temp_range = partial(
                analize_single_temp_range, tracking_fps=tracking_fps, pole=pole, config=config, pix_area=pix_area, lon=lon_mat, lat=lat_mat)
            # pool.map(part_single_temp_range, range(
            #     len(config['min_temp_arr'])))
            # pool.close()
            # pool.join()
            for ind in range(len(config['min_temp_arr'])):
                part_single_temp_range(ind)

# def save_results(res_dict, config):
#     min_temp, max_temp = config['min_temp_arr'][0], config['max_temp_arr'][0]
#     temp_key = f'{abs(round(min_temp))}_{abs(round(max_temp))}'
#     # cloudtrack_data = xr.(
#     #     tracking_fps['np'][temp_key]["cloudtracks"][0])
#     # lat = cloudtrack_data['lat']
#     # lon = cloudtrack_data['lon']
#     # lat_resolution = extract_value((lat.max()-lat.min())/len(lat))
#     # lon_resolution = extract_value((lon.max()-lon.min())/len(lon))
#     # cloudtrack_data.close()
#     columns = ["is_liq", "is_mix", "is_ice", "max_water_frac",
#                "max_ice_fraction", "avg_size[km]", "max_size[km]",
#                "min_size[km]", "avg_size[px]", "max_size[px]",
#                "min_size[px]", "track_start_time", "track_length",
#                "glaciation_start_time", "glaciation_end_time", "avg_lat",
#                "avg_lon", "start_ice_fraction", "end_ice_fraction",
#                "ice_frac_hist", "cot_hist", "lat_hist", "lon_hist",
#                "size_hist_km"]
#     datapoints_per_cloud = len(columns)
#     # Iterating through the cloud data
#     for temp_ind in range(len(config['max_temp_arr'])):
#         for pole in config['pole_folders']:
#             min_temp, max_temp = config['min_temp_arr'][temp_ind], config['max_temp_arr'][temp_ind]
#             temp_key = f'{abs(round(min_temp))}_{abs(round(max_temp))}'
#             key = f'{pole}_{temp_key}'
#             cloud_arr = res_dict[key]

#             cloudinfo_df = pd.DataFrame(
#                 index=range(len(cloud_arr)), columns=columns)
#             for cloud_ind in range(len(cloud_arr)):
#                 current_cloud = cloud_arr[cloud_ind]
#                 if current_cloud is not None:
#                     cloudinfo_df.iloc[cloud_ind] = [
#                         current_cloud.
#                         current_cloud.is_liq,
#                         current_cloud.is_mix,
#                         current_cloud.is_ice,
#                         current_cloud.max_water_fraction,
#                         current_cloud.max_ice_fraction,
#                         extract_value(current_cloud.avg_cloud_size_km),
#                         extract_value(current_cloud.max_size_km),
#                         extract_value(current_cloud.min_size_km),
#                         extract_value(current_cloud.avg_cloud_size_px),
#                         extract_value(current_cloud.max_size_px),
#                         extract_value(current_cloud.min_size_px),
#                         current_cloud.track_start_time,
#                         current_cloud.track_length,
#                         current_cloud.glaciation_start_time,
#                         current_cloud.glaciation_end_time,
#                         extract_value(current_cloud.avg_cloud_lat),
#                         extract_value(current_cloud.avg_cloud_lon),
#                         current_cloud.start_ice_fraction_arr,
#                         current_cloud.end_ice_fraction_arr,
#                         current_cloud.ice_fraction_list,
#                         current_cloud.mean_cot_list,
#                         current_cloud.lat_list,
#                         current_cloud.lon_list,
#                         current_cloud.cloud_size_km_list
#                     ]

#             # Ensure output directory exists
#             output_dir = os.path.join(
#                 config['postprocessing_output_dir'],
#                 config['time_folder_name'],
#                 f"T_{abs(round(min_temp)):02}_{abs(round(max_temp)):02}_agg_{config['agg_fact']:02}"
#             )
#             os.makedirs(os.path.dirname(output_dir), exist_ok=True)

#             # Save DataFrame to Parquet
#             output_dir_parq = output_dir + ".parquet"
#             print("Writing to ", output_dir_parq)
#             cloudinfo_df.to_parquet(output_dir_parq)

#             # Optionally save as CSV
#             if config['write_csv']:
#                 output_dir_csv = output_dir + ".csv"
#                 cloudinfo_df.to_csv(output_dir_csv)

def analyze_tracked_clouds(config):
    tracking_fps = generate_tracking_filenames(config)
    with Manager() as manager:
        cloud_dict = manager.dict()
        # TODO: Paralelize here
        part_analize_single_pole = partial(
            analize_single_pole, cloud_dict=cloud_dict, tracking_fps=tracking_fps, config=config)
        # with NestablePool(2) as pool:
        #     pool.map(part_analize_single_pole, config['pole_folders'])
        #     pool.close()
        #     pool.join()
        for pole in  config['pole_folders']:
            part_analize_single_pole(pole)


if __name__ == "__main__":
    config = read_config()
    analyze_tracked_clouds(config)
