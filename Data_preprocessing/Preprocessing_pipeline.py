import os
import xarray as xr
import numpy as np
import subprocess
import time
import threading
# Doesn't fail glaciosly like the multiprocessing version but is easier to use than refactoring the code for a non-nestable one
from Glaciation_time_estimator.Auxiliary_func.Nestable_multiprocessing import NestablePool
from multiprocessing import Pool
from Glaciation_time_estimator.Auxiliary_func.config_reader import read_config
from functools import partial
from Glaciation_time_estimator.Data_preprocessing.Resample_data import ProjectionTransformer
from Glaciation_time_estimator.Data_preprocessing.File_name_generator import generate_filename_dict
from Glaciation_time_estimator.Data_preprocessing.Output_file_generation import OutputNonResampledFile, OutputResampledFile
import warnings

global CLAAS_FP
CLAAS_FP = os.environ["CLAAS_DIR"]
if CLAAS_FP == "":
    raise ValueError("CLAAS_DIR is not defined")


def generate_temp_range(t_deltas: list) -> tuple:
    boundary_temps = np.arange(0, -38.1, -t_deltas[0])
    t_min = boundary_temps[1:].astype(int)
    t_max = boundary_temps[0:-1].astype(int)
    for i in range(len(t_deltas)-1):
        boundary_temps = np.arange(0, -38.1, -t_deltas[i+1])
        # t_ranges_temp=np.concatenate((boundary_temps[1:][None,:].astype(int),boundary_temps[0:-1][None,:].astype(int)),0,dtype='int')
        t_min = np.concatenate((t_min, boundary_temps[1:].astype(int)))
        t_max = np.concatenate((t_max, boundary_temps[0:-1].astype(int)))
    return t_min, t_max


def fps_by_folder(fp_arr_target):
    if len(fp_arr_target) != 0:
        vec_dirname = np.vectorize(os.path.dirname)
        _, folder_start_ind = np.unique(
            vec_dirname(fp_arr_target), return_index=True)
        fps_by_folder = []
        for ind in range(len(folder_start_ind)):
            # print("b")
            if ind < len(folder_start_ind)-1:
                start_ind = folder_start_ind[ind]
                end_ind = folder_start_ind[ind+1]
                fps_by_folder.append(fp_arr_target[start_ind:end_ind])
                # print(start_ind, end_ind)
            else:
                start_ind = folder_start_ind[ind]
                fps_by_folder.append(fp_arr_target[start_ind:])
        return fps_by_folder
    return []


def dispatch(sem, argv, **kw):
    try:
        for args in argv[:-1]:
            subprocess.run(args, check=True,
                           stdout=subprocess.DEVNULL)
        for file in argv[-1]:
            os.remove(file)
    finally:
        sem.release()


# cdo -setrtoc2,1,inf,1,0 -setmisstoc,0 -selname,cph_resampled Agg_01_20220205223000.nc out_const.nc
# cdo -ifnotthen -lec,0 out_median.nc out_mean.nc out_final.nc
# cdo -b f32 gridboxmean,3,3 -selname,cph_resampled out_corr_miss.nc out_mean.nc
# cdo -setctomiss,0 -selname,cph_resampled Agg_01_20220205223000.nc out_corr_miss.nc
# cdo gridboxmedian,3,3 -selname,cph_resampled Agg_01_20220205223000.nc out_median.nc

