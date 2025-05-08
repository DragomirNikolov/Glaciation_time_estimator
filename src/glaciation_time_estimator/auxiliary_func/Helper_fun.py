import numpy as np
import os
#####
# find time indexes at which there is data from both datasets
# returns (indexes of common time in time1 , ---//--- in time2)
#####


def time_intersection(time1: np.array, time2: np.array) -> tuple:
    return (np.nonzero(np.in1d(time1, time2))[0], np.nonzero(np.in1d(time2, time1))[0])

# Return a 2d array of [[min_temp][max_temp]].T.  Use with: for t_max,t_min in t_ranges:


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


def get_env_variable(name, fail=False, replace_dir="/cluster/work/climate/dnikolo/dump"):
    var = os.environ[name]
    if (var == ""):
        if fail:
            raise ValueError(f"Env variable {name} not set")
        else:
            var = replace_dir
    return var
