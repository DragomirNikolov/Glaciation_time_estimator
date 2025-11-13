import numpy as np
import os
import pandas as pd
from datetime import timedelta
from glaciation_time_estimator.data_postprocessing.Job_result_fp_generator import generate_tracking_filenames
from glaciation_time_estimator.auxiliary_func.config_reader import read_config

BOOL_COLS_AND = {"is_large_pix_cloud", "is_cot_valid_cloud", "is_ctp_valid_cloud"}
BOOL_COLS_OR  = {"is_liq", "is_mix", "is_ice"}

def Extract_array_from_df(series: pd.Series):
    if series.empty:
        return None
    return np.stack(series.values)

def get_glaciations_df(config):
    agg_fact = config['agg_fact']
    folder_name = f"{config['start_time'].strftime(config['time_folder_format'])}_{config['end_time'].strftime(config['time_folder_format'])}"
    pole=config["pole_folders"][0]
    if config["Resample"]:
        fp = os.path.join(
                    config['postprocessing_output_dir'],
                    pole,
                    folder_name,
                    f"R_Agg_{agg_fact:02}_Glaciations.parquet"
                )
    else:
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
            if config["Resample"]:
                fp = os.path.join(
                    config['postprocessing_output_dir'],
                    pole,
                    folder_name,
                    f"R_Agg_{agg_fact:02}_T_{abs(round(min_temp)):02}_{abs(round(max_temp)):02}.parquet"
                )
            else:
                fp = os.path.join(
                    config['postprocessing_output_dir'],
                    pole,
                    folder_name,
                    f"Agg_{agg_fact:02}_T_{abs(round(min_temp)):02}_{abs(round(max_temp)):02}.parquet"
                )
            print(f"fp searched: {fp}")
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

# --- helpers --------------------------------------------------------------

def _to_seconds(td):
    if pd.isna(td):
        return np.nan
    return pd.to_timedelta(td).total_seconds()

def _wavg(a, b, w1, w2):
    # weighted average that skips NaNs in values or weights
    vals = np.array([a, b], dtype=float)
    wts  = np.array([w1, w2], dtype=float)
    m = ~np.isnan(vals) & ~np.isnan(wts)
    if not m.any():
        return np.nan
    w = wts[m].sum()
    return np.nan if w == 0 else np.dot(vals[m], wts[m]) / w

def _concat_hist(x, y):
    def to_array(v):
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return np.array([])
        if isinstance(v, np.ndarray):
            return v
        if isinstance(v, list):
            return np.array(v)
        return np.array(v)
    return np.concatenate([to_array(x), to_array(y)])

# --- your boundary extraction (fixed axis) --------------------------------

def extract_bound_lat_lon(df, bound_type="end"):
    df = df.copy()
    if bound_type == "end":
        df["end_lat"] = df["lat_hist"].apply(lambda x: x[-1] if x is not None and len(x) else np.nan)
        df["end_lon"] = df["lon_hist"].apply(lambda x: x[-1] if x is not None and len(x) else np.nan)
    elif bound_type == "start":
        df["start_lat"] = df["lat_hist"].apply(lambda x: x[0] if x is not None and len(x) else np.nan)
        df["start_lon"] = df["lon_hist"].apply(lambda x: x[0] if x is not None and len(x) else np.nan)
    return df

# --- main merge -----------------------------------------------------------

