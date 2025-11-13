import numpy as np
import xarray as xr
import pyproj
import pyresample.kd_tree as kd_tree
from pyresample.geometry import SwathDefinition
from pyresample.bilinear import XArrayBilinearResampler
from pyresample.ewa import DaskEWAResampler
from pyresample import get_area_def


import os
from tempfile import gettempdir

class ProjectionTransformer():
    def __init__(self):
        self.AreaDef = None
        self.SwathDef = None
        self._neighbor_info = None
        self._neighbor_params = None  # (radius, epsilon, neighbours)
        self._bil_info = False
        self.ewa_resampler = None

    def generate_lat_lon_prj(self, aux_data):
        lon_mat = aux_data["lon"][0, :, :].values
        lat_mat = aux_data["lat"][0, :, :].values

        self.bounds = [np.nanmin(lon_mat.astype(np.float64)),
                       np.nanmax(lon_mat.astype(np.float64)),
                       np.nanmin(lat_mat.astype(np.float64)),
                       np.nanmax(lat_mat.astype(np.float64))]
        print(f"Bounds = {self.bounds}")

        Proj4Args = (
            '+proj=eqc +lat_ts=0 +lat_0=0 +lon_0=0 +x_0=0 +y_0=0 '
            '+a=6378.137 +b=6378.137 +units=km'
        )
        Prj = pyproj.Proj(Proj4Args)
        AreaID = AreaName = ProjID = 'cyl'

        self.ny, self.nx = lon_mat.shape

        SW = Prj(self.bounds[0], self.bounds[2])
        NW = Prj(self.bounds[1], self.bounds[3])
        area_extent = [SW[0], SW[1], NW[0], NW[1]]

        self.AreaDef = get_area_def(AreaID, AreaName, ProjID, Proj4Args,
                                    self.nx, self.ny, area_extent)
        self.SwathDef = SwathDefinition(lons=lon_mat, lats=lat_mat)

        # Invalidate any old neighbor cache if geometry changed
        self._neighbor_info = None
        self._neighbor_params = None

        self._generate_new_coordinates()

    def _generate_new_coordinates(self):
        self.new_cord_lon = np.linspace(self.bounds[0], self.bounds[1], self.nx)
        self.new_cord_lat = np.linspace(self.bounds[2], self.bounds[3], self.ny)

    # --- New: build, use, and persist neighbor cache -------------------------

    def build_neighbor_cache(self, radius_of_influence=60000, epsilon=5, neighbours=1):
        """Precompute and cache neighbor info for later fast resampling."""
        if self.SwathDef is None or self.AreaDef is None:
            raise RuntimeError("Call generate_lat_lon_prj(...) before caching neighbors.")
        info = kd_tree.get_neighbour_info(
            self.SwathDef, self.AreaDef,
            radius_of_influence=radius_of_influence,
            neighbours=neighbours,
            epsilon=epsilon
        )
        self._neighbor_info = info
        self._neighbor_params = (radius_of_influence, epsilon, neighbours)

    def save_neighbor_cache(self, path):
        """Persist the cached neighbor info to disk."""
        if self._neighbor_info is None:
            raise RuntimeError("No neighbor cache to save. Call build_neighbor_cache() first.")
        vi, vo, ia, da = self._neighbor_info
        roi, eps, neigh = self._neighbor_params
        np.savez_compressed(path, vi=vi, vo=vo, ia=ia, da=da,
                            roi=roi, eps=eps, neigh=neigh,
                            nx=self.nx, ny=self.ny)

    def load_neighbor_cache(self, path):
        """Load neighbor info from disk (must match current geometry)."""
        z = np.load(path, allow_pickle=False)
        # Basic sanity checks
        if (int(z["nx"]) != self.nx) or (int(z["ny"]) != self.ny):
            raise ValueError("Cached neighbor grid size does not match current geometry.")
        self._neighbor_info = (z["vi"], z["vo"], z["ia"], z["da"])
        self._neighbor_params = (int(z["roi"]), int(z["eps"]), int(z["neigh"]))

    # -------------------------------------------------------------------------

    def build_bilinear_cache(self, path, radius_of_influence=60000, epsilon=5,neighbours=1):
        if self.SwathDef is None or self.AreaDef is None:
            raise RuntimeError("Call generate_lat_lon_prj(...) before caching bilinear neibbours.")
        resampler = XArrayBilinearResampler(self.SwathDef, self.AreaDef, radius_of_influence=radius_of_influence, epsilon=epsilon, neighbours=neighbours)
        resampler.save_resampling_info(path)
        self._neighbor_params == (radius_of_influence, epsilon, neighbours)
        self._bil_info=True
       
    
    def load_bilinear_cache(self,path,radius_of_influence=60000,epsilon=5,neighbours=1):
        self.bil_resampler = XArrayBilinearResampler(self.SwathDef, self.AreaDef, radius_of_influence=radius_of_influence,epsilon=epsilon,neighbours=neighbours)
        self.bil_resampler.load_resampling_info(path)

    def bilinear_remap(self,var_tyx, n_resample_procs=8, radius_of_influence=30000, epsilon=1000, neighbours=1):
        # If we have a matching neighbor cache, use it; else fall back
        use_cache = (
            self._bil_info and
            self._neighbor_params == (radius_of_influence, epsilon, neighbours)
        )

        if use_cache:
            print("Using precomputed neighbor cache for remapping.")
            out = self.bil_resampler.resample(var_tyx, fill_value=-1, nprocs=n_resample_procs)
            
        else:
            resampler = XArrayBilinearResampler(self.SwathDef, self.AreaDef, radius_of_influence=radius_of_influence,epsilon=1000, reduce_data=True)
            out = resampler.resample(var_tyx, fill_value=-1, nprocs=n_resample_procs)
            # Compute neighbors on the fly (slower) or pre-build via build_neighbor_cache()
            

        # Back to (time, y, x) and keep your original flip on Y
        # out = out.transpose(2, 0, 1)
        # out = np.flip(out, axis=1)
        # out[np.isnan(out)] = -1
        return out
    