def aggregation(resample_res_fps, agg_res_fps, agg_fact):
    sem = threading.Semaphore(8)   # pick a threshold here

    Ts = []
    for filename_ind in range(len(resample_res_fps)):
        resample_res_file = resample_res_fps[filename_ind]
        resample_res_mean = resample_res_file.removesuffix(".nc")+"_mean.nc"
        resample_res_median = resample_res_file.removesuffix(
            ".nc")+"_median.nc"
        resample_res_mask = resample_res_file.removesuffix(".nc")+"_mask.nc"
        resample_res_corr_miss = resample_res_file.removesuffix(
            ".nc")+"_corr_miss.nc"
        agg_res_file = agg_res_fps[filename_ind]
        argv = [["cdo", f"setctomiss,0",
                "-selname,cph_resampled,ctt_resampled", resample_res_file, resample_res_corr_miss],
                ["cdo", "-b", "f32", f"gridboxmean,{agg_fact},{agg_fact}",
                "-selname,cph_resampled,ctt_resampled", resample_res_corr_miss, resample_res_mean],
                ["cdo", "-setrtoc2,1,inf,1,0", "-setmisstoc,0",
                "-selname,cph_resampled", resample_res_file, resample_res_mask],
                ["cdo", f"gridboxmedian,{agg_fact},{agg_fact}",
                "-selname,cph_resampled", resample_res_mask, resample_res_median],
                ["cdo", "-ifnotthen", "-lec,0", resample_res_median,
                    resample_res_mean, agg_res_file],
                [resample_res_mean, resample_res_median, resample_res_mask, resample_res_corr_miss]]
        sem.acquire()
        T = threading.Thread(target=dispatch, args=(sem, argv))
        T.start()
        Ts.append(T)

    for T in Ts:
        T.join()

def format_folder(folder_fp_ind, folder_fps_CTX, folder_fps_CPP, folder_resample_res_fps, do_resampling=False):
    sem = threading.Semaphore(8)   # pick a threshold here

    Ts = []
    cpp_fp_list = folder_fps_CPP[folder_fp_ind]
    ctx_fp_list = folder_fps_CTX[folder_fp_ind]
    reformated_fp_list= folder_resample_res_fps[folder_fp_ind]
    for filename_ind in range(len(cpp_fp_list)):
        cpp_fp = cpp_fp_list[filename_ind]
        ctx_fp = ctx_fp_list[filename_ind]
        reformated_output_fp = reformated_fp_list[filename_ind]
        merged_fp = reformated_output_fp.removesuffix(".nc")+"_merged.nc"
        # cdo -chname,cph,cph_resampled -setgrid,/wolke_scratch/dnikolo/Glaciation_time_estimator/Data_preprocessing/grid.txt -apply,-selname,cph [ CPPin20230101084500405SVMSGI1MD.nc ] test_1.nc
        argv = [["cdo", "merge", "-selname,ctt", ctx_fp, "-selname,cph", cpp_fp,merged_fp ],
                ["cdo", f"-chname,cph,cph_resampled","-chname,ctt,ctt_resampled", "-setgrid,/wolke_scratch/dnikolo/Glaciation_time_estimator/Data_preprocessing/grid.txt",
                    merged_fp, reformated_output_fp],
                [merged_fp]]
        sem.acquire()
        T = threading.Thread(target=dispatch, args=(sem, argv))
        T.start()
        Ts.append(T)

    for T in Ts:
        T.join()

def resampling_worker(folder_fp_ind, aux_data, agg_fact, folder_fps_CTX, folder_fps_CPP, folder_resample_res_fps, folder_agg_res_fps, transformer, do_resampling=False):
    day_start_time = time.time()
    # Open relevant datasets
    # print(len(folder_fps_CTX[folder_fp_ind]))
    # print(len(folder_fps_CPP[folder_fp_ind]))
    input_ctx_ds = xr.open_mfdataset(
        list(folder_fps_CTX[folder_fp_ind]), parallel=True, chunks={"time": len(folder_fps_CTX[folder_fp_ind]), "x": aux_data.sizes["x"], "y": aux_data.sizes["y"]})
    input_cpp_ds = xr.open_mfdataset(
        list(folder_fps_CPP[folder_fp_ind]), parallel=True, chunks={"time": len(folder_fps_CPP[folder_fp_ind]), "x": aux_data.sizes["x"], "y": aux_data.sizes["y"]})
    
    if do_resampling:
        output_file = OutputResampledFile(
            input_cpp_ds, agg_fact=1)
    else:
        output_file = OutputNonResampledFile(
            input_cpp_ds, input_ctx_ds, agg_fact=1)
    # Add coordinate variables to the output file
    output_file.add_coords(transformer.new_cord_lat,
                           transformer.new_cord_lon)

    # Resample cpx dataset contents
    if do_resampling:
        resampled_ctt_data = transformer.remap_data(
            input_ctx_ds["ctt"])
        resampled_cth_data = transformer.remap_data(
            input_ctx_ds["cth"])
        output_file.set_ctx_output_variables(
            resampled_ctt_data, resampled_cth_data)
    else:
        output_file.set_ctx_output_variables()
    # del resampled_ctt_data, resampled_cth_data
    input_ctx_ds.close()

    # Resample cpp dataset contents
    if do_resampling:
        resampled_cph_data = transformer.remap_data(
            input_cpp_ds["cph"])
        output_file.set_cpp_output_variables(
            resampled_cph_data)
    else:
        output_file.set_cpp_output_variables()
    # Generate output file and save result
    resample_res_fps = folder_resample_res_fps[folder_fp_ind]
    agg_res_fps = folder_agg_res_fps[folder_fp_ind]
    output_file.save_file(resample_res_fps)
    # Close dataset
    input_cpp_ds.close()
    resample_end_time = time.time()
    print(
        f"Resampled day {folder_fp_ind} in {round(resample_end_time-day_start_time,2)}s starting with fp: {folder_fps_CTX[folder_fp_ind][0]}")
    aggregation(resample_res_fps, agg_res_fps, agg_fact)
    agg_end_time = time.time()
    print(
        f"Aggregated day {folder_fp_ind}/{len(folder_resample_res_fps)} in {round(agg_end_time - resample_end_time,2)}s: {agg_res_fps[0]}")


