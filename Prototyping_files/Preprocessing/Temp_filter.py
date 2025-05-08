import numpy as np
import netCDF4 as nc
# from ..Helper_fun import generate_temp_range
from glaciation_time_estimator.data_preprocessing.Output_file_generation import OutputFilteredFile
# ==================================================
# Filtering and formatting data
# ==================================================
# TODO: Make non-cph specific


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

class TempFilter:
    def __init__(self, t_deltas):
        self.temp_bounds = generate_temp_range(t_deltas)

    def filter_data(self, ds,  min_temp, max_temp):
        mask = (ds['ctt_resampled'] >= 273.15+min_temp) & (ds['ctt_resampled'] <= 273.15+max_temp)
        ds['cph_filtered'] = xr.where(mask, ds['cph_resampled'], 0)

    def iterative_filter(self, res_data):
        self.ctt = res_data["ctt_resampled"].to_masked_array(copy=False)
        self.cph = res_data["cph_resampled"].to_masked_array(copy=False)
        cph_filtered_list = []
        min_temp = self.temp_bounds[0][i]
        max_temp = self.temp_bounds[1][i]
        cph_filtered_list.append(self.filter_data(min_temp, max_temp))  
        return cph_filtered_list