def merge_boundary_tracks(
    p1_bound, p2_bound, lat_tol=1e-5, lon_tol=1e-5
):
    """
    p1_bound rows must have end_lat/end_lon
    p2_bound rows must have start_lat/start_lon
    lat/lon tolerances are in degrees (~1e-5 ≈ 1.1 m).
    """

    # ensure needed columns exist
    if "end_lat" not in p1_bound or "end_lon" not in p1_bound:
        p1_bound = extract_bound_lat_lon(p1_bound, "end")
    if "start_lat" not in p2_bound or "start_lon" not in p2_bound:
        p2_bound = extract_bound_lat_lon(p2_bound, "start")

    p1b = p1_bound.reset_index(drop=True).copy()
    p2b = p2_bound.reset_index(drop=True).copy()

    # known "hist/series" columns that should be concatenated
    hist_cols = {
        "ice_frac_hist","cot_hist","cot_std_hist","cot_nan_frac_hist",
        "ctp_hist","ctp_std_hist","ctp_nan_frac_hist",
        "ctt_hist","ctt_std_hist",
        "lat_hist","lon_hist","size_hist_km"
    }

    # pattern-based groups
    def is_avg(col): return col.startswith("avg_")
    def is_max(col): return col.startswith("max_")
    def is_min(col): return col.startswith("min_")

    out_rows = []

    # pre-compute p2 end times to help with time logic if needed
    if "track_end_time" not in p2b.columns:
        if "track_length" in p2b and "track_start_time" in p2b:
            p2b["track_end_time"] = p2b["track_start_time"] + p2b["track_length"]

    for i, r1 in p1b.iterrows():
        # candidate p2 rows within tolerance
        m = (
            (p2b["start_lat"].sub(r1["end_lat"]).abs() <= lat_tol) &
            (p2b["start_lon"].sub(r1["end_lon"]).abs() <= lon_tol)
        )
        candidates = p2b[m]
        if candidates.empty:
            continue  # no match for this p1 boundary

        # choose the nearest candidate (by haversine-ish small-angle Euclid)
        deltas = (candidates["start_lat"] - r1["end_lat"])**2 + (candidates["start_lon"] - r1["end_lon"])**2
        j = deltas.idxmin()
        r2 = p2b.loc[j]

        # weights for averages
        w1 = _to_seconds(r1.get("track_length", np.nan))
        w2 = _to_seconds(r2.get("track_length", np.nan))

        merged = {}

        # tracknumber: keep p2's, add p1's as extra
        merged["tracknumber"] = r2.get("tracknumber", np.nan)
        merged["tracknumber_df1"] = r1.get("tracknumber", np.nan)

        # boundary coordinates (for reference)
        merged["boundary_lat"] = r1["end_lat"]
        merged["boundary_lon"] = r1["end_lon"]

        # time span: start is p1's start; length sums; end recomputed
        merged["track_start_time"] = r1.get("track_start_time", pd.NaT)
        merged["track_length"] = pd.to_timedelta(r1.get("track_length", pd.NaT)) + pd.to_timedelta(r2.get("track_length", pd.NaT))
        merged["track_end_time"] = merged["track_start_time"] + merged["track_length"]

        # glaciation window, if present
        # if "glaciation_start_time" in p1b.columns or "glaciation_start_time" in p2b.columns:
        #     merged["glaciation_start_time"] = min(r1.get("glaciation_start_time", pd.NaT),
        #                                           r2.get("glaciation_start_time", pd.NaT))
        # if "glaciation_end_time" in p1b.columns or "glaciation_end_time" in p2b.columns:
        #     merged["glaciation_end_time"] = max(r1.get("glaciation_end_time", pd.NaT),
        #                                         r2.get("glaciation_end_time", pd.NaT))

        # start/end fractions: take start from p1, end from p2 (natural for a joined track)
        if "start_ice_fraction" in p1b.columns or "start_ice_fraction" in p2b.columns:
            merged["start_ice_fraction"] = r1.get("start_ice_fraction", np.nan)
        if "end_ice_fraction" in p1b.columns or "end_ice_fraction" in p2b.columns:
            merged["end_ice_fraction"] = r2.get("end_ice_fraction", np.nan)

        # apply boolean rules
        for c in BOOL_COLS_AND:
            if c in p1b.columns or c in p2b.columns:
                merged[c] = bool(r1.get(c, False)) and bool(r2.get(c, False))
        for c in BOOL_COLS_OR:
            if c in p1b.columns or c in p2b.columns:
                merged[c] = bool(r1.get(c, False)) or bool(r2.get(c, False))

        # hist/list-like concatenation
        for c in hist_cols:
            if c in p1b.columns or c in p2b.columns:
                merged[c] = _concat_hist(r1.get(c, []), r2.get(c, []))

        # avg_/max_/min_ columns
        all_cols = set(p1b.columns).union(p2b.columns)
        for c in all_cols:
            if c in merged:     # already handled
                continue
            if c in {"tracknumber","tracknumber_df1","boundary_lat","boundary_lon",
                     "track_start_time","track_end_time","track_length"}:
                continue
            if c in hist_cols:
                continue
            if c in BOOL_COLS_AND or c in BOOL_COLS_OR:
                continue
            v1 = r1.get(c, np.nan)
            v2 = r2.get(c, np.nan)

            if is_avg(c):
                merged[c] = _wavg(v1, v2, w1, w2)
            elif is_max(c):
                merged[c] = np.nanmax([v1, v2])
            elif is_min(c):
                merged[c] = np.nanmin([v1, v2])
            elif c == "avg_lat" or c == "avg_lon":
                # already captured by is_avg, but just in case names differ
                merged[c] = _wavg(v1, v2, w1, w2)
            else:
                # default: prefer p2's value, else p1's
                merged[c] = v2 if (not (isinstance(v2, float) and np.isnan(v2))) else v1

        out_rows.append(merged)

    return pd.DataFrame(out_rows)