def resample_pole(pole, target_filenames, aux_fps, agg_fact, n_workers):
    transformer = ProjectionTransformer()
    aux_data = xr.load_dataset(os.path.join(
        CLAAS_FP, aux_fps[pole]), decode_times=False)
    transformer.generate_lat_lon_prj(aux_data)
    folder_fps_CTX = fps_by_folder(target_filenames[pole]["resample_CTX"])
    folder_fps_CPP = fps_by_folder(target_filenames[pole]["resample_CPP"])
    folder_resample_res_fps = fps_by_folder(
        target_filenames[pole]["resample_res"])
    folder_agg_res_fps = fps_by_folder(
        target_filenames[pole]["agg_res"])
    par_worker = partial(resampling_worker, aux_data=aux_data, agg_fact=agg_fact, folder_fps_CTX=folder_fps_CTX, folder_fps_CPP=folder_fps_CPP,
                         folder_resample_res_fps=folder_resample_res_fps, folder_agg_res_fps=folder_agg_res_fps, transformer=transformer)
    ind_to_iterate = range(len(folder_fps_CTX))
    # if n_workers > 1:
    #     pole_pool = NestablePool(n_workers)
    #     pole_pool.map(par_worker, ind_to_iterate)
    #     pole_pool.close()
    #     pole_pool.join()
    # elif n_workers == 1:
    warnings.warn("Working without multiprocessing")
    for ind in ind_to_iterate:
        par_worker(ind)

    aux_data.close()


def generate_resampled_output(target_filenames, config, n_tot_workers=6):
    pole_folders = config['pole_folders']
    aux_fps = config['aux_fps']
    agg_fact = config['agg_fact']
    start_time = time.time()
    # pool = NestablePool(len(pole_folders))
    # part_resample_pole_fun = partial(resample_pole, target_filenames=target_filenames,
    #                                  aux_fps=aux_fps, agg_fact=agg_fact, n_workers=int(n_tot_workers/len(pole_folders)))
    # pool.map(part_resample_pole_fun, pole_folders)
    # pool.close()
    # pool.join()
    part_resample_pole_fun = partial(resample_pole, target_filenames=target_filenames,
                                     aux_fps=aux_fps, agg_fact=agg_fact, n_workers=int(n_tot_workers))
    for pole in pole_folders:
        part_resample_pole_fun(pole)
    end_time = time.time()
    print(f"Total resampling + agg time = {round(end_time-start_time,2)}")


