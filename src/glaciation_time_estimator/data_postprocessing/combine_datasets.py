import numpy as np
import os
import pandas as pd
from datetime import timedelta
from glaciation_time_estimator.data_postprocessing.Job_result_fp_generator import generate_tracking_filenames
from glaciation_time_estimator.auxiliary_func.config_reader import read_config

def Extract_array_from_df(series: pd.Series):
    if series.empty:
        return None
    return np.stack(series.values)

def get_glaciations_df(config):
    agg_fact = config['agg_fact']
    folder_name = f"{config['start_time'].strftime(config['time_folder_format'])}_{config['end_time'].strftime(config['time_folder_format'])}"
    pole=config["pole_folders"][0]
    fp = os.path.join(
                config['postprocessing_output_dir'],
                pole,
                folder_name,
                f"Agg_{agg_fact:02}_Glaciations.parquet"
            )
    try:
        return pd.read_parquet(fp)
    except FileNotFoundError:
        print(f"Skipping glaciations")
        return 

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

            # Read the parquet file into a dataframe
            try:
                df = pd.read_parquet(fp)
            except FileNotFoundError:
                print(f"Skipping all clouds file: {pole} {min_temp} to {max_temp}")
                continue

            # Add columns for min_temp, max_temp, and pole
            df['min_temp'] = min_temp
            df['max_temp'] = max_temp
            df['pole'] = pole
            df['Hemisphere'] = "South" if pole == "sp" else "North"
            df['Lifetime [h]'] = df['track_length'] / pd.Timedelta(hours=1)
            df["Radius [km]"]=np.sqrt(df["avg_size[km]"]/np.pi)
            # Append the dataframe to the sublist
            cloud_properties_df_list[i].append(df)

    # Combine all dataframes into a single dataframe
    if len(cloud_properties_df_list)==0:
        return None
    return pd.concat(
        [df for sublist in cloud_properties_df_list for df in sublist], ignore_index=True)

def month_to_season(month):
    if month in [12, 1, 2]:
        return 'DJF'
    elif month in [3, 4, 5]:
        return 'MAM'
    elif month in [6, 7, 8]:
        return 'JJA'
    else:
        return 'SON'

def clasify_clouds(yearly_data):
    yearly_data["Level"] = pd.cut(
        yearly_data.avg_ctp,
        bins=[50, 440, 680, 1000],
        labels=["Cirro","Alto","Low"]
    )
    yearly_data["Optical Thickness"] = pd.cut(
        yearly_data.avg_cot,
        bins=[0, 3.6, 23, 379],
        labels=["Thin", "Medium", "Thick"]
    )

    yearly_data["Cloud type"] = list(zip(yearly_data["Level"],yearly_data["Optical Thickness"]))
    # Define mapping dictionary
    cloud_type_mapping = {
        ("Low", "Thin"): "Cumulus",
        ("Alto", "Thin"): "Altocumulus",
        ("Cirro", "Thin"): "Cirrus",
        ("Low", "Medium"): "Stratocumulus",
        ("Alto", "Medium"): "Altostratus",
        ("Cirro", "Medium"): "Cirrostratus",
        ("Low", "Thick"): "Stratus",
        ("Alto", "Thick"): "Nimbostratus",
        ("Cirro", "Thick"): "Deep convection",
    }

    # Apply mapping
    yearly_data["Cloud type"] = yearly_data["Cloud type"].map(cloud_type_mapping)

def combine_whole_year(config):
    year=config['start_time'].year
    analysis_df_list = []
    months=[month for month in range(1,13)]
    for month in months:
        for part in [1,2]:
            print(f"Analysing {year}_tracking/{month:02}_{part:02}.yaml")
            config_fp = f'/cluster/work/climate/dnikolo/n2o/Glaciation_time_estimator/configs/{year}_tracking/{month:02}_{part:02}.yaml'
            temp_config = read_config(config_fp)
            df = get_combined_cloud_df(temp_config)
            if df is not None:
                    analysis_df_list.append(df)
            else:
                    print(f"Skiping month {month}")
    yearly_data = pd.concat(
            [df for df in analysis_df_list], ignore_index=True)
    clasify_clouds(yearly_data)
    yearly_data['Season'] = yearly_data['track_start_time'].dt.month.apply(month_to_season)
    os.makedirs(os.path.join(config['postprocessing_output_dir'],"Final_results"),exist_ok=True)
    yearly_data.to_parquet(os.path.join(config['postprocessing_output_dir'],"Final_results",f"{year}_all.parquet"))

if __name__=="__main__":
    print("Combining yearly files")
    combine_whole_year(config_reader())
    print("Period combined")