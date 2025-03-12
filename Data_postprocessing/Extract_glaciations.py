import os
from functools import partial
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
from Glaciation_time_estimator.Data_postprocessing.Job_result_fp_generator import generate_tracking_filenames
from Glaciation_time_estimator.Auxiliary_func.config_reader import read_config
from derivative import dxdt
from scipy.integrate import cumulative_trapezoid

def Extract_array_from_df(series: pd.Series):
    if series.empty:
        return None
    return np.stack(series.values)


class Peak:
    def __init__(self, startidx):
        self.born = self.left = self.right = startidx
        self.died = None

    def get_persistence(self, seq):
        return float("inf") if self.died is None else seq[self.born] - seq[self.died]


def get_persistent_homology(seq):
    peaks = []
    # Maps indices to peaks
    idxtopeak = [None for s in seq]
    # Sequence indices sorted by values
    indices = range(len(seq))
    indices = sorted(indices, key=lambda i: seq[i], reverse=True)

    # Process each sample in descending order
    for idx in indices:
        lftdone = (idx > 0 and idxtopeak[idx-1] is not None)
        rgtdone = (idx < len(seq)-1 and idxtopeak[idx+1] is not None)
        il = idxtopeak[idx-1] if lftdone else None
        ir = idxtopeak[idx+1] if rgtdone else None

        # New peak born
        if not lftdone and not rgtdone:
            peaks.append(Peak(idx))
            idxtopeak[idx] = len(peaks)-1

        # Directly merge to next peak left
        if lftdone and not rgtdone:
            peaks[il].right += 1
            idxtopeak[idx] = il

        # Directly merge to next peak right
        if not lftdone and rgtdone:
            peaks[ir].left -= 1
            idxtopeak[idx] = ir

        # Merge left and right peaks
        if lftdone and rgtdone:
            # Left was born earlier: merge right to left
            if seq[peaks[il].born] > seq[peaks[ir].born]:
                peaks[ir].died = idx
                peaks[il].right = peaks[ir].right
                idxtopeak[peaks[il].right] = idxtopeak[idx] = il
            else:
                peaks[il].died = idx
                peaks[ir].left = peaks[il].left
                idxtopeak[peaks[ir].left] = idxtopeak[idx] = ir

    # This is optional convenience
    # return sorted(peaks, key=lambda p: p.get_persistence(seq), reverse=True)
    # return idxtopeak, sorted(peaks, key=lambda p: -p.born, reverse=True)
    return peaks


class Glaciation:
    def __init__(self, min_ind, max_ind, data, timestep=15):
        self.max = data[max_ind]
        self.min = data[min_ind]
        self.min_ind = min_ind
        self.max_ind = max_ind
        self.magnitude = self.max - self.min
        self.time = (max_ind - min_ind)*timestep
        self.timestep=timestep
    def estimate_glac_time(self,data ,max_rmse_diff=2 ):
        glac_timesteps=self.max_ind- self.min_ind
        if glac_timesteps ==1:
            self.linear=True
            time=self.timestep
            self.rate_arr=np.array([(self.max-self.min)/self.timestep*60])
            self.line_rmse=0
        else:
            #Calculate mean suqared error relative to a line between the two points
            linear_growth_line = np.linspace(data[self.min_ind],data[self.max_ind], num =glac_timesteps+1 )
            rmse = np.sqrt((np.square(linear_growth_line - data[self.min_ind:self.max_ind+1])).mean())
            self.line_rmse=rmse
            if rmse>max_rmse_diff*global_rmse:
                self.linear=False
                #This divide by 3 is the magic number that makes all the noise robust derivatives work
                magical_factor=3
                t=np.arange(len(data))/magical_factor
                #TODO: Correct min and max ind to min and max in filtered data
                dIFdt = dxdt(data, t, kind="trend_filtered", order=0, alpha=1e-2)
                trend_filtered_curve = data[0] + cumulative_trapezoid(dIFdt, t, initial=0)
                # self.find_nearest_peak(trend_filtered_curve)
                #Correct so that total delta is equal to measured magnitude
                dIFdt_glac = dIFdt[self.min_ind:self.max_ind+1]
                dIFdt_glac *= self.magnitude/(cumulative_trapezoid(dIFdt_glac, t[self.min_ind:self.max_ind+1], initial=0)[-1])

                #Factor *4/3 added: 4 to convert to hours  and 3 to correct for the factor added above
                dIFdt_glac *= 60/self.timestep/magical_factor
                #Not sure about min rate to take
                self.rate_arr=dIFdt_glac[dIFdt_glac>1e-2]
                # print(f"rmse = {rmse:03f}: Non-linear")
            else:
                # print(f"rmse = {rmse:03f}: Linear")
                self.linear=True
                self.rate_arr=np.full(glac_timesteps , (self.max-self.min)/(glac_timesteps*self.timestep)*60)
        self.avg_rate = self.rate_arr.mean()


