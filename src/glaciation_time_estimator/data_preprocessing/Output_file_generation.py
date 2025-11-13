import os
import xarray as xr
import numpy as np
import dask
import os, shutil, errno, uuid

class OutputFile:
    def __init__(self, cph_dataset, agg_fact):
        self.cph_ds = cph_dataset
        self.agg_fact = agg_fact

    # def add_coords(self, lats, lons):
    #     self.cph_ds = self.cph_ds.assign_coords({"lon": lons, "lat": lats})
    #     self.cph_ds.lat.attrs = {"standard_name": "latitude",
    #                              "long_name": "latitude",
    #                              "units": "degrees_north", }
    #     self.cph_ds.lon.attrs = {"standard_name": "longitude",
    #                              "long_name": "longitude",
    #                              "units": "degrees_east", }
    # def add_coords(self, lats, lons):

        
    #     # ensure float64 and attach as coords
    #     lat = np.asarray(lats, dtype=np.float64)
    #     lon = np.asarray(lons, dtype=np.float64)
    #     self.cph_ds = self.cph_ds.assign_coords({"lat": lat, "lon": lon})

    #     # CF/ACDD-style attrs + axis
    #     self.cph_ds.lat.attrs = {
    #         "standard_name": "latitude",
    #         "long_name": "latitude",
    #         "units": "degrees_north",
    #         "axis": "Y",
    #     }
    #     self.cph_ds.lon.attrs = {
    #         "standard_name": "longitude",
    #         "long_name": "longitude",
    #         "units": "degrees_east",
    #         "axis": "X",
    #     }

    #     # ensure no fill for coords & double dtype on disk
    #     self.cph_ds["lat"].encoding.update({"_FillValue": None, "dtype": "double"})
    #     self.cph_ds["lon"].encoding.update({"_FillValue": None, "dtype": "double"})
    def add_coords(self, lats, lons):
        # ensure finite float64 arrays with no NaNs
        lat = np.asarray(lats, dtype=np.float64)
        lon = np.asarray(lons, dtype=np.float64)
        if not np.all(np.isfinite(lat)) or not np.all(np.isfinite(lon)):
            print("Input lat/lon arrays contain NaNs or inf values!", lats)
            print("lat values:", lat)
            print("lon values:", lon, flush=True)
            raise ValueError("lat/lon contain NaNs or inf; coordinates cannot be written with fill values.")

        # attach as coordinates
        self.cph_ds = self.cph_ds.assign_coords({"lat": lat, "lon": lon})

        # CF/ACDD attrs (NO _FillValue anywhere here)
        self.cph_ds["lat"].attrs = {
            "standard_name": "latitude",
            "long_name": "latitude",
            "units": "degrees_north",
            "axis": "Y",
        }
        self.cph_ds["lon"].attrs = {
            "standard_name": "longitude",
            "long_name": "longitude",
            "units": "degrees_east",
            "axis": "X",
        }

        # ensure coords have no _FillValue in encoding (remove if present)
        for c in ("lat", "lon"):
            enc = self.cph_ds[c].encoding
            enc.pop("_FillValue", None)      # be explicit
            enc.update({"dtype": "float64"}) # storage dtype


        


    # def set_cpp_output_variables(self, resampled_cph_data):
    #     self.cph_ds["cph_resampled"] = xr.DataArray(
    #         resampled_cph_data,
    #         dims=("time", "lat", "lon"),
    #         attrs={
    #             "cell_methods": "time: point",
    #             "flag_meanings": "clear liquid ice",
    #             "flag_values": "0s, 1s, 2s",
    #             "missing_value": np.int16(-1),
    #             # "grid_mapping": "projection",
    #             'coordinates': 'lon lat',
    #             "units": "1",
    #             "long_name": "Cloud Thermodynamic Phase",
    #             "standard_name": "thermodynamic_phase_of_cloud_water_particles_at_cloud_top",
    #             # "_FillValue": np.int16(-1),
    #         }
    #     )
    def set_cpp_output_variables(self, resampled_cph_data):
        self.cph_ds["cph_resampled"] = xr.DataArray(
            resampled_cph_data,
            dims=("time", "lat", "lon"),
            attrs={
                "cell_methods": "time: point",
                "flag_meanings": "clear liquid ice",
                # <<< make these numeric shorts, not strings
                "flag_values": np.array([0, 1, 2], dtype=np.int16),
                "missing_value": np.int16(-1),
                "units": "1",
                "long_name": "Cloud Thermodynamic Phase",
                "standard_name": "thermodynamic_phase_of_cloud_water_particles_at_cloud_top",
                "coordinates": "lon lat",
            },
        )

    # def set_ctx_output_variables(self, resampled_ctt_data, resampled_cth_data):
    #     self.cph_ds["ctt_resampled"] = xr.DataArray(
    #         resampled_ctt_data.astype(np.float32),
    #         dims=("time", "lat", "lon"),
    #         attrs={
    #             # "_FillValue": np.float32(-1),
    #             "units": "K",
    #             "valid_range": [np.float32(0), np.float32(4060)],
    #             "standard_name": "air_temperature_at_cloud_top",
    #             "long_name": "Cloud Top Temperature",
    #             # "grid_mapping": "projection",
    #             'coordinates': 'lon lat',
    #             "cell_methods": "time: point",
    #             "add_offset": np.float32(0.0),
    #             # "scale_factor": np.float32(0.1)
    #         }
    #     )
    #     self.cph_ds["cth_resampled"] = xr.DataArray(
    #         resampled_cth_data.astype(np.float32),
    #         dims=("time", "lat", "lon"),
    #         attrs={
    #             # "_FillValue": np.float32(-1),
    #             "units": "m",
    #             "valid_range": [np.float32(0), np.float32(30000)],
    #             "standard_name": "cloud_top_altitude",
    #             "long_name": "Cloud Top Height",
    #             # "grid_mapping": "projection",
    #             'coordinates': 'lon lat',
    #             "cell_methods": "time: point",
    #             "add_offset": np.float32(0.0),
    #             "scale_factor": np.float32(1.0)
    #         }
    #     )
    def set_ctx_output_variables(self, resampled_ctt_data, resampled_cth_data):
        data_scaled = np.round(resampled_ctt_data ).astype(np.int16)  # K -> tenths of K
        self.cph_ds["ctt_resampled"] = xr.DataArray(
            data_scaled,
            dims=("time", "lat", "lon"),
            attrs={
                "units": "K",
                "standard_name": "air_temperature_at_cloud_top",
                "long_name": "Cloud Top Temperature",
                "cell_methods": "time: point",
                "coordinates": "lon lat",
            },
        )
        # storage directives via encoding (not attrs)
        self.cph_ds["ctt_resampled"].encoding.update({
            "dtype": "int16",
            "_FillValue": np.int16(-1),
            "scale_factor": np.float32(0.1),
            "add_offset": np.float32(0.0),
            "zlib": True, "complevel": 9,
            "chunksizes": (1, self.cph_ds.sizes["lat"], self.cph_ds.sizes["lon"]),
        })

        # We still compute CTH in memory if you need it later, but we won't write it
        self.cph_ds["cth_resampled"] = xr.DataArray(
            resampled_cth_data.astype(np.float32),
            dims=("time", "lat", "lon"),
            attrs={
                "units": "m",
                "valid_range": np.array([0, 30000], dtype=np.float32),
                "standard_name": "cloud_top_altitude",
                "long_name": "Cloud Top Height",
                "cell_methods": "time: point",
                "coordinates": "lon lat",
            },
        )




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

    
    def save_file(self, output_fps):
        # Keep ONLY ctt/cph to match the CDO intermediary
        keep = [v for v in ("cph_resampled", "ctt_resampled") if v in self.cph_ds]
        drop = [v for v in self.cph_ds.data_vars if v not in keep]
        if drop:
            self.cph_ds = self.cph_ds.drop_vars(drop)

        # Drop stray grid coords so dims are exactly (time,lat,lon)
        for c in ("x", "y", "nx", "ny"):
            if c in self.cph_ds.coords or c in self.cph_ds.variables:
                self.cph_ds = self.cph_ds.drop_vars(c, errors="ignore")

        self.cph_ds = self.cph_ds.assign_coords(time=self.cph_ds["time"].load())

        
        # right before saving:
        self.cph_ds["time"].attrs.update({
            "standard_name": "time",
            "long_name": "time",
            "axis": "T",
        })
        self.cph_ds["time"].encoding.update({
            "units": "days since 1970-01-01",
            "calendar": "standard",
        })


        # strip any conflicting attrs
        self.cph_ds = self._strip_encoding_attrs(self.cph_ds)
        ny, nx = int(self.cph_ds.sizes["lat"]), int(self.cph_ds.sizes["lon"])
        enc = self._default_encoding((1, ny, nx))
        os.makedirs(os.path.dirname(output_fps[0]), exist_ok=True)
        _, dataset_list = zip(*(self.cph_ds.groupby("time")))
        xr.save_mfdataset(dataset_list, list(output_fps),compute=True, engine="h5netcdf", encoding=enc)