# cache_file = os.path.join(gettempdir(), "bilinear_resampling_luts.zarr")
    def nn_remap(self,var_tyx, n_resample_procs=8,
                 radius_of_influence=60000, epsilon=5):
        data = var_tyx.values  # numpy array now
        # data = var_field.transpose("y", "x", "time").values
        nt = data.shape[2]

        # If we have a matching neighbor cache, use it; else fall back
        use_cache = (
            self._neighbor_info is not None and
            self._neighbor_params == (radius_of_influence, epsilon, 1)
        )

        if use_cache:
            print("Using precomputed neighbor cache for remapping.")
            vi, vo, ia, da = self._neighbor_info
            out = kd_tree.get_sample_from_neighbour_info(
                    'nn',
                    (self.ny, self.nx),
                    data,
                    vi, vo, ia, da,
                    fill_value=-1
                )
        else:
            # Compute neighbors on the fly (slower) or pre-build via build_neighbor_cache()
            out = kd_tree.resample_nearest(
                self.SwathDef, data, self.AreaDef,
                radius_of_influence=radius_of_influence,
                fill_value=-1, epsilon=epsilon,
                nprocs=n_resample_procs
            )

        # Back to (time, y, x) and keep your original flip on Y
        out = out.transpose(2, 0, 1)
        out = np.flip(out, axis=1)
        out[np.isnan(out)] = -1
        return out
    
    def build_ewa_resampler(self):
        self.ewa_resampler = DaskEWAResampler(self.SwathDef, self.AreaDef)

    def ewa_remap(self,var_tyx,rows_per_scan=None):
        if self.ewa_resampler is None:
            self.build_ewa_resampler()
        out = self.ewa_resampler.resample(var_tyx.values[:,:,0],rows_per_scan=3133,fill_value=-1)
        # out = out.transpose(2, 0, 1)
        out = np.flip(out, axis=0)
        out[np.isnan(out)] = -1
        return out


    def remap_data(self, var_field, n_resample_procs=8, radius_of_influence=60000, epsilon=5, method=None):
        if self.SwathDef is None:
            raise RuntimeError(
                "No projection parameters. Run generate_lat_lon_prj(...) first."
            )

        if len(var_field.shape) != 3:
            raise NotImplementedError("2D var field remapping not yet added")

        # Data as (y, x, time)
        var_tyx = var_field.transpose("y", "x", "time").load()  # keeps files open until read completes
        if method == 'nn':
            return self.nn_remap(var_tyx, n_resample_procs,
                                radius_of_influence=radius_of_influence, epsilon=epsilon)
        elif method == 'ewa':
            return self.ewa_remap(var_tyx)
        elif method == 'bilinear':
            return self.bilinear_remap(var_tyx, n_resample_procs=n_resample_procs,radius_of_influence=radius_of_influence, epsilon=epsilon)
        else:
            raise NotImplementedError(f"Remapping method '{method}' not implemented.")
    