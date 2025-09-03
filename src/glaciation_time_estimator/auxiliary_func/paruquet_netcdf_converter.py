# pip install pandas pyarrow xarray netcdf4
import re
import numpy as np
import pandas as pd
import xarray as xr

def df_to_netcdf_time_from_start_time_first(
    parquet_path: str,
    out_nc_path: str,
    time_step_minutes: int = 15,
    start_time_col: str = "track_start_time",
    track_length_col: str = "track_length",
    list_col_hints=None,
    list_dtype=np.float32
):
    df = pd.read_parquet(parquet_path)
    df.columns = [str(c) for c in df.columns]

    # parse starts / (optional) durations
    if start_time_col not in df.columns:
        raise KeyError(f"Missing start time column '{start_time_col}'")
    df[start_time_col] = pd.to_datetime(df[start_time_col], errors="coerce")

    has_track_len = track_length_col in df.columns
    if has_track_len and not np.issubdtype(df[track_length_col].dtype, np.timedelta64):
        df[track_length_col] = pd.to_timedelta(df[track_length_col], errors="coerce")

    step = pd.Timedelta(minutes=time_step_minutes)

    # detect & parse list-like columns
    def looks_like_seq(s: pd.Series) -> bool:
        if list_col_hints and s.name in list_col_hints: return True
        for v in s.dropna().head(12):
            if isinstance(v, (list, tuple, np.ndarray)): return True
            if isinstance(v, str) and v.strip().startswith("["): return True
        return False

    def parse_seq(cell) -> np.ndarray:
        if cell is None or (isinstance(cell, float) and np.isnan(cell)):
            return np.array([], dtype=list_dtype)
        if isinstance(cell, (list, tuple, np.ndarray)):
            return np.asarray(cell, dtype=list_dtype).ravel()
        if isinstance(cell, (int, float, np.integer, np.floating)):
            return np.asarray([cell], dtype=list_dtype)
        if isinstance(cell, str):
            s = cell.strip()
            if not s or s.lower() in {"nan", "none"}:
                return np.array([], dtype=list_dtype)
            if (s[0] in "\"'" and s[-1] == s[0]): s = s[1:-1].strip()
            if s.startswith("[") and s.endswith("]"): s = s[1:-1]
            s = re.sub(r"\s+", " ", s)
            arr = np.fromstring(s, sep=",")
            if arr.size <= 1: arr = np.fromstring(s, sep=" ")
            if arr.size <= 1 and ";" in s: arr = np.fromstring(s.replace(";", " "), sep=" ")
            return arr.astype(list_dtype, copy=False)
        return np.array([], dtype=list_dtype)

    seq_cols = [c for c in df.columns if looks_like_seq(df[c])]
    nrow = len(df)

    parsed_per_col, len_per_col = {}, {}
    for col in seq_cols:
        parsed = [parse_seq(v) for v in df[col].tolist()]
        parsed_per_col[col] = parsed
        len_per_col[col] = np.array([len(a) for a in parsed], dtype=int)

    # row lengths: max(list lengths) vs declared track_length
    if has_track_len:
        steps = (df[track_length_col] // step).astype("Int64").fillna(0).astype(int)
        expected_len = np.maximum(0, steps + (steps > 0).astype(int))
    else:
        expected_len = np.zeros(nrow, dtype=int)

    max_list_len = np.max(np.vstack([len_per_col[c] for c in seq_cols]), axis=0) if seq_cols else np.zeros(nrow, int)
    row_len = np.maximum(expected_len, max_list_len)
    max_len = int(row_len.max()) if nrow else 0

    # --- coordinates: time-first using an integer index ---
    # time_from_start is a pure index (0..max_len-1), avoids timedelta encoding issues
    t_index = np.arange(max_len, dtype=np.int32)  # (time_from_start,)
    ds = xr.Dataset()
    ds = ds.assign_coords(time_from_start=("time_from_start", t_index))
    ds = ds.assign_coords(row=("row", np.arange(nrow, dtype=np.int64)))

    # auxiliary coordinate: elapsed minutes for readability
    if max_len > 0:
        elapsed_minutes = t_index.astype(np.int64) * time_step_minutes
        ds["elapsed_minutes"] = xr.DataArray(elapsed_minutes, dims=("time_from_start",))
        ds["elapsed_minutes"].attrs.update({
            "long_name": "elapsed minutes from track start",
            "units": "minutes"
        })

    # absolute time (time_from_start, row)
    starts = df[start_time_col].to_numpy(dtype="datetime64[ns]")
    if max_len > 0:
        offs_td = (t_index.astype("int64") * time_step_minutes).astype("timedelta64[m]").astype("timedelta64[ns]")
        abs_time = offs_td[:, None] + starts[None, :]  # (time, row)
        ds["time"] = xr.DataArray(abs_time, dims=("time_from_start", "row"))
        ds["time"].attrs.update({"long_name": "absolute time", "standard_name": "time"})

    ds.attrs.update({
        "Conventions": "CF-1.8",
        "featureType": "timeSeries",
        "title": "Tracks on a uniform time-from-start grid (time-first, integer index)",
        "history": f"time_from_start length = {max_len} at {time_step_minutes} min cadence",
    })

    # per-row scalars stay 1-D on 'row'
    for col in df.columns:
        if col in seq_cols: continue
        s = df[col]
        if np.issubdtype(s.dtype, np.datetime64):
            ds[col] = xr.DataArray(s.to_numpy(), dims=("row",))
        elif np.issubdtype(s.dtype, np.timedelta64):
            ds[col] = xr.DataArray(s.dt.total_seconds().to_numpy(), dims=("row",), attrs={"units": "seconds"})
        elif s.dtype == bool or s.dropna().map(lambda x: isinstance(x, (bool, np.bool_))).all():
            ds[col] = xr.DataArray(s.fillna(False).astype(np.int8).to_numpy(), dims=("row",),
                                   attrs={"flag_meanings": "false true"})
        else:
            co = pd.to_numeric(s, errors="coerce")
            if np.issubdtype(co.dtype, np.number):
                ds[col] = xr.DataArray(co.to_numpy(), dims=("row",))
            else:
                ds[col] = xr.DataArray(s.astype(str).replace("nan", "").to_numpy(), dims=("row",))

    # list-like variables as (time_from_start, row)
    for col in seq_cols:
        data = np.full((max_len, nrow), np.nan, dtype=list_dtype)
        Lvec = len_per_col[col]
        for i in range(nrow):
            L = Lvec[i]
            if L <= 0: continue
            data[:min(L, max_len), i] = parsed_per_col[col][i][:max_len]
        ds[col] = xr.DataArray(data, dims=("time_from_start", "row"))
        ds[f"valid_length_{col}"] = xr.DataArray(Lvec, dims=("row",),
                                                attrs={"long_name": f"valid samples in {col} per row"})

    ds = ds.transpose("time_from_start", "row", ...)
    ds.to_netcdf(out_nc_path, engine="netcdf4")
    return ds

if __name__ == "__main__":
    pd.read_parquet("")