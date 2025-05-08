import numpy as np
import xarray as xr
import datetime as dt


import numpy as np
import xarray as xr
import datetime as dt


class Cloud:
    # def __new__(self, *args, **kwargs):
    #     return super().__new__(self)
    def __init__(self, cloud_id, is_resampled):
        self.id = cloud_id
        self.is_resampled = is_resampled
        self.crit_fraction = 0.1
        # Bools inidicating if the cloud has been liquid at any point
        self.is_liq: bool = False
        self.is_mix: bool = False
        self.is_ice: bool = False
        # Max and min cloud size in pixels
        self.max_size_km: float = 0.0
        self.max_size_px: int = 0
        self.min_size_km: float = 510.0e6
        self.min_size_px: int = 3717*3717

        # Variables giving the first and last 4 timesteps (1 hour) of the cloud ice fraction - both arrays run in the same time direction start: [1 , 2 , 3 , 4] ... end: [1 , 2 , 3 , 4]
        self.start_ice_fraction_arr = np.empty(4)
        self.end_ice_fraction_arr = np.empty(4)
        # self.ice_fraction_arr=np.empty(max_timesteps)
        self.ice_fraction_list = []

        self.max_water_fraction: float = 0.0
        self.max_ice_fraction: float = 0.0

        self.track_start_time: dt.datetime = None
        self.track_end_time: dt.datetime = None
        self.track_length = None

        self.glaciation_start_time: dt.datetime = None
        self.glaciation_end_time: dt.datetime = None

        self.n_timesteps = None

        self.sum_cloud_cot = 0
        self.avg_cot = None
        self.cot_timestep_counter = 0
        self.mean_cot_list = []
        self.std_cot_list = []

        self.sum_cloud_ctp = 0
        self.avg_ctp = None
        self.ctp_timestep_counter = 0
        self.mean_ctp_list = []
        self.std_ctp_list = []

        self.sum_cloud_cwp = 0
        self.avg_cwp = None
        self.cwp_timestep_counter = 0
        self.mean_cwp_list = []
        self.std_cwp_list = []

        self.sum_cloud_lat = 0.0
        self.sum_cloud_lon = 0.0
        self.avg_cloud_lat = None
        self.avg_cloud_lon = None
        self.lon_list = []
        self.lat_list = []

        self.sum_cloud_size_km = 0.0
        self.avg_cloud_size_km = None
        self.cloud_size_km_list = []
        self.large_pixel_cloud = False

        self.sum_cloud_size_px = 0.0
        self.avg_cloud_size_px = None

        self.valid_cot_cloud = False
        self.cot_nan_frac_list = []

        self.valid_ctp_cloud = False
        self.ctp_nan_frac_list = []

        self.n_timesteps_no_cloud = 0
        self.terminate_cloud = False

    def __str__(self):
        return f"{self.is_liq},{self.is_mix},{self.is_ice},"
    # In resampled clouds pixel area should be the area in degrees lon_resolution*lat_resolution

    def update_status(self, time: dt.datetime, cloud_values: np.array, cot_values, ctp_values, cloud_lat, cloud_lon, pixel_area):
        ind_to_take = ~np.isnan(pixel_area)
        pixel_area = pixel_area[ind_to_take]
        if sum(pixel_area) == 0 or len(pixel_area)==0:
            error_message = f"""All pixel areas are zero or pixel area size is 0:\n
            Cloud_properties:
            ID: {self.id}\n
            Time: {time}\n
            Max_size_km: {self.max_size_km}\n
            Valid_cot_cloud: {self.valid_cot_cloud}\n
            Valid_ctp_cloud: {self.valid_ctp_cloud}\n
            Pixel_area: {pixel_area}\n
            Ind to take: {ind_to_take}\n
            Cloud_values: {cloud_values}\n
            Cot_values: {cot_values}\n
            Ctp_values: {ctp_values}\n
            Cloud_lat: {cloud_lat}\n
            Cloud_lon: {cloud_lon}
            """
            raise ValueError(error_message)
        cot_values = cot_values[ind_to_take]
        ctp_values = ctp_values[ind_to_take]
        cloud_lat = cloud_lat[ind_to_take]
        cloud_lon = cloud_lon[ind_to_take]
        cloud_size_px = cloud_values.shape[0]
        if not self.is_resampled:
            cloud_lat = np.average(cloud_lat, weights=pixel_area)
            cloud_lon = np.average(cloud_lon, weights=pixel_area)
            # cloud_lat = 10
            # cloud_lon = 10
        # print(cloud_values)
        if cloud_size_px:
            self.n_timesteps_no_cloud = 0
            valid_values = cloud_values[cloud_values >= 1]
            # print(len(valid_values)/len(cloud_values))
            ice_fraction = (valid_values.sum() -
                            float(len(valid_values)))/float(len(valid_values))
            # print(valid_values)
            # ice_fraction=float(np.count_nonzero(cloud_values==2))/float(cloud_size_px)
            water_fraction = 1-ice_fraction
            # assert math.isclose(water_fraction+ice_fraction,1)
            # print(water_fraction)
            # print(water_fraction)f cloud_arr[track_number-1] is None:

            if not (self.track_start_time):
                self.track_start_time = time
                self.n_timesteps = 1
            else:
                self.n_timesteps += 1
            if self.n_timesteps <= 4:
                self.start_ice_fraction_arr[self.n_timesteps-1] = ice_fraction
            # Check and set type of cloud
            if water_fraction > 1-self.crit_fraction:
                self.is_liq = True
            elif water_fraction > self.crit_fraction:
                self.is_mix = True
            else:
                self.is_ice = True
            if self.is_resampled:
                cloud_size_km = pixel_area*cloud_size_px * \
                    np.cos(np.deg2rad(cloud_lat))*111.321*111.111
            else:
                cloud_size_km = pixel_area.sum()
                large_pixel_frac = np.count_nonzero(
                    pixel_area > 66)/pixel_area.shape[0]
                if large_pixel_frac > 0.1 or pixel_area.max() > 110:
                    self.large_pixel_cloud = True
            self.cloud_size_km_list.append(cloud_size_km)
            self.max_size_km = max(self.max_size_km, cloud_size_km)
            self.min_size_km = min(self.min_size_km, cloud_size_km)

            self.max_size_px = max(self.max_size_px, cloud_size_px)
            self.min_size_px = min(self.min_size_px, cloud_size_px)

            self.sum_cloud_size_px += cloud_size_px
            self.avg_cloud_size_px = self.sum_cloud_size_px/self.n_timesteps

            self.sum_cloud_size_km += cloud_size_km
            self.avg_cloud_size_km = self.sum_cloud_size_km/self.n_timesteps

            # I assume that water_frac+ice_frac=1

            self.max_water_fraction = max(
                self.max_water_fraction, water_fraction)
            self.max_ice_fraction = max(
                self.max_ice_fraction, 1-water_fraction)

            self.sum_cloud_lat += cloud_lat
            self.sum_cloud_lon += cloud_lon
            self.lon_list.append(cloud_lon)
            self.lat_list.append(cloud_lat)
            self.avg_cloud_lat = self.sum_cloud_lat/self.n_timesteps
            self.avg_cloud_lon = self.sum_cloud_lon/self.n_timesteps

            self.track_end_time = time
            self.track_length = self.track_end_time-self.track_start_time

            self.end_ice_fraction_arr[0:3] = self.end_ice_fraction_arr[1:4]
            self.end_ice_fraction_arr[3] = ice_fraction

            # self.ice_fraction_arr[n_timesteps]=ice_fraction
            self.ice_fraction_list.append(ice_fraction)

            self.update_cot_variables(cot_values, pixel_area)
            self.update_ctp_variables(ctp_values, pixel_area)

    def update_cot_variables(self, cot_values, pixel_area):
        cot_nan_frac = np.count_nonzero(
            np.isnan(cot_values))/cot_values.shape[0]
        if cot_nan_frac > 0.1:
            self.valid_cot_cloud = False
        self.cot_nan_frac_list.append(cot_nan_frac)
        weights = pixel_area[~np.isnan(cot_values)]
        if len(weights) > 0:
            cot_values = cot_values[~np.isnan(cot_values)]
            mean_cot = np.average(cot_values, weights=weights)
            if cot_nan_frac < 0.1:
                self.sum_cloud_cot += mean_cot
                self.cot_timestep_counter += 1
                self.avg_cot = self.sum_cloud_cot/self.cot_timestep_counter
        else:
            mean_cot = np.nan
        self.mean_cot_list.append(mean_cot)

    def update_ctp_variables(self, ctp_values, pixel_area):
        ctp_nan_frac = np.count_nonzero(
            np.isnan(ctp_values))/ctp_values.shape[0]
        if ctp_nan_frac > 0.1:
            self.valid_ctp_cloud = False
        self.ctp_nan_frac_list.append(ctp_nan_frac)
        weights = pixel_area[~np.isnan(ctp_values)]
        if len(weights) > 0:
            ctp_values = ctp_values[~np.isnan(ctp_values)]
            mean_ctp = np.average(ctp_values, weights=weights)
            if ctp_nan_frac < 0.1:
                self.sum_cloud_ctp += mean_ctp
                self.ctp_timestep_counter += 1
                self.avg_ctp = self.sum_cloud_ctp/self.ctp_timestep_counter
        else:
            mean_ctp = np.nan
        self.mean_ctp_list.append(mean_ctp)

    def update_missing_cloud(self):
        if self.track_end_time and (not self.terminate_cloud):
            self.n_timesteps_no_cloud += 1
            if self.n_timesteps_no_cloud > 1:
                self.terminate_cloud = True
