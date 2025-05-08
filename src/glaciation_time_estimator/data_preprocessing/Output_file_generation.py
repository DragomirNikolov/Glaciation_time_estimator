import os
import xarray as xr
import numpy as np



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
                "_FillValue": np.int16(-1),
            }
        )
    def set_ctx_output_variables(self, resampled_ctt_data, resampled_cth_data):
        self.cph_ds["ctt_resampled"] = xr.DataArray(
            resampled_ctt_data.astype(np.float32),
            dims=("time", "lat", "lon"),
            attrs={
                "_FillValue": np.float32(-1),
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
                "_FillValue": np.float32(-1),
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


class OutputResampledFile(OutputFile):

    def save_file(self, output_fps):
        os.makedirs(os.path.dirname(output_fps[0]), exist_ok=True)
        _, dataset_list = zip(*(self.cph_ds.groupby("time")))
        xr.save_mfdataset(dataset_list, list(output_fps))

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


