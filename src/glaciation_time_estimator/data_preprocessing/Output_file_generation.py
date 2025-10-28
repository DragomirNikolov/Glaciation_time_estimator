import os
import xarray as xr
import numpy as np
import dask


class OutputFile:
    def __init__(self, cph_dataset, agg_fact):
        self.cph_ds = cph_dataset
        self.agg_fact = agg_fact

    def add_coords(self, lats, lons):
        self.cph_ds = self.cph_ds.assign_coords({"lon": lons, "lat": lats})
        self.cph_ds.lat.attrs = {"standard_name": "latitude",
                                 "long_name": "latitude",
                                 "units": "degrees_north", }
        self.cph_ds.lon.attrs = {"standard_name": "longitude",
                                 "long_name": "longitude",
                                 "units": "degrees_east", }

    def set_cpp_output_variables(self, resampled_cph_data):
        self.cph_ds["cph_resampled"] = xr.DataArray(
            resampled_cph_data,
            dims=("time", "lat", "lon"),
            attrs={
                "cell_methods": "time: point",
                "flag_meanings": "clear liquid ice",
                "flag_values": "0s, 1s, 2s",
                "missing_value": np.int16(-1),
                # "grid_mapping": "projection",
                'coordinates': 'lon lat',
                "units": "1",
                "long_name": "Cloud Thermodynamic Phase",
                "standard_name": "thermodynamic_phase_of_cloud_water_particles_at_cloud_top",
                # "_FillValue": np.int16(-1),
            }
        )
    def set_ctx_output_variables(self, resampled_ctt_data, resampled_cth_data):
        self.cph_ds["ctt_resampled"] = xr.DataArray(
            resampled_ctt_data.astype(np.float32),
            dims=("time", "lat", "lon"),
            attrs={
                # "_FillValue": np.float32(-1),
                "units": "K",
                "valid_range": [np.float32(0), np.float32(4060)],
                "standard_name": "air_temperature_at_cloud_top",
                "long_name": "Cloud Top Temperature",
                # "grid_mapping": "projection",
                'coordinates': 'lon lat',
                "cell_methods": "time: point",
                "add_offset": np.float32(0.0),
                # "scale_factor": np.float32(0.1)
            }
        )
        self.cph_ds["cth_resampled"] = xr.DataArray(
            resampled_cth_data.astype(np.float32),
            dims=("time", "lat", "lon"),
            attrs={
                # "_FillValue": np.float32(-1),
                "units": "m",
                "valid_range": [np.float32(0), np.float32(30000)],
                "standard_name": "cloud_top_altitude",
                "long_name": "Cloud Top Height",
                # "grid_mapping": "projection",
                'coordinates': 'lon lat',
                "cell_methods": "time: point",
                "add_offset": np.float32(0.0),
                "scale_factor": np.float32(1.0)
            }
        )


# class OutputResampledFile(OutputFile):

#     def save_file(self, output_fps):
#         os.makedirs(os.path.dirname(output_fps[0]), exist_ok=True)
#         _, dataset_list = zip(*(self.cph_ds.groupby("time")))
#         xr.save_mfdataset(dataset_list, list(output_fps))