def select_peaks(data, filt, significant_peak_tresh=0.2, glac_tresh=0.4):
    if not isinstance(data, (list, np.ndarray)):
        data = data['ice_frac_hist']
    if filt is not None:
        filt_data = np.array(filt(data))
    else:
        filt_data = np.array(data)
    peaks = get_persistent_homology(filt_data)
    prev_peak = Peak(0)
    glac_list = []
    for peak in peaks:
        if peak.born > prev_peak.born+1:
            if peak.get_persistence(filt_data) >= significant_peak_tresh:
                # local_min = data[prev_peak.born:peak.born].min()
                # print(f"{prev_peak.born},{peak.born}")
                inter_peak_data = filt_data[prev_peak.born:peak.born]
                local_min_ind = np.where(
                    inter_peak_data == inter_peak_data.min())[0][-1]
                local_min = inter_peak_data[local_min_ind]
                if filt_data[peak.born] - local_min >= glac_tresh:
                    glac_list.append(Glaciation(
                        prev_peak.born + local_min_ind, peak.born, filt_data))
                    glac_list[-1].estimate_glac_time(filt_data)
                    # print("a")
                prev_peak = peak
    return glac_list


def get_combined_cloud_df(config):
    t_deltas = config['t_deltas']
    agg_fact = config['agg_fact']
    min_temp_array, max_temp_array = config['min_temp_arr'], config['max_temp_arr']
    folder_name = f"{config['start_time'].strftime(config['time_folder_format'])}_{config['end_time'].strftime(config['time_folder_format'])}"
    # Initialize an empty list to store the individual dataframes
    cloud_properties_df_list = []

    # Iterate over each temperature range
    for i in range(len(min_temp_array)):
        cloud_properties_df_list.append([])
        min_temp = min_temp_array[i]
        max_temp = max_temp_array[i]

        # Iterate over each pole
        for pole in config["pole_folders"]:
            # Construct the file path
            fp = os.path.join(
                config['postprocessing_output_dir'],
                pole,
                folder_name,
                f"Agg_{agg_fact:02}_T_{abs(round(min_temp)):02}_{abs(round(max_temp)):02}.parquet"
            )
            try:
                # Read the parquet file into a dataframe
                df = pd.read_parquet(fp)
            except:
                print(f"Couldn't load {fp}.\nSkipping ({pole}, {min_temp} to {max_temp})")
                continue

            # Add columns for min_temp, max_temp, and pole
            df['min_temp'] = min_temp
            df['max_temp'] = max_temp
            df['pole'] = pole
            df['Hemisphere'] = "South" if pole == "sp" else "North"
            df['Lifetime [h]'] = df['track_length'] / pd.Timedelta(hours=1)

            # Append the dataframe to the sublist
            cloud_properties_df_list[i].append(df)

    # Combine all dataframes into a single dataframe
    return pd.concat(
        [df for sublist in cloud_properties_df_list for df in sublist], ignore_index=True)


def extract_glaciation_events(df):
    out_df = df[df["max_ice_fraction"]-(1-df["max_water_frac"]) > 0.5].copy()
    part_select_peaks = partial(select_peaks, filt=None)
    out_df["glac_list"] = df.apply(part_select_peaks, axis=1)
    return out_df


def gen_glac_df(result_df, combined_cloud_df):
    glaciations_list = []
    for i, row in result_df.iterrows():
        for glaciation in row['glac_list']:
            # glaciation.
            glaciations_list.append([i, glaciation.time, glaciation.magnitude, glaciation.min_ind , glaciation.max_ind, glaciation.linear, glaciation.line_rmse, glaciation.rate_arr,glaciation.rate_arr.mean() ])
    glaciations_df = pd.DataFrame(glaciations_list, columns=[
        "Cloud_ID", "Time [m]", "Magnitude", "Glac_start_ind", "Glac_peak_ind", "Linear", "line_rmse", "Rate_arr", "Mean_glac_rate"])
    glaciations_df["Glaciation time [h]"] = glaciations_df["Time [m]"]/60
    return pd.merge(glaciations_df, combined_cloud_df, how="left",
                    left_on="Cloud_ID", right_index=True, validate="m:1")


def save_glac_df(glaciations_df, config):
    for pole in config["pole_folders"]:
        output_dir = os.path.join(
            config['postprocessing_output_dir'], pole,
            config['time_folder_name'],
            f"Agg_{config['agg_fact']:02}_Glaciations"
        )
        # Save DataFrame to Parquet
        output_dir_parq = output_dir + ".parquet"
        print("Writing to ", output_dir_parq)
        glaciations_df.to_parquet(output_dir_parq)

        # Optionally save as CSV
        if config['write_csv']:
            output_dir_csv = output_dir + ".csv"
            glaciations_df.to_csv(output_dir_csv)


def extract_glaciations(config):
    sqrt_mse = config["Global_sqrt_mse"]
    combined_cloud_df = get_combined_cloud_df(config)
    result_df = extract_glaciation_events(combined_cloud_df)
    glaciations_df = gen_glac_df(result_df, combined_cloud_df)
    save_glac_df(glaciations_df, config)


if __name__ == "__main__":
    config = read_config()
    global global_rmse
    global_rmse = config["Global_sqrt_mse"]
    extract_glaciations(config)