# class OutputResampledFile(OutputFile):

#     def _default_encoding(self, chunks_time_lat_lon):
#         t, y, x = chunks_time_lat_lon
#         enc = {}
#         if "cph_resampled" in self.cph_ds:
#             enc["cph_resampled"] = {
#                 "dtype": "int16",
#                 # Set exactly one time-step per file, but keep chunk metadata consistent
#                 "chunksizes": (1, y, x),
#                 # choose either of the following two lines:
#                 # no compression (fastest CPU):
#                 # "zlib": False,
#                 # light compression (often good tradeoff on disks):
#                 "zlib": True, "complevel": 9,
#                 "_FillValue": np.int16(-1),
#             }
#         for v in ("ctt_resampled", "cth_resampled"):
#             if v in self.cph_ds:
#                 enc[v] = {
#                     "dtype": "float32",
#                     "chunksizes": (1, y, x),
#                     "zlib": True, "complevel": 9,
#                     "_FillValue": np.float32(-1),
#                 }
#         return enc
    
#     def _strip_encoding_attrs(self, ds):
#         bad = {"_FillValue", "missing_value", "scale_factor", "add_offset"}
#         for v in ds.variables:
#             for k in list(ds[v].attrs.keys()):
#                 if k in bad:
#                     ds[v].attrs.pop(k, None)
#         return ds