class OutputResampledFile(OutputFile):

    def _default_encoding(self, chunks_time_lat_lon):
        t, y, x = chunks_time_lat_lon
        enc = {}
        if "cph_resampled" in self.cph_ds:
            enc["cph_resampled"] = {
                "dtype": "int16",
                # Set exactly one time-step per file, but keep chunk metadata consistent
                "chunksizes": (1, y, x),
                # choose either of the following two lines:
                # no compression (fastest CPU):
                # "zlib": False,
                # light compression (often good tradeoff on disks):
                "zlib": True, "complevel": 9,
                "_FillValue": np.int16(-1),
            }
        for v in ("ctt_resampled", "cth_resampled"):
            if v in self.cph_ds:
                enc[v] = {
                    "dtype": "float32",
                    "chunksizes": (1, y, x),
                    "zlib": True, "complevel": 9,
                    "_FillValue": np.float32(-1),
                }
        return enc
    
    def _strip_encoding_attrs(self, ds):
        bad = {"_FillValue", "missing_value", "scale_factor", "add_offset"}
        for v in ds.variables:
            for k in list(ds[v].attrs.keys()):
                if k in bad:
                    ds[v].attrs.pop(k, None)
        return ds

    def save_file(self, output_fps, chunks_lat=512, chunks_lon=512, n_workers=8, tmpdir=None):
        
        # keep only the resampled variables we created (these are NumPy-backed already)
        keep = [v for v in ("cph_resampled", "ctt_resampled", "cth_resampled") if v in self.cph_ds]
        drop = [v for v in self.cph_ds.data_vars if v not in keep]
        if drop:
            self.cph_ds = self.cph_ds.drop_vars(drop)

        # materialize coords so no h5netcdf reads occur during writing
        self.cph_ds = self.cph_ds.assign_coords(
            time=self.cph_ds["time"].load().values,   # break backend link
            lat=np.asarray(self.cph_ds["lat"].values),
            lon=np.asarray(self.cph_ds["lon"].values),
        )

        # strip any conflicting attrs
        self.cph_ds = self._strip_encoding_attrs(self.cph_ds)

        # Ensure dims order is ('time','lat','lon')
        self.cph_ds = self.cph_ds.transpose("time", "lat", "lon", ...)
        # Clamp chunk sizes to domain and chunk for efficient 1-step writes
        ny, nx = int(self.cph_ds.sizes["lat"]), int(self.cph_ds.sizes["lon"])
        y_chunk = min(chunks_lat, ny); x_chunk = min(chunks_lon, nx)
        self.cph_ds = self.cph_ds.chunk({"time": 1, "lat": y_chunk, "lon": x_chunk})

        # build encoding (you can keep your current method; leaving here for clarity)
        encoding = self._default_encoding((1, y_chunk, x_chunk))
        engine = "h5netcdf"

        # Split dataset into one-per-time and schedule all writes together
        delayed_writes = []
        times = self.cph_ds.indexes["time"]
        if len(times) != len(output_fps):
            raise ValueError(f"Mismatch between time slices ({len(times)}) and output files ({len(output_fps)}).")
        times = self.cph_ds.indexes["time"]
        for i, (t_val, out_fp) in enumerate(zip(times, output_fps)):
            # keep time dimension!

            
            ds_t = self.cph_ds.isel(time=slice(i, i+1))
            # write to local tmp then move to final to avoid partial files and speed up on network FS
            if tmpdir is None:
                tmpdir = os.environ.get("TMPDIR", None)
            if tmpdir:
                os.makedirs(tmpdir, exist_ok=True)
                tmp_fp = os.path.join(tmpdir, f".tmp_{os.path.basename(out_fp)}")
            else:
                tmp_fp = out_fp + ".tmp"

            os.makedirs(os.path.dirname(out_fp), exist_ok=True)
            # delayed = ds_t.to_netcdf(tmp_fp, engine=engine, encoding=encoding, compute=False)
            # # add a tiny delayed task to move tmp -> final after write finishes
            # @dask.delayed
            # def _move(src, dst):
            #     os.replace(src, dst)
            #     return dst
            delayed_store = ds_t.to_netcdf(tmp_fp, engine=engine, encoding=encoding, compute=False)

            # add a dependent task that runs after the write finishes
            @dask.delayed
            def _move(_ignored, src, dst):
                os.replace(src, dst)
                return dst
            delayed_writes.append(_move(delayed_store, tmp_fp, out_fp))

        # Execute in parallel
        dask.compute(*delayed_writes, scheduler="threads", num_workers=n_workers)

