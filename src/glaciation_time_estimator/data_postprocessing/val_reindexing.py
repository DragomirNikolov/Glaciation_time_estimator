import numpy as np
from scipy.spatial import cKDTree
# TODO: Review file may be too much ai slop

def _wrap_lon180(lon):
    """Wrap lon to [-180, 180)."""
    lon = np.asarray(lon)
    return ((lon + 180.0) % 360.0) - 180.0

def build_val_index(val_lat, val_lon):
    """
    Build a reusable nearest-neighbor index for DARDAR lat/lon bins.

    Returns:
      index dict with:
        - 'tree' (if scipy available) OR 'points' for fallback
        - 'flat_i', 'flat_j' mapping from flat point index -> (i,j) in dd arrays
        - 'shape' original dd grid shape
    """
    val_lat = np.asarray(val_lat)
    val_lon = _wrap_lon180(np.asarray(val_lon))

    # Determine grid shape and flatten
    if val_lat.ndim == 1 and val_lon.ndim == 1:
        # meshgrid case: dd arrays likely (nlat, nlon) and coords are 1D
        # We'll build points for all (i,j).
        lat2d, lon2d = np.meshgrid(val_lat, val_lon, indexing="ij")
        val_lat2d = lat2d
        val_lon2d = lon2d
    else:
        # already 2D (or higher, but assumed 2D bins)
        val_lat2d = val_lat
        val_lon2d = val_lon

    ny, nx = val_lat2d.shape
    pts = np.column_stack([val_lat2d.ravel(), val_lon2d.ravel()]).astype(np.float64)

    flat_idx = np.arange(ny * nx, dtype=np.int64)
    flat_i = (flat_idx // nx).astype(np.int64)
    flat_j = (flat_idx %  nx).astype(np.int64)

    out = {"shape": (ny, nx), "flat_i": flat_i, "flat_j": flat_j}

    # Try KDTree (fast). Fallback to pts (still vectorized, but heavier).
    try:
        out["tree"] = cKDTree(pts)
    except Exception:
        out["points"] = pts

    return out

def match_val_to_cloud(val_index, val_cph, val_cth, val_cth_std, cloud_lat, cloud_lon,
                          max_km=None, fill_value=np.nan):
    """
    Match each (cloud_lat, cloud_lon) to nearest DARDAR bin and extract dd variables.

    Parameters
    ----------
    val_index : output of build_val_index
    val_* : 2D arrays on DARDAR bin grid (ny, nx)
    cloud_lat, cloud_lon : arrays (any shape) of cloud pixel coordinates
    max_km : optional radius gate. If provided, matches farther than max_km -> fill_value
    fill_value : value to put where no valid match / outside gate

    Returns
    -------
    cloud_val_cph, cloud_val_cth, cloud_val_cth_std : arrays same shape as cloud_lat
    """
    cloud_lat = np.asarray(cloud_lat)
    cloud_lon = _wrap_lon180(np.asarray(cloud_lon))

    orig_shape = cloud_lat.shape
    q = np.column_stack([cloud_lat.ravel(), cloud_lon.ravel()]).astype(np.float64)
    valid_q = np.isfinite(q).all(axis=1)

    out_cph = np.full(q.shape[0], fill_value, dtype=np.float64)
    out_cth = np.full(q.shape[0], fill_value, dtype=np.float64)
    out_std = np.full(q.shape[0], fill_value, dtype=np.float64)

    if not np.any(valid_q):
        return (out_cph.reshape(orig_shape),
                out_cth.reshape(orig_shape),
                out_std.reshape(orig_shape))

    flat_i = val_index["flat_i"]
    flat_j = val_index["flat_j"]
    q_valid = q[valid_q]

    # Nearest neighbor query
    if "tree" in val_index:
        dist_deg, nn = val_index["tree"].query(q_valid, k=1)
        # dist_deg is Euclidean in (lat,lon) degrees space. OK for “nearest bin”
        # If you want gating in km, approximate below.
    else:
        pts = val_index["points"]  # (npts,2)
        # vectorized (but can be heavy if DARDAR grid is big)
        # compute squared distances in degrees
        # (Nq, Npts) can be huge -> do chunking
        nn = np.empty((q_valid.shape[0],), dtype=np.int64)
        dist_deg = np.empty((q_valid.shape[0],), dtype=np.float64)
        chunk = 20000
        for s in range(0, q_valid.shape[0], chunk):
            e = min(s + chunk, q_valid.shape[0])
            dq = q_valid[s:e]  # (m,2)
            d2 = (dq[:, None, 0] - pts[None, :, 0])**2 + (dq[:, None, 1] - pts[None, :, 1])**2
            nn_chunk = np.argmin(d2, axis=1)
            nn[s:e] = nn_chunk
            dist_deg[s:e] = np.sqrt(d2[np.arange(e - s), nn_chunk])

    ii = flat_i[nn]
    jj = flat_j[nn]

    # Extract
    val_cph = np.asarray(val_cph)
    val_cth = np.asarray(val_cth)
    val_cth_std = np.asarray(val_cth_std)

    matched_cph = val_cph[ii, jj].astype(np.float64, copy=False)
    matched_cth = val_cth[ii, jj].astype(np.float64, copy=False)
    matched_std = val_cth_std[ii, jj].astype(np.float64, copy=False)

    # Optional distance gate (rough): convert deg -> km
    # 1 deg lat ~ 111 km; lon scaled by cos(lat). But our dist is Euclidean in deg-space.
    if max_km is not None:
        # conservative conversion: 1 deg ~ 111 km
        dist_km = dist_deg * 111.0
        bad = dist_km > max_km
        if np.any(bad):
            matched_cph = matched_cph.copy()
            matched_cth = matched_cth.copy()
            matched_std = matched_std.copy()
            matched_cph[bad] = fill_value
            matched_cth[bad] = fill_value
            matched_std[bad] = fill_value

    out_cph[valid_q] = matched_cph
    out_cth[valid_q] = matched_cth
    out_std[valid_q] = matched_std

    return (out_cph.reshape(orig_shape),
            out_cth.reshape(orig_shape),
            out_std.reshape(orig_shape))
