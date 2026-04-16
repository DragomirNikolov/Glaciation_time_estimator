from datetime import datetime, timedelta
import numpy as np
import os
from pandas import date_range
import numpy.core.defchararray as np_f
from glaciation_time_estimator.auxiliary_func.config_reader import read_config
# from ..Helper_fun import generate_temp_range


def round_time(tm, round_increment, round_up=False):
    """Rounds down the datetime `tm` down to the nearest `round_increment` in minutes."""
    if round_up:
        return tm - timedelta(minutes=tm.minute % round_increment, seconds=tm.second, microseconds=tm.microsecond) + timedelta(minutes=round_increment)
    return tm - timedelta(minutes=tm.minute % round_increment,
                          seconds=tm.second,
                          microseconds=tm.microsecond)


def intertwine_iterable(*lists):
    tot_lenth = 0
    for list in lists:
        tot_lenth += len(list)
    intertwined_list = [None]*tot_lenth
    for list_ind in range(len(lists)):
        intertwined_list[list_ind::len(lists)] = lists[list_ind]
    return intertwined_list


class MissingFilesSearcher:
    def __init__(self, config, exclude_existing=True):
        round_increment = 15
        self.start_time = round_time(config['start_time'], round_increment)
        self.end_time = round_time(config['end_time'], round_increment)
        assert (self.start_time <
                self.end_time), "Start time should be before end time after rounding doun to nearest 15 minutes"
        self.t_deltas = config['t_deltas']
        self.temps_to_check = self.gen_temps_to_check()
        self.min_temp_arr = config['min_temp_arr']
        self.max_temp_arr = config['max_temp_arr']
        # CLAAS_FP shouldnt contain the CPP
        self.CLAAS_FP = config['CLAAS_fp'].replace(f"{os.uname()[1]}:","")
        # print(CLAAS_FP)
        self.pole_split = config['pole_split']
        self.pole_folders = config['pole_folders']
        self.agg_fact = config['agg_fact']
        self.do_resampling = config['Resample']
        self.exclude_existing = exclude_existing
        # self.boundary_date = datetime(
        #     year=2021, month=1, day=1, hour=0, minute=0, second=0)
        self.boundary_date = config['struct_boundary_date']
        self.config = config

    def gen_filename_list(self, start_time=None, end_time=None, file_format="%Y/%m/%d/CPPin%Y%m%d%H%M%S.nc", freq=timedelta(minutes=15), inclusive="both"):
        if start_time is None:
            start_time = self.start_time
        else:
            start_time = round_time(start_time, 15)

        if end_time is None:
            end_time = self.end_time
        else:
            end_time = round_time(end_time, 15)
        # filenames = [start_time.strftime(file_format)]
        filenames = date_range(start_time, end_time,
                               freq=freq, inclusive=inclusive).strftime(file_format).to_list()
        return filenames

    def gen_temps_to_check(self):
        temps_to_check_max = [0 for dt in self.t_deltas]
        temps_to_check_min = [abs(0-dt) for dt in self.t_deltas]
        return temps_to_check_max, temps_to_check_min

    def gen_filtered_filenames(self, CLAAS_FP_POLE):
        filtered_first_dt_filenames = []
        for temp_ind in range(len(self.temps_to_check[0])):
            min_temp = self.temps_to_check[0][temp_ind]
            max_temp = self.temps_to_check[1][temp_ind]
            if self.do_resampling:
                filtered_fp_format = os.path.join(
                    CLAAS_FP_POLE, f"%Y/%m/%d/R_Agg_{self.agg_fact:02}_T_{max_temp:02}_{min_temp:02}_%Y%m%d%H%M%S.nc")
            else:
                filtered_fp_format = os.path.join(
                    CLAAS_FP_POLE, f"%Y/%m/%d/Agg_{self.agg_fact:02}_T_{max_temp:02}_{min_temp:02}_%Y%m%d%H%M%S.nc")
            filtered_first_dt_filenames.append(
                np.array(self.gen_filename_list(file_format=filtered_fp_format)))
        filtered_first_dt_filenames = np.array(
            intertwine_iterable(*(filtered_first_dt_filenames)))
        return filtered_first_dt_filenames

    def are_missing(self, filenames):
        if len(filenames) != 0:
            if self.exclude_existing:
                vec_isfile = np.vectorize(os.path.isfile)
                file_exists_bool = vec_isfile(filenames)
                return np.invert(file_exists_bool)
            else:
                return np.full(filenames.shape, True)
        else:
            return np.array([], dtype=bool)

    def gen_missing_filtered_filenames(self, CLAAS_FP_POLE):
        filtered_first_dt_filenames = self.gen_filtered_filenames(
            CLAAS_FP_POLE)
        self.filtered_file_missing_bool = self.are_missing(
            filtered_first_dt_filenames)
        # if len(self.filtered_file_missing_bool)!=0:
        self.missing_filtered_filenames = filtered_first_dt_filenames[
            self.filtered_file_missing_bool]
        # return self.missing_filtered_filenames

    def gen_resample_ind(self, file_missing_bool):
        n_temps = len(self.temps_to_check[0])
        resample_ind = np.zeros(
            int(len(file_missing_bool)/n_temps), dtype=bool)
        for temp_ind in range(n_temps):
            resample_ind = resample_ind | file_missing_bool[temp_ind::n_temps]
        return resample_ind

    def gen_filenames_to_filter(self, CLAAS_FP_POLE):
        if self.do_resampling:
            resampled_fp_format = os.path.join(
                CLAAS_FP_POLE, f"%Y/%m/%d/R_Agg_{self.agg_fact:02}_%Y%m%d%H%M%S.nc")
        else:
            resampled_fp_format = os.path.join(
                CLAAS_FP_POLE, f"%Y/%m/%d/Agg_{self.agg_fact:02}_%Y%m%d%H%M%S.nc")
        resample_filenames = np.array(
            self.gen_filename_list(file_format=resampled_fp_format))
        self.resample_ind = self.gen_resample_ind(
            self.filtered_file_missing_bool)
        self.filenames_to_filter = resample_filenames[self.resample_ind]

    def gen_unpr_filenames_to_resample(self, CLAAS_FP_POLE):
        cpp_fp_format = [os.path.join(
            CLAAS_FP_POLE, "%Y/%m/%d/CPPin%Y%m%d%H%M%S405SVMSG01MD.nc"), os.path.join(
            CLAAS_FP_POLE, "%Y/%m/%d/CPPin%Y%m%d%H%M%S405SVMSGI1MD.nc")]
        ctx_fp_format = [os.path.join(
            CLAAS_FP_POLE, "%Y/%m/%d/CTXin%Y%m%d%H%M%S405SVMSG01MD.nc"), os.path.join(
            CLAAS_FP_POLE, "%Y/%m/%d/CTXin%Y%m%d%H%M%S405SVMSGI1MD.nc")]
        ind_to_resample = self.are_missing(self.filenames_to_filter)
        if ind_to_resample is not None:
            self.agg_result_names = self.filenames_to_filter[ind_to_resample]
            if self.do_resampling:
                self.resample_result_names = np.char.replace(
                    self.agg_result_names, f"R_Agg_{self.agg_fact:02}", "R_Agg_01")
            else:
                self.resample_result_names = np.char.replace(
                        self.agg_result_names, f"Agg_{self.agg_fact:02}", "Agg_01")
            # print(ind_to_resample)
            if (self.start_time < self.boundary_date) & (self.end_time < self.boundary_date):
                self.cpp_files_to_resample = np.array(self.gen_filename_list(
                    file_format=cpp_fp_format[0]))[self.resample_ind][ind_to_resample]
                self.ctx_files_to_resample = np.array(self.gen_filename_list(
                    file_format=ctx_fp_format[0]))[self.resample_ind][ind_to_resample]
            elif (self.start_time >= self.boundary_date) & (self.end_time >= self.boundary_date):
                self.cpp_files_to_resample = np.array(self.gen_filename_list(
                    file_format=cpp_fp_format[1]))[self.resample_ind][ind_to_resample]
                self.ctx_files_to_resample = np.array(self.gen_filename_list(
                    file_format=ctx_fp_format[1]))[self.resample_ind][ind_to_resample]
            else:
                self.cpp_files_to_resample = self.cross_bound_date_name_generator(
                    cpp_fp_format, ind_to_resample)[self.resample_ind][ind_to_resample]
                self.ctx_files_to_resample = self.cross_bound_date_name_generator(
                    ctx_fp_format, ind_to_resample)[self.resample_ind][ind_to_resample]
            ind_to_agg = self.are_missing(self.resample_result_names)
            self.resample_result_names =  self.resample_result_names[ind_to_agg]
            self.cpp_files_to_resample =  self.cpp_files_to_resample[ind_to_agg]
            self.ctx_files_to_resample =  self.ctx_files_to_resample[ind_to_agg]

    def cross_bound_date_name_generator(self, fp_format_list, ind_to_resample):
        result = []
        start_end_time = [self.start_time, self.boundary_date, self.end_time]
        inclusive_list = ["left", "both"]
        for i in range(2):
            # print(fp_format_list[i], ind_to_resample)
            result.append(self.cross_bound_date_name_generator_single_it(
                fp_format_list[i], ind_to_resample, start_end_time[i:i+2], inclusive=inclusive_list[i]))
        return np.concatenate(result)

    def cross_bound_date_name_generator_single_it(self, fp_format, ind_to_resample, start_end_time=[None, None], inclusive="both"):
        files_to_resample = np.array(self.gen_filename_list(start_time=start_end_time[0], end_time=start_end_time[1],
                                                            file_format=fp_format, inclusive=inclusive))
        ind_short = ind_to_resample[:len(files_to_resample)]
        return files_to_resample[ind_short]

    def gen_target_filenames(self):
        if self.pole_split:
            self.result_dict = {pole: {"filter": None, "resample_CPP": None,
                                       "resample_CTX": None} for pole in self.pole_folders}
            for pole in self.pole_folders:
                CLAAS_FP_POLE = os.path.join(self.CLAAS_FP, pole)
                self.gen_missing_filtered_filenames(
                    os.path.join(self.CLAAS_FP, "Filtered_Data", pole))
                self.gen_filenames_to_filter(os.path.join(
                    self.CLAAS_FP, "Resampled_Data", pole))
                self.gen_unpr_filenames_to_resample(CLAAS_FP_POLE)
                self.result_dict[pole]["resample_CPP"] = self.cpp_files_to_resample
                self.result_dict[pole]["resample_CTX"] = self.ctx_files_to_resample
                self.result_dict[pole]["resample_res"] = self.resample_result_names
                self.result_dict[pole]["agg_res"] = self.agg_result_names
                self.result_dict[pole]["filter"] = self.filenames_to_filter

        else:
            self.result_dict = {"filter": None,
                                "resample_CPP": None, "resample_CTX": None}
            self.gen_missing_filtered_filenames(self.CLAAS_FP)
            self.gen_filenames_to_filter(self.CLAAS_FP)
            self.gen_unpr_filenames_to_resample(self.CLAAS_FP)
            self.result_dict["filter"] = self.filenames_to_filter
            self.result_dict["resample_CPP"] = self.cpp_files_to_resample
            self.result_dict["resample_CTX"] = self.ctx_files_to_resample
            self.result_dict["resample_res"] = self.resample_result_names
            # raise NotImplementedError("Not implemented for non split poles")

    def gen_cloudtrack_filenames(self, job_output_folder):
        cloudtracks_fps = {}
        folder_name = self.config["time_folder_name"]
        filename_format = "cloudtracks_%Y%m%d_%H%M%S.nc"
        for temp_ind in range(len(self.min_temp_arr)):
            min_temp = abs(self.min_temp_arr[temp_ind])
            max_temp = abs(self.max_temp_arr[temp_ind])
            if self.do_resampling:
                cloudtracks_fp_format = os.path.join(
                    job_output_folder, f"R_Agg_{self.agg_fact:02}_T_{min_temp:02}_{max_temp:02}", folder_name, "pixel_path_tracking", folder_name, filename_format)
            else:
                cloudtracks_fp_format = os.path.join(
                    job_output_folder, f"Agg_{self.agg_fact:02}_T_{min_temp:02}_{max_temp:02}", folder_name, "pixel_path_tracking", folder_name, filename_format)

            key = f"{abs(min_temp)}_{abs(max_temp)}"
            cloudtracks_fps[key] = {}
            cloudtracks_fps[key]["cloudtracks"] = np.array(
                self.gen_filename_list(file_format=cloudtracks_fp_format))
            if self.do_resampling:
                stats_fp_format = os.path.join(
                    job_output_folder, f"R_Agg_{self.agg_fact:02}_T_{min_temp:02}_{max_temp:02}", folder_name, "stats")
            else:
                stats_fp_format = os.path.join(
                    job_output_folder, f"Agg_{self.agg_fact:02}_T_{min_temp:02}_{max_temp:02}", folder_name, "stats")
            cloudtracks_fps[key]["trackstats"] = os.path.join(
                stats_fp_format, f"trackstats_{folder_name}.nc")
            cloudtracks_fps[key]["tracknumbers"] = os.path.join(
                stats_fp_format, f"tracknumbers_{folder_name}.nc")
            cloudtracks_fps[key]["trackstats_final"] = os.path.join(
                stats_fp_format, f"trackstats_final_{folder_name}.nc")
            cloudtracks_fps[key]["trackstats_sparce"] = os.path.join(
                stats_fp_format, f"trackstats_sparce_{folder_name}.nc")
        return cloudtracks_fps


