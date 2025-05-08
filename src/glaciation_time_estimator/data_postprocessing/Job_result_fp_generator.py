import os
from glaciation_time_estimator.data_preprocessing.File_name_generator import MissingFilesSearcher
from glaciation_time_estimator.auxiliary_func.config_reader import read_config


def generate_tracking_filenames(config):
    target_fp_dict = {}
    fp_gen = MissingFilesSearcher(config)

    # stats_fp_format = os.path.join(
    #             config['job_output_folder'], f"Agg_{self.agg_fact:02}_T_{min_temp:02}_{max_temp:02}",folder_name)

    for pole in config['pole_folders']:
        job_output_dir = os.path.join(config['job_output_fp'], pole)
        target_fp_dict[pole] = fp_gen.gen_cloudtrack_filenames(job_output_dir)
    return target_fp_dict
#/cluster/work/climate/dnikolo/Job_output/Agg_3_T_5_0_t_202301010000_202301072345/np/stats/trackstats_20230101.0000_20230107.2345.nc



if __name__ == "__main__":
    print(generate_tracking_filenames(read_config()))
# pole/Agg_3_T_5_0/YmD.HM(start)_YmD.HM(end)/pixel_path_tracking/
# pole/Agg_3_T_5_0/YmD.HM(start)_YmD.HM(end)/stats/
# pole/Agg_3_T_5_0/YmD.HM(start)_YmD.HM(end)/tracking/
# pole/Agg_3_T_5_0/aux/YmD.HM(start)_YmD.HM(end)/log
# pole/Agg_3_T_5_0/aux/YmD.HM(start)_YmD.HM(end)/setup