def generate_filtered_output_fps(day_fp, agg_fact, min_temp, max_temp):
    output_fp = day_fp
    output_fp = np.char.replace(output_fp, "Resampled_Data", "Filtered_Data")
    output_fp = np.char.replace(
        output_fp, f"Agg_{agg_fact:02}", f"Agg_{agg_fact:02}_T_{abs(min_temp):02}_{abs(max_temp):02}")
    os.makedirs(os.path.dirname(output_fp[0]), exist_ok=True)
    return output_fp


# def filtering_worker(day_fp_to_filter, temp_bounds, agg_fact):
#     # print("day_fp_to_filter: ", len(day_fp_to_filter))
#     combined_ds = xr.open_mfdataset(
#         list(day_fp_to_filter), parallel=True)
#     for temp_ind in range(len(temp_bounds[0])):
#         min_temp = temp_bounds[0][temp_ind]
#         max_temp = temp_bounds[1][temp_ind]
#         output_combined_ds = combined_ds.copy()
#         mask = (combined_ds['ctt_resampled'] >= 273.15 +
#                 min_temp) & (combined_ds['ctt_resampled'] <= 273.15+max_temp)
#         output_combined_ds['cph_filtered'] = xr.where(
#             mask, combined_ds['cph_resampled'], 0).compute()
#         output_combined_ds = output_combined_ds.drop_vars(
#             ["cph_resampled", "ctt_resampled"])
#         output_fps = generate_filtered_output_fps(
#             day_fp_to_filter, agg_fact, min_temp, max_temp)
#         _, dataset_list = zip(
#             *(output_combined_ds.groupby("time")))
#         # print(len(folder_fps_CTX[folder_fp_ind]))
#         # print("output_fps: ", len(output_fps))
#         # print("dataset_list: ", len(dataset_list))
#         xr.save_mfdataset(dataset_list, list(output_fps))
#         output_combined_ds.close()
#     combined_ds.close()

# cdo -setmisstoc,0 -expr,"cph_filtered = cph_resampled*(ctt_resampled<253.15 && ctt_resampled>243.15)" Agg_03_20220101221500.nc test.nc


def filtering_worker_cdo(day_fp_to_filter, temp_bounds, agg_fact):
    sem = threading.Semaphore(4)   # pick a threshold here
    for temp_ind in range(len(temp_bounds[0])):
        min_temp = temp_bounds[0][temp_ind]
        max_temp = temp_bounds[1][temp_ind]
        outpur_fps = generate_filtered_output_fps(
            day_fp_to_filter, agg_fact, min_temp, max_temp)
        Ts = []
        for file_ind, output_fp in enumerate(outpur_fps):
            sem.acquire()
            argv = [["cdo", "-setmisstoc,0", f'-expr,cph_filtered = cph_resampled*(ctt_resampled<{(273.15+max_temp):0.2f} && ctt_resampled>{(273.15+min_temp):0.2f})', day_fp_to_filter[file_ind], output_fp],
                    []
                    ]
            T = threading.Thread(target=dispatch, args=(sem, argv))
            T.start()
            Ts.append(T)
        for T in Ts:
            T.join()
    return


def generate_filtered_files(target_filenames, t_deltas, agg_fact, n_workers=8):
    pole_folders = ["np", "sp"]
    temp_bounds = generate_temp_range(t_deltas)
    for pole in pole_folders:
        filter_start_time = time.time()
        pool = Pool(n_workers)
        pool.map(partial(filtering_worker_cdo, temp_bounds=temp_bounds,
                 agg_fact=agg_fact), fps_by_folder(target_filenames[pole]["filter"]))
        pool.close()
        pool.join()
        filter_end_time = time.time()
        print(
            f"Filtered {pole} in {round(filter_end_time-filter_start_time,2)}s")


if __name__ == "__main__":
    print("Generating target filenames")

    config = read_config()
    t_deltas = config["t_deltas"]
    # config = parse_cmd_args()
    print(config['start_time'],
          config['end_time'], config['agg_fact'])
    target_filenames = generate_filename_dict()
    # print(target_filenames)
    print("Target filenames generated")
    print("Resampling needed files")
    generate_resampled_output(target_filenames, config)
    print("Needed files resampled. Start filtering")
    generate_filtered_files(target_filenames, t_deltas,
                            agg_fact=config['agg_fact'])
    print("Filtering complete")
