import numpy as np
import xarray as xr
import datetime as dt
import numpy as np
import xarray as xr
import datetime as dt
# I have no idea why this sqrt but will keep it to be sure
from math import sqrt as m_sqrt


class Cloud:
    """
    A class containing all the information of a given tracked feature (cloud)
    """
    # def __new__(self, *args, **kwargs):
    #     return super().__new__(self)
    def __init__(self, cloud_id, is_resampled, agg_fact):
        # Set initial parameters
        self.id = cloud_id # tracknumber
        self.is_resampled = is_resampled # whether we are analyzing output directly from CLAAS or after resampling
        self.crit_fraction = 0.1 # For simplified analysis. Critical IF below which the cloud is considered liquid. Above 1-crit_fraction the cloud is considered ice. In the medium range the cloud is considered mixed.
        # Bools inidicating if the cloud has been liquid at any point
        self.is_liq: bool = False # Has the cloud been liquid at any point?
        self.is_mix: bool = False # Has the cloud been mixed at any point?
        self.is_ice: bool = False # Has the cloud been ice at any point?
        # Max and min cloud size in pixels
        self.max_size_km: float = 0.0 # Maximum area of the cloud in km
        self.max_size_px: int = 0 # Maximum area of the cloud in num. of pixels
        self.min_size_km: float = 510.0e6 # Minimum area of the cloud in km. Start with really large value and minimize from there 
        self.min_size_px: int = 3717*3717 # Minimum area of the cloud in num. of pixels. 

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

        self.sum_cloud_ctt = 0
        self.avg_ctt = None
        self.mean_ctt_list = []
        self.std_ctt_list = []

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

        self.cloud_size_km_list_debug = []

        self.valid_cot_cloud = False
        self.cot_nan_frac_list = []

        self.valid_ctp_cloud = False
        self.ctp_nan_frac_list = []

        self.n_timesteps_no_cloud = 0
        self.terminate_cloud = False
        
        # val_* = validation variables
        
        #validation validation variables
        
        self.val_cph_list = []
        self.val_cph_deviation = []
        self.val_cph_std_list = []
        self.val_pix_claas_cph_meas = []
        self.val_pix_claas_cph_std = []

        self.val_cth_list = []
        self.val_cth_deviation = []
        self.val_cth_std_list = []
        self.val_pix_claas_cth_meas = []
        self.val_pix_claas_cth_std = []
        self.val_intersec_lon = []
        self.val_intersec_lat = []
        
        self.val_cth_std_list = []

        self.sum_cloud_cth = 0
        self.avg_cth = None
        self.cth_timestep_counter = 0
        self.mean_cth_list = []
        self.std_cth_list = []
        self.valid_cth_cloud = False
        self.cth_nan_frac_list = []

        self.deactivate_cloud = False
        self.agg_fact=agg_fact

    def __str__(self):
        return f"Cloud: {self.id}, Avg_size: {self.avg_cloud_size_km}"
    # In resampled clouds pixel area should be the area in degrees lon_resolution*lat_resolution

    def weighted_avg_and_std(self, values, weights):
        """
        Return the weighted average and standard deviation.

        They weights are in effect first normalized so that they 
        sum to 1 (and so they must not all be 0).

        values, weights -- NumPy ndarrays with the same shape.
        """
        average = np.average(values, weights=weights)
        # Fast and numerically precise:
        variance = np.average((values-average)**2, weights=weights)
        return (average, m_sqrt(variance))

    def check_status_inputs(self, cloud_values,pixel_area_non_agg, pixel_area_agg):
        """
        Do checks on the validity of some inputs.
        """
        assert (~np.isnan(pixel_area_non_agg).any()), "NaN values in pixel area array after filtering"
        assert (~np.isnan(pixel_area_agg).any()).any(), "NaN values in pixel area array after filtering"
        assert (pixel_area_agg > 0).all(), f"0 or negative values in aggregated pixel area array {pixel_area_agg}"
        assert (len(pixel_area_agg) == len(cloud_values)), f"Length of pixel area array ({len(pixel_area_non_agg)}) does not match length of cloud values array ({len(cloud_values)})"

    def validation_get_valid_values(self,val_cph,val_cth,val_cth_std):
        """
        Get valid validation values for the cloud. This is used for validation of the cloud properties.
        """
        if val_cph is not None:
            val_cph = val_cph[~np.isnan(val_cph)]
        if val_cth is not None:
            val_cth = val_cth[~np.isnan(val_cth)]
        if val_cth_std is not None:
            val_cth_std = val_cth_std[~np.isnan(val_cth_std)]
        return val_cph, val_cth, val_cth_std
    
    def check_non_agg_values(self, cot_values, ctp_values, ctt_values, cth_values, cloud_lat, cloud_lon, pixel_area_non_agg, val_cth, val_cth_std):
        """Check the validity of the cloud values and filter out invalid pixels. This is important to avoid errors in
        """
        ## There are certain locations where the aggregated pixel field has values below 30
        if ((((cloud_lat<20) & (cloud_lat>0.01)) | ((cloud_lat>-20)& (cloud_lat<-0.01)))).any():
            self.deactivate_cloud=True
            return None, None, None, None, None, None, None, None, None
        ## Aggregated pixels may cover NaN (e.g. outside the globe) in the original resolution.
        ## We filter those using ind_to_take
        ind_to_take = (~np.isnan(pixel_area_non_agg) & (pixel_area_non_agg>0)) 
        pixel_area_non_agg = pixel_area_non_agg[ind_to_take]

         
        if sum(pixel_area_non_agg) == 0 or len(pixel_area_non_agg)==0 and not self.deactivate_cloud:
            message = f"""
            Cloud_properties:\n
            ID: {self.id}\nå
            Max_size_km: {self.max_size_km}\n
            Valid_cot_cloud: {self.valid_cot_cloud}\n
            Valid_ctp_cloud: {self.valid_ctp_cloud}\n
            pixel_area_non_agg: {pixel_area_non_agg}\n
            Ind to take: {ind_to_take}\n
            Cot_values: {cot_values}\n
            Ctp_values: {ctp_values}\n
            Cloud_lat: {cloud_lat}\n
            Cloud_lon: {cloud_lon}
            """ 
            self.deactivate_cloud=True
            return None, None, None, None, None, None, None, None, None
            # raise ValueError("All pixel areas are zero or pixel area size is 0:\n"+message)
        # print(message)

        cot_values = cot_values[ind_to_take] if cot_values.size !=0 else None
        ctp_values = ctp_values[ind_to_take] if ctp_values.size !=0 else None
        ctt_values = ctt_values[ind_to_take] if ctt_values.size !=0 else None

        if cth_values is not None:
            cth_values = cth_values[ind_to_take] if cth_values.size !=0 else None
            val_cth = val_cth[ind_to_take] if val_cth is not None and val_cth.size !=0 else None
            val_cth_std = val_cth_std[ind_to_take] if val_cth_std is not None and val_cth_std.size !=0 else None
        cloud_lat = cloud_lat[ind_to_take]
        cloud_lon = cloud_lon[ind_to_take]
        return cot_values, ctp_values, ctt_values, cth_values, cloud_lat, cloud_lon, pixel_area_non_agg, val_cth, val_cth_std

    def update_status(self, time: dt.datetime, cloud_values: np.array, cot_values, ctp_values, ctt_values, cloud_lat, cloud_lon, pixel_area_non_agg, pixel_area_agg, 
                      #For validation with validation satellite
                      val_cph=None, val_cth=None, val_cth_std=None, claas_cth_values=None, is_input_agg = False):
        """
        Main function of the class. This is executed each timestep the cloud is present.
        Data about the cloud top pixels is passed and the cloud properties and time series are updated.
        It is important that this function is called sequentially

        Inputs:
        --------
        time: datetime
            The time of the current timestep
        cloud_values: np.array
            1d Array of cloud phase values for the cloud top pixels
        cot_values: np.array
            Array of cloud optical thickness values for the cloud top pixels
        ctp_values: np.array
            Array of cloud top pressure values for the cloud top pixels
        cloud_lat: np.array 
            Array of latitudes for the cloud top pixels
        cloud_lon: np.array
            Array of longitudes for the cloud top pixels
        pixel_area_non_agg: np.array
            Array of pixel areas for the cloud top pixels (non-aggregated)
        pixel_area_agg: np.array
            Array of pixel areas for the cloud top pixels (aggregated)
        
        All the arrays must be the same length with corresponding values at the same indices.
        
        Outputs:
           None
        """

        
        ## Aggregated pixels may cover NaN (e.g. outside the globe) in the original resolution.
        ## We filter those using check_non_agg_values
        cot_values, ctp_values, ctt_values, claas_cth_values, cloud_lat, cloud_lon, pixel_area_non_agg, val_cth, val_cth_std = self.check_non_agg_values(cot_values, ctp_values, ctt_values, claas_cth_values, cloud_lat, cloud_lon, pixel_area_non_agg, val_cth, val_cth_std)
        if self.deactivate_cloud:
            return
        cloud_size_px = cloud_values.shape[0]
        

        # We calculated weighted average position of the cloud in latitude and longitude
        if not self.is_resampled:
            cloud_lat_px = cloud_lat.copy()
            cloud_lon_px = cloud_lon.copy()
            cloud_lat = np.average(cloud_lat, weights=pixel_area_non_agg)
            cloud_lon = np.average(cloud_lon, weights=pixel_area_non_agg)
            # cloud_lat = 10
            # cloud_lon = 10
        else:
            cloud_lat = np.average(cloud_lat, weights=pixel_area_non_agg)
            cloud_lon = np.average(cloud_lon, weights=pixel_area_non_agg)
        # print(cloud_values)

        
        if cloud_size_px:
            self.n_timesteps_no_cloud = 0
            valid_values = cloud_values[cloud_values >= 1-1e3] - 1
            agg_area_weights = pixel_area_agg[cloud_values >= 1-1e3]
            # print(len(valid_values)/len(cloud_values))
            # print("Agg_area_weights:", agg_area_weights)
            try:
                ice_fraction = np.average(valid_values, weights=agg_area_weights)
            except Exception as e:
                message_2 = f"agg_area_weights: {agg_area_weights}\n valid_values: {valid_values}\n cloud_values: {cloud_values}\n pixel_area_non_agg: {pixel_area_non_agg}\n pixel_area_agg: {pixel_area_agg}"
                raise ValueError("Error calculating ice fraction with message:\n"  + message_2 + e)
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
            # if self.is_resampled:
            #     cloud_size_km = sum(pixel_area_non_agg*cloud_size_px * \
            #         np.cos(np.deg2rad(cloud_lat))*111.321*111.111)
            # else:
            cloud_size_km = pixel_area_non_agg.sum()
            area_threshold=66
            if is_input_agg:
                area_threshold=area_threshold*self.agg_fact**2
            large_pixel_frac = np.count_nonzero(
                pixel_area_non_agg > area_threshold)/pixel_area_non_agg.shape[0]
            if large_pixel_frac > 0.1 or pixel_area_non_agg.max() > area_threshold*2:
                self.large_pixel_cloud = True
            self.cloud_size_km_list.append(cloud_size_km)
            self.cloud_size_km_list_debug.append(pixel_area_non_agg.sum())
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
            if cot_values is not None:
                self.update_cot_variables(cot_values, pixel_area_non_agg)
            if ctp_values is not None:
                self.update_ctp_variables(ctp_values, pixel_area_non_agg)
            if ctt_values is not None:
                self.update_ctt_variables(ctt_values, pixel_area_non_agg)
            if claas_cth_values is not None:
                self.update_cth_variables(claas_cth_values, pixel_area_non_agg)
            # val_cph, val_cth, val_cth_std = self.validation_get_valid_values(val_cph, val_cth, val_cth_std)
            if val_cph is not None or val_cth is not None or val_cth_std is not None:
                self.update_validation_variables(val_cph,val_cth,val_cth_std, cloud_values,claas_cth_values, cloud_lon_px, cloud_lat_px)
            
    def update_validation_variables(self, val_cph,val_cth,val_cth_std, cloud_values, claas_cth_values, cloud_lon_px, cloud_lat_px):
        self.update_validation_cph( val_cph, cloud_values, cloud_lon_px,cloud_lat_px)
        self.update_validation_cth( val_cth, claas_cth_values)
        
    def update_validation_cph(self, val_cph, cloud_values, cloud_lon_px, cloud_lat_px ):
        if val_cph.size > 0:
            # 0.99 is 1 with accounting for floating point errors
            val_cloudy_pixels = val_cph >= 0.99
            val_valid_pixels = val_cph >= 0
            val_cph_cloudy = val_cph[val_cloudy_pixels]-1
            
            if val_cph_cloudy.size > 0:
                # print("Checking validation cloud")
                if val_valid_pixels.shape!=cloud_values.shape:
                    raise Exception(f"Mismatch between validation values size and cloud values size val_cloudy_pixels:\n {val_cloudy_pixels}\n cloud_values: {cloud_values}\n cloud lat {cloud_lat_px}")
                val_pixel_IF_claas_measurement = cloud_values[val_cloudy_pixels].mean()-1
                val_pixel_IF_claas_std = (cloud_values[val_cloudy_pixels]-1).std()
                val_cph_mean = val_cph_cloudy.mean()
                self.val_cph_list.append(val_cph_mean)
                self.val_cph_deviation.append(val_pixel_IF_claas_measurement - val_cph_mean)
                self.val_cph_std_list.append(val_cph_cloudy.std())
                self.val_pix_claas_cph_meas.append(val_pixel_IF_claas_measurement)
                self.val_pix_claas_cph_std.append(val_pixel_IF_claas_std)
                self.val_intersec_lon.append(cloud_lon_px)
                self.val_intersec_lat.append(cloud_lat_px)
            else:
                # in case there are no cloudy pixels
                self.val_cph_list.append(-1)
                self.val_cph_deviation.append(-99)
                self.val_cph_std_list.append(-1)
                self.val_pix_claas_cph_meas.append(-1)
                self.val_pix_claas_cph_std.append(-1)
        else:
            self.val_cph_list.append(np.nan)
            self.val_cph_deviation.append(np.nan)
            self.val_cph_std_list.append(np.nan)
            self.val_pix_claas_cph_meas.append(np.nan)
            self.val_pix_claas_cph_std.append(np.nan)

    def update_validation_cth(self, val_cth ,claas_cth_values):
        if val_cth.size > 0:
            # 0.99 is 1 with accounting for floating point errors
            val_cloudy_pixels = val_cth > 0
            val_cth_cloudy = val_cth[val_cloudy_pixels]
            val_cth_cloudy=val_cth_cloudy*1000 # convert to m

            if val_cth_cloudy.size > 0:
                # print("Checking validation cloud")
                # if val_valid_pixels.shape!=cloud_values.shape:
                #     raise Exception(f"Mismatch between validation values size and cloud values size val_cloudy_pixels:\n {val_cloudy_pixels}\n cloud_values: {cloud_values}\n cloud lat {cloud_lat}")
                val_pixel_cth_claas_measurement = claas_cth_values[val_cloudy_pixels].mean()
                val_pixel_cth_claas_std = (claas_cth_values[val_cloudy_pixels]).std()
                val_cth_mean = val_cth_cloudy.mean()
                self.val_cth_list.append(val_cth_mean)
                self.val_cth_deviation.append(val_pixel_cth_claas_measurement - val_cth_mean)
                self.val_cth_std_list.append(val_cth_cloudy.std())
                self.val_pix_claas_cth_meas.append(val_pixel_cth_claas_measurement)
                self.val_pix_claas_cth_std.append(val_pixel_cth_claas_std)
            else:
                # in case there are no cloudy pixels
                self.val_cth_list.append(-1)
                self.val_cth_deviation.append(-99)
                self.val_cth_std_list.append(-1)
                self.val_pix_claas_cth_meas.append(-1)
                self.val_pix_claas_cth_std.append(-1)
        else:
            self.val_cth_list.append(np.nan)
            self.val_cth_deviation.append(np.nan)
            self.val_cth_std_list.append(np.nan)
            self.val_pix_claas_cth_meas.append(np.nan)
            self.val_pix_claas_cth_std.append(np.nan)

    def update_cth_variables(self, cth_values, pixel_area_non_agg):
        cth_nan_frac = np.count_nonzero(
            np.isnan(cth_values))/cth_values.shape[0]
        if cth_nan_frac > 0.1:
            self.valid_cth_cloud = False
        self.cth_nan_frac_list.append(cth_nan_frac)
        weights = pixel_area_non_agg[~np.isnan(cth_values)]
        if len(weights) > 0:
            cth_values = cth_values[~np.isnan(cth_values)]
            mean_cth, std_cth = self.weighted_avg_and_std(cth_values, weights)
            if cth_nan_frac < 0.1:
                self.sum_cloud_cth += mean_cth
                self.cth_timestep_counter += 1
                self.avg_cth = self.sum_cloud_cth/self.cth_timestep_counter
        else:
            mean_cth = np.nan
            std_cth = np.nan
        self.mean_cth_list.append(mean_cth)
        self.std_cth_list.append(std_cth)

    def update_cot_variables(self, cot_values, pixel_area_non_agg):
        cot_nan_frac = np.count_nonzero(
            np.isnan(cot_values))/cot_values.shape[0]
        if cot_nan_frac > 0.1:
            self.valid_cot_cloud = False
        self.cot_nan_frac_list.append(cot_nan_frac)
        weights = pixel_area_non_agg[~np.isnan(cot_values)]
        if len(weights) > 0:
            cot_values = cot_values[~np.isnan(cot_values)]
            mean_cot, std_cot = self.weighted_avg_and_std(cot_values, weights)
            if cot_nan_frac < 0.1:
                self.sum_cloud_cot += mean_cot
                self.cot_timestep_counter += 1
                self.avg_cot = self.sum_cloud_cot/self.cot_timestep_counter
        else:
            mean_cot = np.nan
            std_cot = np.nan
        self.mean_cot_list.append(mean_cot)
        self.std_cot_list.append(std_cot)

    def update_ctp_variables(self, ctp_values, pixel_area_non_agg):
        ctp_nan_frac = np.count_nonzero(
            np.isnan(ctp_values))/ctp_values.shape[0]
        if ctp_nan_frac > 0.1:
            self.valid_ctp_cloud = False
        self.ctp_nan_frac_list.append(ctp_nan_frac)
        weights = pixel_area_non_agg[~np.isnan(ctp_values)]
        if len(weights) > 0:
            ctp_values = ctp_values[~np.isnan(ctp_values)]
            mean_ctp, std_ctp = self.weighted_avg_and_std(ctp_values, weights)
            if ctp_nan_frac < 0.1:
                self.sum_cloud_ctp += mean_ctp
                self.ctp_timestep_counter += 1
                self.avg_ctp = self.sum_cloud_ctp/self.ctp_timestep_counter
        else:
            mean_ctp = np.nan
            std_ctp = np.nan
        self.mean_ctp_list.append(mean_ctp)
        self.std_ctp_list.append(std_ctp)

    def update_ctt_variables(self, ctt_values, pixel_area_non_agg):
        weights = pixel_area_non_agg[~np.isnan(ctt_values)]
        if len(weights) > 0:
            ctt_values = ctt_values[~np.isnan(ctt_values)]
            mean_ctt, std_ctt = self.weighted_avg_and_std(ctt_values, weights)
            self.sum_cloud_ctt += mean_ctt
            self.avg_ctt = self.sum_cloud_ctt/self.n_timesteps
        else:
            mean_ctt = np.nan
            std_ctt = np.nan
        self.mean_ctt_list.append(mean_ctt)
        self.std_ctt_list.append(std_ctt)

    def update_missing_cloud(self):
        if self.track_end_time and (not self.terminate_cloud):
            self.n_timesteps_no_cloud += 1
            if self.n_timesteps_no_cloud > 1:
                self.terminate_cloud = True
