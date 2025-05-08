# from toolz import pipe
# import xarray as xr
from datetime import datetime, timedelta
import numpy as np
import os
from dateutil.relativedelta import relativedelta
from pandas import date_range


# Specify the folder path
# TODO: Make it extract an env variable
global CLAAS_FP
CLAAS_FP = "/cluster/work/climate/dnikolo/CLAAS_Data/"


def round_time(tm, round_increment):
    """Rounds down the datetime `tm` down to the nearest `round_increment` in minutes."""
    return tm - timedelta(minutes=tm.minute % round_increment,
                          seconds=tm.second,
                          microseconds=tm.microsecond)


def generate_month_folder_names(start_time, end_time, round_increment=15):
    """
    Generates a list of month folder names based on time interval.

    Parameters:
        start_time (datetime): Start time.
        end_time (datetime): End time.
        round_increment (int): Time interval in minutes.

    Returns:
        array: List of folder paths for each time interval.
    """
    # Round start and end times
    start_time = round_time(start_time, round_increment)
    end_time = round_time(end_time, round_increment)
    folder_format = "%Y_%m"
    month_folder_names = [start_time.strftime(folder_format)]
    month_folder_names.extend(date_range(start_time, end_time,
                                         freq='MS').strftime(folder_format).to_list())
    # month_folder_names=np.array([os.path.join(t.strftime("%Y_%m")) for t in time_range])
    return set(month_folder_names)


def first_day_of_month(month_str):
    return datetime.strptime(month_str, "%Y_%m").replace(day=1, hour=0, minute=0, second=0)


def last_day_of_month(month_str):
    any_day = datetime.strptime(month_str, "%Y_%m")
    # The day 28 exists in every month. 4 days later, it's always next month
    next_month = any_day.replace(day=28) + timedelta(days=4)
    # subtracting the number of the current day brings us back one month
    return (next_month - timedelta(days=next_month.day)).replace(hour=23, minute=59, second=59)


def gen_filename_list(start_time, end_time):
    folder_format = "%Y_%m"
    file_format = folder_format+"/CPH/CPPin%Y%m%d%H%M%S.nc"
    filenames = [start_time.strftime(file_format)]
    filenames.extend(date_range(start_time, end_time,
                                freq=timedelta(minutes=15)).strftime(file_format).to_list())
    return filenames


def generate_filenames(start_time, end_time, target_months, round_increment=15):
    """
    Generates a list of folder paths based on time intervals.

    Parameters:
        start_time (datetime): Start time.
        end_time (datetime): End time.
        round_increment (int): Time interval in minutes.

    Returns:
        list: List of folder paths for each time interval.
    """
    # Round start and end times
    start_time = round_time(start_time, round_increment)
    end_time = round_time(end_time, round_increment)
    folder_format = "%Y_%m"
    file_format = folder_format+"/CPH/CPPin%Y%m%d%H%M%S.nc"
    # Generate array of time incremented times
    filenames = []
    for month in target_months:
        if month == start_time.strftime(folder_format):
            month_end = last_day_of_month(month)
            if end_time < month_end:
                filenames.extend(gen_filename_list(start_time, end_time))
            else:
                filenames.extend(gen_filename_list(start_time, month_end))
        elif month == end_time.strftime(folder_format):
            month_start = first_day_of_month(month)
            filenames.extend(gen_filename_list(month_start, end_time))
        else:
            month_start = first_day_of_month(month)
            month_end = last_day_of_month(month)
            filenames.extend(gen_filename_list(month_start, month_end))
    # Generate folder paths

    return filenames


def find_missing_files(outer_folder_to_check, target_months, searched_files_set, inner_folder_to_check=""):
    for month in target_months:
        # TODO: Make it throw and exception for the case where location doesnt exist
        folder_path = os.path.join(
            CLAAS_FP, outer_folder_to_check, month, inner_folder_to_check)
        if os.path.exists(folder_path):
            contained_files = set([os.path.join(month, inner_folder_to_check, filename[:19]+".nc") for filename in os.listdir(
                folder_path) if filename.startswith("CPPin")])
            # print(os.listdir(folder_path))
            searched_files_set = searched_files_set - \
                contained_files
    return searched_files_set


def filenames_to_resample(start_time, end_time):
    # Generate the name of the folders of each required month
    month_folder_names = generate_month_folder_names(start_time, end_time)
    print(month_folder_names)
    # Get sets of the processed and unprocessed folders
    unpr_folders = set(os.listdir(
        os.path.join(CLAAS_FP, "Unprocessed_data/")))
    resampled_folders = set(os.listdir(
        os.path.join(CLAAS_FP, "Resampled_data/")))

    # Check if any of the months are missing entirely from the dataset
    unpr_target_months = month_folder_names-resampled_folders
    assert unpr_target_months.issubset(
        unpr_folders), f"One of the month folders doesn't exist in the downloaded dataset \nMissing months={unpr_target_months-unpr_folders}"

    # Generate a list of file names to search for in the resampled data
    resampled_target_months = month_folder_names.intersection(
        resampled_folders)
    target_resampled_filenames = generate_filenames(
        start_time, end_time, resampled_target_months)
    # Find what part of those files are missing in the resampled data
    missing_resampled_filenames = find_missing_files("Resampled_data",resampled_target_months,
        set(target_resampled_filenames))
    # Generate a list of file names to search for in the unprocessed data
    target_unpr_filenames = generate_filenames(
        start_time, end_time, unpr_target_months)
    list_missing_resampled_filenames = list(missing_resampled_filenames)
    target_unpr_filenames.extend(list_missing_resampled_filenames)
    # Check if any of the files are entirely missing from the data storage
    unpr_target_months = unpr_target_months | set([filename.split(
        os.path.sep)[-3] for filename in list_missing_resampled_filenames])
    missing_unpr_filenames = find_missing_files("Unprocessed_data", unpr_target_months, set(
        target_unpr_filenames), inner_folder_to_check="CPH")
    assert len(
        missing_unpr_filenames) == 0, f"All month folders are present but some files don't exist in the downloaded dataset \nNumber of missing files = {len(missing_unpr_filenames)}\nMissing files={missing_unpr_filenames}"
    target_unpr_filenames = [os.path.join(CLAAS_FP, "Unprocessed_data", filename.removesuffix(
        ".nc")+"405SVMSG01MD.nc") for filename in target_unpr_filenames]
    return target_unpr_filenames