def _align_columns(to_append: pd.DataFrame, target_like: pd.DataFrame) -> pd.DataFrame:
    """
    Make sure 'to_append' has exactly the same columns (and order) as 'target_like'.
    Missing columns are added as NaN; extra columns are dropped.
    """
    out = to_append.copy()
    for col in target_like.columns:
        if col not in out.columns:
            out[col] = np.nan
    # drop extras and reorder
    out = out[target_like.columns]
    return out

def apply_merged_rows(df1: pd.DataFrame, df2: pd.DataFrame, merged_boundary: pd.DataFrame):
    """
    Remove the pre-merged entries from df1 and df2, and keep the merged entries only in df2.

    Assumptions:
      - merged_boundary['tracknumber']      -> the df2 tracknumber (kept in final df2)
      - merged_boundary['tracknumber_df1']   -> the df1 tracknumber (only used to drop from df1)
    Notes:
      - Track numbers are independent per dataset. We never compare df1 IDs to df2 IDs.
      - If, for any reason, multiple merged rows have the same df2 tracknumber,
        we keep the one with the longest merged track_length.
    """
    mb = merged_boundary.copy()

    # If duplicates by df2 track exist, keep the "best" one (longest track_length)
    if "track_length" in mb.columns:
        # ensure comparable numeric for sorting (seconds)
        tl_seconds = pd.to_timedelta(mb["track_length"]).dt.total_seconds()
        mb = mb.assign(_tl_sec=tl_seconds).sort_values("_tl_sec", ascending=False)
        mb = mb.drop_duplicates(subset=["tracknumber"], keep="first").drop(columns=["_tl_sec"])
    else:
        mb = mb.drop_duplicates(subset=["tracknumber"], keep="first")

    # Build drop sets (string-cast to avoid dtype mismatches)
    drop_ids_df1 = set(mb["tracknumber_df1"].dropna().astype(str).tolist()) if "tracknumber_df1" in mb else set()
    drop_ids_df2 = set(mb["tracknumber"].dropna().astype(str).tolist()) if "tracknumber" in mb else set()

    # 1) Prune df1 (remove pre-merged df1 rows)
    if "tracknumber" not in df1.columns:
        raise KeyError("df1 must have a 'tracknumber' column.")
    df1_kept = df1[~df1["tracknumber"].astype(str).isin(drop_ids_df1)].copy()

    # 2) Prune df2 (remove pre-merged df2 rows)
    if "tracknumber" not in df2.columns:
        raise KeyError("df2 must have a 'tracknumber' column.")
    df2_pruned = df2[~df2["tracknumber"].astype(str).isin(drop_ids_df2)].copy()

    # 3) Append merged rows into df2
    #    Align columns so concat is clean; cast tracknumber dtype to match df2's.
    mb_to_df2 = _align_columns(mb, df2_pruned)
    try:
        mb_to_df2["tracknumber"] = mb_to_df2["tracknumber"].astype(df2_pruned["tracknumber"].dtype)
    except Exception:
        # fallback: leave as-is if casting fails
        pass

    df2_final = pd.concat([df2_pruned, mb_to_df2], ignore_index=True)

    # Optional: reset indices for neatness (already done by concat on df2; do it for df1 too)
    df1_final = df1_kept.reset_index(drop=True)

    return df1_final, df2_final

# --- usage ---
# df1_new, df2_new = apply_merged_rows(df1, df2, merged_boundary)


# /\ /\ Code above written with the kind help of chatGPT but tested on a few examples
def _coerce_boolean(s: pd.Series) -> pd.Series:
    # robust mapping that tolerates 1/0, 1.0/0.0, strings, actual bools, and NaN
    mapping = {
        True: True, False: False,
        1: True, 0: False,
        1.0: True, 0.0: False,
        "1": True, "0": False,
        "True": True, "False": False,
        "true": True, "false": False,
    }
    out = s.map(mapping).astype("boolean")  # pandas nullable boolean
    return out