#     def save_file(self, output_fps, chunks_lat=512, chunks_lon=512, n_workers=8, tmpdir=None):
        
#         # keep only the resampled variables we created (these are NumPy-backed already)
#         keep = [v for v in ("cph_resampled", "ctt_resampled", "cth_resampled") if v in self.cph_ds]
#         drop = [v for v in self.cph_ds.data_vars if v not in keep]
#         if drop:
#             self.cph_ds = self.cph_ds.drop_vars(drop)

#         # materialize coords so no h5netcdf reads occur during writing
#         self.cph_ds = self.cph_ds.assign_coords(
#             time=self.cph_ds["time"].load().values,   # break backend link
#             lat=np.asarray(self.cph_ds["lat"].values),
#             lon=np.asarray(self.cph_ds["lon"].values),
#         )

#         # strip any conflicting attrs
#         self.cph_ds = self._strip_encoding_attrs(self.cph_ds)

#         # Ensure dims order is ('time','lat','lon')
#         self.cph_ds = self.cph_ds.transpose("time", "lat", "lon", ...)
#         # Clamp chunk sizes to domain and chunk for efficient 1-step writes
#         ny, nx = int(self.cph_ds.sizes["lat"]), int(self.cph_ds.sizes["lon"])
#         y_chunk = min(chunks_lat, ny); x_chunk = min(chunks_lon, nx)
#         self.cph_ds = self.cph_ds.chunk({"time": 1, "lat": y_chunk, "lon": x_chunk})

#         # build encoding (you can keep your current method; leaving here for clarity)
#         encoding = self._default_encoding((1, y_chunk, x_chunk))
#         engine = "h5netcdf"

