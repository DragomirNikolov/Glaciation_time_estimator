import os
import xarray as xr
import numpy as np
import subprocess
import time
import threading
from multiprocessing import Pool
from functools import partial
from glaciation_time_estimator.auxiliary_func.config_reader import read_config
from glaciation_time_estimator.auxiliary_func.Helper_fun import generate_temp_range
from glaciation_time_estimator.data_preprocessing.Resample_data import ProjectionTransformer
from glaciation_time_estimator.data_preprocessing.File_name_generator import generate_filename_dict
from glaciation_time_estimator.data_preprocessing.Output_file_generation import OutputResampledFile
import warnings

# global CLAAS_FP
# CLAAS_FP = os.environ["CLAAS_DIR"]
# if CLAAS_FP == "":
#     raise ValueError("CLAAS_DIR is not defined")


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
            # subprocess.run(args, check=True)
        for file in argv[-1]:
            os.remove(file)
    finally:
        sem.release()


def format_folder(folder_fp_ind, folder_fps_CTX, folder_fps_CPP, folder_resample_res_fps, grid_fp, n_threads=8):
    formatting_start_time = time.time()
    sem = threading.Semaphore(n_threads)   # pick a threshold here

    Ts = []
    cpp_fp_list = folder_fps_CPP[folder_fp_ind]
    ctx_fp_list = folder_fps_CTX[folder_fp_ind]
    reformated_fp_list = folder_resample_res_fps[folder_fp_ind]
    for filename_ind in range(len(cpp_fp_list)):
        cpp_fp = cpp_fp_list[filename_ind]
        ctx_fp = ctx_fp_list[filename_ind]
        reformated_output_fp = reformated_fp_list[filename_ind]
        merged_fp = reformated_output_fp.removesuffix(".nc")+"_merged.nc"
        # cdo -chname,cph,cph_resampled -setgrid,/wolke_scratch/dnikolo/Glaciation_time_estimator/Data_preprocessing/grid.txt -apply,-selname,cph [ CPPin20230101084500405SVMSGI1MD.nc ] test_1.nc
        os.makedirs(os.path.dirname(merged_fp), exist_ok=True)
        argv = [["cdo", "-O", "merge", "-selname,ctt", ctx_fp, "-selname,cph", cpp_fp, merged_fp],
                ["cdo", "-O", f"-chname,cph,cph_resampled", "-chname,ctt,ctt_resampled", f"-setgrid,{grid_fp}",
                    merged_fp, reformated_output_fp],
                [merged_fp]]
        sem.acquire()
        T = threading.Thread(target=dispatch, args=(sem, argv))
        T.start()
        Ts.append(T)

    for T in Ts:
        T.join()
    formatting_end_time = time.time()
    print(
        f"Formated day {folder_fp_ind} in {round(formatting_end_time - formatting_start_time,2)}s starting with fp: {folder_fps_CTX[folder_fp_ind][0]}")


# Used if Resample: True in the config file
def resample_folder(folder_fp_ind, aux_data, agg_fact, folder_fps_CTX, folder_fps_CPP, folder_resample_res_fps, folder_agg_res_fps, transformer):
    day_start_time = time.time()
    # Open relevant datasets
    # print(len(folder_fps_CTX[folder_fp_ind]))
    # print(len(folder_fps_CPP[folder_fp_ind]))
    input_ctx_ds = xr.open_mfdataset(
        list(folder_fps_CTX[folder_fp_ind]), parallel=True, chunks={"time": len(folder_fps_CTX[folder_fp_ind]), "x": aux_data.sizes["x"], "y": aux_data.sizes["y"]})
    input_cpp_ds = xr.open_mfdataset(
        list(folder_fps_CPP[folder_fp_ind]), parallel=True, chunks={"time": len(folder_fps_CPP[folder_fp_ind]), "x": aux_data.sizes["x"], "y": aux_data.sizes["y"]})

    output_file = OutputResampledFile(
        input_cpp_ds, agg_fact=1)
    # Add coordinate variables to the output file
    output_file.add_coords(transformer.new_cord_lat,
                           transformer.new_cord_lon)

    # Resample cpx dataset contents
    resampled_ctt_data = transformer.remap_data(
        input_ctx_ds["ctt"])
    resampled_cth_data = transformer.remap_data(
        input_ctx_ds["cth"])
    output_file.set_ctx_output_variables(
        resampled_ctt_data, resampled_cth_data)
    # del resampled_ctt_data, resampled_cth_data
    input_ctx_ds.close()

    # Resample cpp dataset contents
    resampled_cph_data = transformer.remap_data(
        input_cpp_ds["cph"])
    output_file.set_cpp_output_variables(
        resampled_cph_data)

    # Generate output file and save result
    resample_res_fps = folder_resample_res_fps[folder_fp_ind]
    agg_res_fps = folder_agg_res_fps[folder_fp_ind]
    output_file.save_file(resample_res_fps)
    # Close dataset
    input_cpp_ds.close()
    resample_end_time = time.time()
    print(
        f"Resampled day {folder_fp_ind} in {round(resample_end_time-day_start_time,2)}s starting with fp: {folder_fps_CTX[folder_fp_ind][0]}")


# Aggregation using cdo
def aggregte_folder(folder_fp_ind, folder_resample_res_fps, folder_agg_res_fps, agg_fact, n_threads=8):
    agg_start_time = time.time()
    sem = threading.Semaphore(n_threads)   # pick a threshold here
    resample_res_fps = folder_resample_res_fps[folder_fp_ind]
    agg_res_fps = folder_agg_res_fps[folder_fp_ind]
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
    agg_end_time = time.time()
    print(
        f"Aggregated day {folder_fp_ind}/{len(folder_resample_res_fps)} in {round(agg_end_time - agg_start_time,2)}s\nStarting with {agg_res_fps[0]}")


