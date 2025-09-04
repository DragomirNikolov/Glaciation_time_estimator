import numpy as np
import pandas as pd
from glaciation_time_estimator.auxiliary_func.config_reader import read_config
from glaciation_time_estimator.auxiliary_func.chunking_data import ChunkLoader

def extract_heatmap(dfs):
    cloud_df , _ , _ = dfs
    lon_bins = np.arange(-80, 82, 1)
    lat_bins = np.arange(-80, 82, 1)

    # 2. Compute the 2D histogram
    heatmap, lon_edges, lat_edges = np.histogram2d(
        cloud_df['avg_lon'],
        cloud_df['avg_lat'],
        bins=[lon_bins, lat_bins]
    )
    return heatmap

if __name__ == "__main__":
    config = read_config(
   '/cluster/work/climate/dnikolo/n2o/Glaciation_time_estimator/configs/map_generation/map_gen_config.yaml')
    analyze_year=True
    years = [year for year in range(2007, 2017)]
    glac_threshold=0.4

    # Set up analysis dataframe
    dataset = ChunkLoader(years,config=config, load_init_chunk=False)
    heatmaps = np.array(dataset.execute_analysis(extract_heatmap,load_glac=False,cloud_columns=["avg_lon","avg_lat"]))
    heatmaps.tofile("/cluster/work/climate/dnikolo/n2o/Glaciation_time_estimator/Result_analysis/heatmap_data.np")
    