def check_existance_of_unpr_files(searcher):
    file_array_names = ["resample_CPP", "resample_CTX"]
    for pole in searcher.pole_folders:
        for file_array_name in file_array_names:
            filenames = searcher.result_dict[pole][file_array_name]
            missing_ind = searcher.are_missing(filenames)
            if missing_ind is not None:
                if (missing_ind).any():
                    missing_files = filenames[missing_ind]
                    raise FileExistsError(
                        f"There are missing {pole} {file_array_name} files \n {missing_files[0]} \n len(filenames): {len(filenames)} \n len(missing_filenames): {len(missing_files)}")
            else:
                print(f"All {pole} {file_array_name} files are present")


def generate_filename_dict(config, exclude_existing=True):
    searcher = MissingFilesSearcher(
        config, exclude_existing=exclude_existing)
    searcher.gen_target_filenames()
    if exclude_existing:
        check_existance_of_unpr_files(searcher)
    return searcher.result_dict


if __name__ == "__main__":
    print("Start")
    # start_time = datetime(2020, 1, 1, 0, 0)
    # end_time = datetime(2021, 11, 29, 23, 59)
    # t_deltas = [3, 5]
    # searcher = MissingFilesSearcher(start_time, end_time, t_deltas)
    # searcher.gen_target_filenames()
    # check_existance_of_unpr_files(searcher)
    result_dict = generate_filename_dict(read_config())
    print(result_dict)
    print("Done")