class OutputNonResampledFile(OutputFile):
    def __init__(self, cph_dataset, ctx_dataset, agg_fact):
        self.agg_fact = agg_fact
        self.cph_ds= cph_dataset.copy()
        neded_vars=["cph","ctt","cth","time","x","y"]
        self.cph_ds = self.remove_unwated_var(self.cph_ds,neded_vars)
        self.ctx_ds= ctx_dataset.copy()
        self.ctx_ds = self.remove_unwated_var(self.ctx_ds,neded_vars)
    def remove_unwated_var(self, dataset,neded_vars):
        return dataset.drop_vars(list(set(dataset.data_vars.keys()) - set(neded_vars)))
    def add_coords(self, lats, lons):    
        self.cph_ds["lon"] = xr.DataArray(
                    lons,
                dims=("x"),)
        self.cph_ds["lat"] = xr.DataArray(
                np.flip(lats),
                dims=("y"),)
        self.cph_ds =  self.cph_ds.swap_dims({"x":"lon", "y":"lat"})
        self.cph_ds = self.cph_ds.drop_vars(["x","y"])
        self.ctx_ds["lon"] = xr.DataArray(
                    lons,
                dims=("x"),)
        self.ctx_ds["lat"] = xr.DataArray(
                np.flip(lats),
                dims=("y"),)
        self.ctx_ds =  self.ctx_ds.swap_dims({"x":"lon", "y":"lat"})
        self.ctx_ds = self.ctx_ds.drop_vars(["x","y"])
    def set_cpp_output_variables(self):
        self.cph_ds["cph_resampled"] = self.cph_ds["cph"].copy() 
        self.cph_ds["cph_resampled"].attrs = {
                "cell_methods": "time: point",
                "flag_meanings": "clear liquid ice",
                "flag_values": "0s, 1s, 2s",
                "missing_value": np.short(-1),
                'coordinates': 'lon lat',
                "units": "1",
                "long_name": "Cloud Thermodynamic Phase",
                "standard_name": "thermodynamic_phase_of_cloud_water_particles_at_cloud_top",
                #"_FillValue": np.int16(-1),
            }
        self.cph_ds = self.cph_ds.drop_vars("cph")
    def set_ctx_output_variables(self):
        self.cph_ds["ctt_resampled"] = self.ctx_ds["ctt"].copy() 
        self.cph_ds["ctt_resampled"].attrs = {
                #"_FillValue": np.float32(-1),
                "units": "K",
                "valid_range": [np.short(0), np.short(4060)],
                "standard_name": "air_temperature_at_cloud_top",
                "long_name": "Cloud Top Temperature",
                # "grid_mapping": "projection",
                'coordinates': 'lon lat',
                "cell_methods": "time: point"
                #"add_offset": np.float32(0.0),
                # "scale_factor": np.float32(0.1)
            }
        self.ctx_ds = self.ctx_ds.drop_vars("ctt")
        self.cph_ds["cth_resampled"] = self.ctx_ds["cth"].copy() 
        self.cph_ds["cth_resampled"].attrs = {
                #"_FillValue": np.float32(-1),
                "units": "m",
                "valid_range": [np.short(0), np.short(30000)],
                "standard_name": "cloud_top_altitude",
                "long_name": "Cloud Top Height",
                # "grid_mapping": "projection",
                'coordinates': 'lon lat',
                "cell_methods": "time: point",
                #"add_offset": np.float32(0.0),
                #"scale_factor": np.float32(1.0)
            }
        self.ctx_ds = self.ctx_ds.drop_vars("cth")
    def save_file(self, output_fps):
        self.cph_ds["lon"].attrs.update({"long_name":"longitude","standard_name":"longitude"})
        self.cph_ds["lat"].attrs.update({"long_name":"latitude","standard_name":"latitude"})
        os.makedirs(os.path.dirname(output_fps[0]), exist_ok=True)
        _, dataset_list = zip(*(self.cph_ds.groupby("time")))
        if len(dataset_list) != len(output_fps):
            raise ValueError(f"Mismatch between dimentons of dataset_list({len(dataset_list)}) and output_list({len(output_fps)}).\n Dataset list: {dataset_list} Output list:{output_fps}")
        xr.save_mfdataset(dataset_list, list(output_fps))
        self.cph_ds.close()
        self.ctx_ds.close()


