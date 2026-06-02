from glaciation_time_estimator.auxiliary_func.config_reader import read_config
import pandas as pd
from tqdm import tqdm
import os
from pathlib import Path


class ChunkLoader:
    def __init__(self, years, config=None, config_fp=None ,load_init_chunk=True, filter=True):
        self.years = years
        if config is None:
            self.config = read_config(config_fp)
            print(f"Loaded config from {config_fp}")
        else:
            self.config = config
        self.glac_thresh=self.config["glac_threshold"]
        base = self.config["postprocessing_output_dir"]
        self.cloud_fps = {
            year: os.path.join(base, "Final_results", f"{year}_all.parquet")
            for year in years
        }
        print(f"Cloud_fps: {self.cloud_fps}")
        self.glac_fps = {
            year: os.path.join(base, "Final_results", f"{year}_glac_{int(self.glac_thresh*10):02}.parquet")
            for year in years
        }
        self.loaded_key = None
        self.filter=filter
        # initial load using full columns
        if load_init_chunk==True:
            self.load_single_chunk(years[0])

    def __str__(self):
        return f"Dataset chunk loader\n \
                Analyzing files: {self.cloud_fps}\n\
                Currently loaded: {self.loaded_key}"
     
    def _check_cloud_coverage(self, key):
        """
        Check if every half-month has at least one cloud
        in every min_temp range.
        """
        required_cols = {"track_start_time", "min_temp"}
        missing_cols = required_cols - set(self.cloud_chunk.columns)
        if missing_cols:
            raise KeyError(f"Missing required columns for coverage check: {missing_cols}")

        min_temps = [-36, -30, -24, -18, -12, -6]

        df = self.cloud_chunk[["track_start_time", "min_temp"]].copy()

        time = pd.to_datetime(df["track_start_time"])
        df["month"] = time.dt.month
        df["day"] = time.dt.day

        df["half_month"] = df["day"].where(df["day"] <= 15, 16)
        df["half_month"] = df["half_month"].map(
            lambda x: "01-15" if x <= 15 else "16-end"
        )

        existing = set(
            df.dropna(subset=["min_temp"])
            .groupby(["month", "half_month", "min_temp"], observed=True)
            .size()
            .index
        )

        missing = []

        for month in range(1, 13):
            for half_month in ["01-15", "16-end"]:
                for temp_range in min_temps:
                    if (month, half_month, temp_range) not in existing:
                        missing.append((month, half_month, temp_range))

        if missing:
            print(f"\nMissing cloud coverage for year {key}:")
            for month, half_month, min_temps in missing:
                print(f"  month={month:02d}, half={half_month}, temp={min_temps}")
        else:
            print(f"All temp ranges covered for year {key}.")
    
    def load_single_chunk(
        self,
        key,
        load_clouds=True,
        load_glac=True,
        cloud_columns=None,
        glac_columns=None,
        force_reload=False
    ):
        """
        Load data for a single year key. Optionally select subsets of columns.
        """
        if self.loaded_key == key and not force_reload:
            return
        # Load cloud data
        if load_clouds:
            if cloud_columns is None:
                self.cloud_chunk = pd.read_parquet(
                self.cloud_fps[key])
                self.cloud_chunk["month"] = pd.to_datetime(
                        self.cloud_chunk['track_start_time']
                    ).dt.month
            else:
                columns_to_load = set(cloud_columns)
                columns_to_load -= columns_to_load.intersection({'Cloud_ID', 'month', 'is_large_pix_cloud','avg_lat','avg_lon', 'track_start_time'})
                comumns_to_load_list = list(columns_to_load)
                comumns_to_load_list.extend(['Cloud_ID', 'is_large_pix_cloud','avg_lat','avg_lon', 'track_start_time'])
                self.cloud_chunk = pd.read_parquet(
                    self.cloud_fps[key], columns=comumns_to_load_list)
                if 'month' in cloud_columns:
                    self.cloud_chunk["month"] = pd.to_datetime(
                        self.cloud_chunk['track_start_time']
                    ).dt.month
            if self.filter:
                self.cloud_chunk=self.cloud_chunk[~self.cloud_chunk.is_large_pix_cloud]
                self.cloud_chunk = self.cloud_chunk[(self.cloud_chunk.avg_lat >30) | (self.cloud_chunk.avg_lat<-30)]

            self._check_cloud_coverage(key)
        else:
            self.cloud_chunk = pd.DataFrame()

        # Load glaciating data
        if load_glac:
            if glac_columns is None:
                self.glac_chunk = pd.read_parquet(
                    self.glac_fps[key]
                )
            else:
                columns_to_load = set(glac_columns)
                columns_to_load -= columns_to_load.intersection({'Cloud_ID', 'is_large_pix_cloud','avg_lat','avg_lon', 'track_start_time'})
                comumns_to_load_list = list(columns_to_load)
                comumns_to_load_list.extend(['Cloud_ID', 'is_large_pix_cloud','avg_lat','avg_lon', 'track_start_time'])
                self.glac_chunk = pd.read_parquet(
                    self.glac_fps[key], columns=comumns_to_load_list
                )
            if self.filter:
                self.glac_chunk=self.glac_chunk[~self.glac_chunk.is_large_pix_cloud]
                self.glac_chunk = self.glac_chunk[(self.glac_chunk.avg_lat >30) | (self.glac_chunk.avg_lat<-30)]
            

            # Drop duplicate Cloud_IDs and mark glaciating
            self.glac_cloud_chunk = self.glac_chunk.drop_duplicates(
                subset="Cloud_ID", keep="first"
            )


            if load_clouds:
                # mark clouds as glaciating
                self.cloud_chunk['is_glaciating'] = (
                    self.cloud_chunk.index.isin(
                        self.glac_cloud_chunk['Cloud_ID']
                    )
                    # self.cloud_chunk['Cloud_ID'].isin(
                    #     self.glac_cloud_chunk['Cloud_ID']
                    # )
                )
                
                # ensure correspondence
                assert self.glac_cloud_chunk["Cloud_ID"].isin(
                    self.cloud_chunk.index
                ).all(), "The files don't correspond to each other"
                # assert self.glac_cloud_chunk["Cloud_ID"].isin(
                #     self.cloud_chunk['Cloud_ID']
                # ).all(), "The files don't correspond to each other"
        else:
            self.glac_chunk = pd.DataFrame()
            self.glac_cloud_chunk = pd.DataFrame()

        self.loaded_key = key

    def load_next_chunk(self,load_clouds=True,
        load_glac=True,
        cloud_columns=None,
        glac_columns=None,
        force_reload=False
    ):
        """Load the next year from the years list"""
        idx = self.years.index(self.loaded_key)
        if idx+1<len(self.years):
            next_year = self.years[idx + 1]
            self.load_single_chunk(next_year,load_clouds,load_glac,cloud_columns,glac_columns,force_reload)
        elif idx+1==len(self.years):
            print("Final chunk already loaded. No new chunk loaded")
        else:
            raise ValueError("Index error when loading years")
                
    def execute_analysis(
        self,
        analysis_func,
        years_to_analyze=None,
        load_clouds=True,
        load_glac=True,
        cloud_columns=None,
        glac_columns=None,
        force_reload=False
    ):
        """
        Run analysis_func on each year's loaded data, optionally selecting columns.

        Returns a list of results, one per year.
        """
        results = []
        if years_to_analyze is None:
            years_to_analyze = self.years

        for year in tqdm(years_to_analyze, desc="Loading years", unit="year"):
            self.load_single_chunk(
                year,
                load_clouds=load_clouds,
                load_glac=load_glac,
                cloud_columns=cloud_columns,
                glac_columns=glac_columns,
                force_reload=force_reload,
            )
            results.append(
                analysis_func(
                    (self.cloud_chunk,
                    self.glac_chunk,
                    self.glac_cloud_chunk)                )
            )
        return results



if __name__ == "__main__":
    dataset = ChunkLoader([2007, 2008], config_fp=os.path.join(
        "/wolke_scratch/dnikolo/Glaciation_time_estimator/configs/config_n2o.yaml"))
    def test_func(cloud_chunk, glac_chunk, glac_cloud_chunk):
        return cloud_chunk.shape, glac_chunk.shape, glac_cloud_chunk.shape
    print(dataset.execute_analysis(
        test_func,
        load_clouds=True,
        load_glac=False,
        cloud_columns=['min_temp', 'Hemisphere',],
        glac_columns=None
    ))
