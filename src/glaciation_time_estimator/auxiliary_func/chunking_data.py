import pandas as pd
import os
import sys
GTE_DIR=os.environ["GTE_DIR"]
from glaciation_time_estimator.auxiliary_func.config_reader import read_config

class ChunkLoader:
    def __init__(self, years, config =None, config_fp=None):
        self.years = years
        if config is None:
            self.config=read_config(config_fp)
        else:
            self.config=config
        self.cloud_fps = {year: os.path.join(self.config["postprocessing_output_dir"],"Final_results",f"{year}_all.parquet") for year in years}
        self.glac_fps = {year: os.path.join(self.config["postprocessing_output_dir"],"Final_results",f"{year}_glac_04.parquet") for year in years}
        self.loaded_key=None
        self.load_single_chunk(years[0])
    def load_single_chunk(self,key):
        if self.loaded_key != key:
            self.cloud_chunk = pd.read_parquet(self.cloud_fps[key])
            self.glac_chunk = pd.read_parquet(self.glac_fps[key])
            self.glac_cloud_chunk = self.glac_chunk.drop_duplicates(subset="Cloud_ID",keep="first")
            self.cloud_chunk['is_glaciating'] = self.cloud_chunk.index.isin(self.glac_cloud_chunk['Cloud_ID'])
            self.cloud_chunk["month"]= pd.to_datetime(self.cloud_chunk['track_start_time']).dt.month
            assert self.glac_cloud_chunk["Cloud_ID"].isin(self.cloud_chunk.index).all(),"The files don't correspont to each other"
            self.loaded_key = key
    def execute_analysis(self,analysis_func, years_to_analyze = None):
        result_list = []
        if years_to_analyze is None:
            years_to_analyze=self.years
        # print(years_to_analyze)
        for year in years_to_analyze:
            self.load_single_chunk(year)
            result_list.append(analysis_func((self.cloud_chunk,self.glac_chunk, self.glac_cloud_chunk)))
        return result_list
if __name__=="__main__":
    dataset = ChunkLoader([2007,2008], config_fp=os.path.join(GTE_DIR,'configs/2007_tracking/01_01.yaml'))