#         # Split dataset into one-per-time and schedule all writes together
#         delayed_writes = []
#         times = self.cph_ds.indexes["time"]
#         if len(times) != len(output_fps):
#             raise ValueError(f"Mismatch between time slices ({len(times)}) and output files ({len(output_fps)}).")
#         times = self.cph_ds.indexes["time"]
        # for i, (t_val, out_fp) in enumerate(zip(times, output_fps)):
        #     # keep time dimension!

            
        #     ds_t = self.cph_ds.isel(time=slice(i, i+1))
        #     # write to local tmp then move to final to avoid partial files and speed up on network FS
        #     if tmpdir is None:
        #         tmpdir = os.environ.get("TMPDIR", None)
        #     if tmpdir:
        #         os.makedirs(tmpdir, exist_ok=True)
        #         tmp_fp = os.path.join(tmpdir, f".tmp_{os.path.basename(out_fp)}")
        #     else:
        #         tmp_fp = out_fp + ".tmp"

        #     os.makedirs(os.path.dirname(out_fp), exist_ok=True)
        #     # delayed = ds_t.to_netcdf(tmp_fp, engine=engine, encoding=encoding, compute=False)
        #     # # add a tiny delayed task to move tmp -> final after write finishes
        #     # @dask.delayed
        #     # def _move(src, dst):
        #     #     os.replace(src, dst)
        #     #     return dst
        #     delayed_store = ds_t.to_netcdf(tmp_fp, engine=engine, encoding=encoding, compute=False)

#             # add a dependent task that runs after the write finishes
#             @dask.delayed
#             def _move(_ignored, src, dst):
#                 os.replace(src, dst)
#                 return dst
#             delayed_writes.append(_move(delayed_store, tmp_fp, out_fp))

#         # Execute in parallel
#         dask.compute(*delayed_writes, scheduler="threads", num_workers=n_workers)



# class OutputResampledFile(OutputFile):

#     def _default_encoding(self, chunks_time_lat_lon):
#         t, y, x = chunks_time_lat_lon
#         enc = {}

#         # === Variables on disk ===
#         # cph_resampled: int16 with fill
#         if "cph_resampled" in self.cph_ds:
#             enc["cph_resampled"] = {
#                 "dtype": "int16",
#                 "chunksizes": (1, y, x),
#                 "zlib": True, "complevel": 9,
#                 "_FillValue": np.int16(-1),
#             }

#         # ctt_resampled: int16 + scale to mirror CDO
#         if "ctt_resampled" in self.cph_ds:
#             enc["ctt_resampled"] = {
#                 "dtype": "int16",
#                 "chunksizes": (1, y, x),
#                 "zlib": True, "complevel": 9,
#                 "_FillValue": np.int16(-1),
#                 "scale_factor": np.float32(0.1),
#                 "add_offset": np.float32(0.0),
#             }

#         # coords/time encodings
#         enc["lat"]  = {"dtype": "double", "_FillValue": None}
#         enc["lon"]  = {"dtype": "double", "_FillValue": None}
#         enc["time"] = {"dtype": "double", "units": "days since 1970-01-01", "calendar": "standard"}

#         return enc

#     def _strip_encoding_attrs(self, ds):
#         # keep attrs simple; rely on encoding for scale/offset/fill
#         bad = {"_FillValue", "missing_value", "scale_factor", "add_offset"}
#         for v in ds.variables:
#             for k in list(ds[v].attrs.keys()):
#                 if k in bad and v not in ("cph_resampled", "ctt_resampled"):
#                     ds[v].attrs.pop(k, None)
#         return ds

#     def mimic_cdo_globals(self, source_ds=None):
#         # Optionally copy CTX global attrs (closer to your CDO path)
#         if source_ds is not None:
#             self.cph_ds.attrs = dict(source_ds.attrs)
#         # Ensure conventions are present
#         self.cph_ds.attrs.setdefault("Conventions", "CF-1.7,ACDD-1.3")