def finalize_for_parquet(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # 1) Booleans: normalize dtype across all known boolean columns
    for col in (BOOL_COLS_AND | BOOL_COLS_OR):
        if col in df.columns:
            df[col] = _coerce_boolean(df[col])
    return df

def extract_boundary_tracks(p1, p2):
    p1["track_end_time"] = p1["track_start_time"] + p1["track_length"]
    p2["track_end_time"] = p2["track_start_time"] + p2["track_length"]
    return p1[p1["track_end_time"] == p1["track_end_time"].max()], p2[p2["track_start_time"] == p2["track_start_time"].min()]
    


# Loads datasets sequentially
# For each part of each month combined the segments of the earth analysed
# Combines all these datasets into one big dataset for the entire year
def combine_whole_year(config):
    year=config['start_time'].year
    analysis_df_list = []
    months=[month for month in range(1,13)]
    for month in months:
        n_parts = config.get('n_month_parts',2)
        df_next = None
        config_fp_next = None

        # Specific case used due to computational constrains in paper preparation. Feel free to disregard
        for part in range(1,n_parts+1):
            print(f"Analysing {year}_tracking/{month:02}_{part:02}.yaml")
            if config.get('Analyze_year',False):
                config_fp = os.path.join(config["yearly_config_folder"],f'{year}_tracking',f'{month:02}_{part:02}.yaml')
            else:
                raise NotImplementedError("Only yearly analysis is implemented")
            temp_config = read_config(config_fp)
            df = get_combined_cloud_df(temp_config)
            if part==2 and n_parts==3:
                config_fp_3 = os.path.join(config["yearly_config_folder"],f'{year}_tracking',f'{month:02}_{3:02}.yaml')
                temp_config_3 = read_config(config_fp_3)
                df_3 = get_combined_cloud_df(temp_config_3)
                if df is not None:
                    print(f"Merging month {month} part {part} with next part {part+1}")
                    if df_3 is not None:
                        df_2_bound, df_3_bound = extract_boundary_tracks(df, df_3)
                        overlaping_clouds = merge_boundary_tracks(df_2_bound, df_3_bound, lat_tol=1e-4, lon_tol=1e-4)
                        print(overlaping_clouds)
                        df, df_3 = apply_merged_rows(df, df_3, overlaping_clouds)
                        analysis_df_list.append(finalize_for_parquet(df_3))  
                    else:
                        print(f"Skiping merge {month} parts {part} and {part+1}")
                    
                    analysis_df_list.append(finalize_for_parquet(df))  
                else:
                    print(f"Skiping month {month}") 
                    if df_3 is not None:
                        analysis_df_list.append(finalize_for_parquet(df_3))  
                    else:
                        print(f"Skiping month {month} part 3")  
                break
            else:
                if df is not None:
                    analysis_df_list.append(finalize_for_parquet(df))  
                else:
                    print(f"Skiping month {month} part {part}")
            # More general interpreatation - assumes that all parts are sequential in time
            # print(f"Analysing {year}_tracking/{month:02}_{part:02}.yaml")
            # if config.get('Analyze_year',False):
            #     config_fp = os.path.join(config["yearly_config_folder"],f'{year}_tracking',f'{month:02}_{part:02}.yaml')
            #     temp_config = read_config(config_fp)
                # if config_fp_next is not None and df_next is not None:
                #     if config_fp == config_fp_next:
                #         print(f"Loading post-merged file for part {part}")
                #         df = df_next
                #         df_next = None
                #     else:
                #         df = get_combined_cloud_df(temp_config)
                # else:
                #     df = get_combined_cloud_df(temp_config)
                # if part<n_parts:
                #     config_fp_next = os.path.join(config["yearly_config_folder"],f'{year}_tracking',f'{month:02}_{part+1:02}.yaml')
                #     temp_config_next = read_config(config_fp_next)
            # else:
            #     raise NotImplementedError("Only yearly analysis is implemented")
            # if df is not None:
            #     if temp_config_next['start_time'] == temp_config["end_time"]:
            #         print(f"Merging month {month} part {part} with next part {part+1}")
            #         df_next = get_combined_cloud_df(temp_config_next)
            #         if df_next is not None and df is not None:
            #             df_bound, df_next_bound = extract_boundary_tracks(df, df_next)
            #             overlaping_clouds = merge_boundary_tracks(df_bound, df_next_bound, lat_tol=1e-4, lon_tol=1e-4)
            #             df, df_next = apply_merged_rows(df, df_next, overlaping_clouds)
            #         else:
            #             df_next=None
            #     else:
            #         df_next=None
            #     analysis_df_list.append(finalize_for_parquet(df))  
            # else:
            #     df_next=None
            #     print(f"Skiping month {month}") 
    yearly_data = pd.concat(
            [df for df in analysis_df_list], ignore_index=True)
    clasify_clouds(yearly_data)
    yearly_data['Season'] = yearly_data['track_start_time'].dt.month.apply(month_to_season)
    os.makedirs(os.path.join(config['postprocessing_output_dir'],"Final_results"),exist_ok=True)
    yearly_data.to_parquet(os.path.join(config['postprocessing_output_dir'],"Final_results",f"{year}_all.parquet"))



if __name__=="__main__":
    print("Combining yearly files")
    combine_whole_year(read_config())
    print("Period combined")