def filter_folder(day_fp_to_filter, temp_bounds, agg_fact, n_threads=8):
    sem = threading.Semaphore(n_threads)   # pick a threshold here
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


def prepare_pole(pole, target_filenames, config, n_workers):
    aux_fps = config['aux_fps']
    agg_fact = config['agg_fact']
    n_threads = config["n_preproc_threads"]
    folder_fps_CTX = fps_by_folder(target_filenames[pole]["resample_CTX"])
    folder_fps_CPP = fps_by_folder(target_filenames[pole]["resample_CPP"])
    folder_resample_res_fps = fps_by_folder(
        target_filenames[pole]["resample_res"])
    folder_agg_res_fps = fps_by_folder(
        target_filenames[pole]["agg_res"])
    if config["Resample"]:
        transformer = ProjectionTransformer()
        aux_data = xr.load_dataset(os.path.join(
            CLAAS_FP, aux_fps[pole]), decode_times=False)
        transformer.generate_lat_lon_prj(aux_data)
        preparation_worker = partial(resample_folder, aux_data=aux_data, agg_fact=agg_fact, folder_fps_CTX=folder_fps_CTX, folder_fps_CPP=folder_fps_CPP,
                                     folder_resample_res_fps=folder_resample_res_fps, folder_agg_res_fps=folder_agg_res_fps, transformer=transformer)
    else:
        preparation_worker = partial(format_folder, folder_fps_CTX=folder_fps_CTX,
                                     folder_fps_CPP=folder_fps_CPP, folder_resample_res_fps=folder_resample_res_fps, grid_fp=config["grid_fps"][pole], n_threads=n_threads)

    aggregation_worker = partial(aggregte_folder, folder_resample_res_fps=folder_resample_res_fps,
                                 folder_agg_res_fps=folder_agg_res_fps, agg_fact=agg_fact, n_threads=n_threads)

    ind_to_iterate = range(len(folder_fps_CTX))
    if n_workers > 1:
        pole_pool = Pool(n_workers)
        pole_pool.map(preparation_worker, ind_to_iterate)
        pole_pool.close()
        pole_pool.join()
        pole_pool = Pool(n_workers)
        pole_pool.map(aggregation_worker, ind_to_iterate)
        pole_pool.close()
        pole_pool.join()

    elif n_workers == 1:
        warnings.warn("Working without multiprocessing")
        for ind in ind_to_iterate:
            preparation_worker(ind)
        for ind in ind_to_iterate:
            aggregation_worker(ind)
    if config["Resample"]:
        aux_data.close()


def prepare_all_files(target_filenames, config):
    pole_folders = config['pole_folders']
    n_tot_workers = config["n_preproc_cores"]
    start_time = time.time()
    # pool = NestablePool(len(pole_folders))
    # part_resample_pole_fun = partial(prepare_pole, target_filenames=target_filenames,
    #                                  aux_fps=aux_fps, agg_fact=agg_fact, n_workers=int(n_tot_workers/len(pole_folders)))
    # pool.map(part_resample_pole_fun, pole_folders)
    # pool.close()
    # pool.join()
    part_prepare_pole_fun = partial(prepare_pole, target_filenames=target_filenames,
                                    config=config, n_workers=int(n_tot_workers/len(pole_folders)))
    for pole in pole_folders:
        part_prepare_pole_fun(pole)
    end_time = time.time()
    print(f"Total resampling + agg time = {round(end_time-start_time,2)}")


def generate_filtered_output_fps(day_fp, agg_fact, min_temp, max_temp):
    output_fp = day_fp
    output_fp = np.char.replace(output_fp, "Resampled_Data", "Filtered_Data")
    output_fp = np.char.replace(
        output_fp, f"Agg_{agg_fact:02}", f"Agg_{agg_fact:02}_T_{abs(min_temp):02}_{abs(max_temp):02}")
    os.makedirs(os.path.dirname(output_fp[0]), exist_ok=True)
    return output_fp


def generate_filtered_files(config, target_filenames, t_deltas, agg_fact, n_workers=8):
    pole_folders = config["pole_folders"]
    temp_bounds = generate_temp_range(t_deltas)
    for pole in pole_folders:
        filter_start_time = time.time()
        pool = Pool(n_workers)
        pool.map(partial(filter_folder, temp_bounds=temp_bounds,
                 agg_fact=agg_fact, n_threads = config["n_preproc_threads"]), fps_by_folder(target_filenames[pole]["filter"]))
        pool.close()
        pool.join()
        filter_end_time = time.time()
        print(
            f"Filtered {pole} in {round(filter_end_time-filter_start_time,2)}s")


def preprocessing_pipeline(config):
    t_deltas = config["t_deltas"]
    global CLAAS_FP
    CLAAS_FP = config["CLAAS_fp"]
    if CLAAS_FP == "":
        raise ValueError("CLAAS_DIR is not defined")
    print("Generating target filenames")
    target_filenames = generate_filename_dict(config)
    # print(target_filenames)
    print("Target filenames generated")
    print("Resampling needed files")
    
    prepare_all_files(target_filenames, config)
    print("Needed files resampled. Start filtering")
    generate_filtered_files(config, target_filenames, t_deltas,
                            agg_fact=config['agg_fact'],n_workers=config["n_preproc_cores"])
    print("Filtering complete")


if __name__ == "__main__":
    # Read the given GTE config file - its file path should be specified as a command line argument -cf <path_to_config>
    config = read_config()
    print(
        f"Start time: {config['start_time']}\nEnd time: {config['end_time']}\nAggreagation factor: {config['agg_fact']}")
    preprocessing_pipeline(config)