#     def save_file(self, output_fps, chunks_lat=512, chunks_lon=512, n_workers=8, tmpdir=None):
#         # Keep ONLY ctt/cph to match the CDO intermediary
#         keep = [v for v in ("cph_resampled", "ctt_resampled") if v in self.cph_ds]
#         drop = [v for v in self.cph_ds.data_vars if v not in keep]
#         if drop:
#             self.cph_ds = self.cph_ds.drop_vars(drop)

#         # Drop stray grid coords so dims are exactly (time,lat,lon)
#         for c in ("x", "y", "nx", "ny"):
#             if c in self.cph_ds.coords or c in self.cph_ds.variables:
#                 self.cph_ds = self.cph_ds.drop_vars(c, errors="ignore")

#         # materialize coords (break backend), ensure float64 coords
#         self.cph_ds = self.cph_ds.assign_coords(
#             time=self.cph_ds["time"].load().values,
#             lat=np.asarray(self.cph_ds["lat"].values, dtype=np.float64),
#             lon=np.asarray(self.cph_ds["lon"].values, dtype=np.float64),
#         )

#         # time variable CF attrs (and we'll also control units via encoding)
#         self.cph_ds["time"].attrs.update({
#             "standard_name": "time",
#             "long_name": "time",
#             "axis": "T",
#         })

#         # strip conflicting attrs
#         self.cph_ds = self._strip_encoding_attrs(self.cph_ds)

#         # order dims
#         self.cph_ds = self.cph_ds.transpose("time", "lat", "lon", ...)

#         # chunk for one-step writes
#         ny, nx = int(self.cph_ds.sizes["lat"]), int(self.cph_ds.sizes["lon"])
#         y_chunk = min(chunks_lat, ny); x_chunk = min(chunks_lon, nx)
#         self.cph_ds = self.cph_ds.chunk({"time": 1, "lat": y_chunk, "lon": x_chunk})

#         # encoding
#         encoding = self._default_encoding((1, y_chunk, x_chunk))
#         engine = "h5netcdf"

#         # check time<->files
#         times = self.cph_ds.indexes["time"]
#         if len(times) != len(output_fps):
#             raise ValueError(f"Mismatch between time slices ({len(times)}) and output files ({len(output_fps)}).")

#         # write each time step to its file, with UNLIMITED time dimension
#         delayed_writes = []
#         for i, out_fp in enumerate(output_fps):
#             ds_t = self.cph_ds.isel(time=slice(i, i+1))

#             if tmpdir is None:
#                 tmpdir = os.environ.get("TMPDIR", None)
#             if tmpdir:
#                 os.makedirs(tmpdir, exist_ok=True)
#                 tmp_fp = os.path.join(tmpdir, f".tmp_{os.path.basename(out_fp)}")
#             else:
#                 tmp_fp = out_fp + ".tmp"

#             os.makedirs(os.path.dirname(out_fp), exist_ok=True)

#             delayed_store = ds_t.to_netcdf(
#                 tmp_fp,
#                 engine=engine,
#                 encoding=encoding,
#                 compute=False,
#                 unlimited_dims={"time"},     # <-- makes time UNLIMITED (ncdump shows it)
#             )
#             # import os, shutil, errno, uuid
#             @dask.delayed
#             def _move(_ignored, src, dst):
#                 try:
#                     os.replace(src, dst)
#                     return dst
#                 except OSError as e:
#                     if getattr(e, "errno", None) != errno.EXDEV:
#                         raise
#                 dest_dir = os.path.dirname(dst)
#                 os.makedirs(dest_dir, exist_ok=True)
#                 tmp_in_dst = os.path.join(dest_dir, f".tmp.{uuid.uuid4().hex}_{os.path.basename(dst)}")
#                 shutil.copy2(src, tmp_in_dst)
#                 os.replace(tmp_in_dst, dst)
#                 os.remove(src)
#                 return dst

#             delayed_writes.append(_move(delayed_store, tmp_fp, out_fp))

#         dask.compute(*delayed_writes, scheduler="threads", num_workers=n_workers)


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


