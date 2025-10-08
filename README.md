# Glaciation Time Estimator

## 1. Introduction
**Glaciation Time Estimator (GTE)** is a climate data analysis tool used to measure how long cloud tops take to freeze, otherwise known as cloud glaciation time (CGT) in stratiform clouds. It analyses cloud top data from the [CLAAS-3 dataset](https://essd.copernicus.org/articles/15/5153/2023/) (L2 product of the SEVIRI instrument onboard Meteosat Second Generation) to identify and track individual cloud tops in the mixed-phase temperature range, from 0 to -38°C. The software uses snapshots of the global cloud mask and cloud top temperature (CTT) to isolate stratiform clouds with nearly uniform CTT. Then, from consecutive snapshots, it tracks the movement of those cloud tops using the [PyFLEXTRK](https://github.com/FlexTRKR/PyFLEXTRKR) feature tracker. Finally, the thermodynamic phase (CPH; liquid, ice or mixed) evolution of these cloud tops is analysed to yield a dataset of the glaciation events that have occurred and the properties of the tracked cloud tops.
## 2. Processed dataset
Dataset with the properties of the ~3.5 million mixed-phase clouds detected annually and the corresponding ~100,000 glaciations can be found at 

## 3. Installing GTE
First, we advise you to create and activate a virtual environment for the project (e.g. in /venv_dir):  
```bash
python3 -m venv /venv_dir
source /venv_dir/bin/activate   # on macOS/Linux
/venv_dir\Scripts\activate      # on Windows
```
Then head over to the page of [PyFLEXTRK](https://github.com/FlexTRKR/PyFLEXTRKR) and install the package. Note that this step is not required if only the post-processing portion of the package is used.    
Once PyFLEXTRK is installed, you can proceed to installing GTE. For this purpose you will need to first pull the package from GitHub to a local directory (/GTE_DIR). In terminal:  
```bash
git clone https://github.com/FlexTRKR/PyFLEXTRKR.git
```
With the git page cloned, simply change directory to the folder where you downloaded it and install the package:
```bash
cd /GTE_DIR
pip install -e .
```
The dependencies are listed in the pyproject.toml file and should install automatically.
## 4. Running GTE
There are 3 prerequisites to running a GTE job:
1. **CLAAS 3 Data**  
First, you will need to download parts of the [level 2 CLAAS 3 dataset](https://navigator.eumetsat.int/product/EO:EUM:DAT:0820). The analysis requires pecifically the *Instantaneous COT, CPH and CWP (CPP)* and *Instantaneous CTT, CTP and CTH (CTX)* products. Once downloaded, you should organise them in the following structure, keeping their original names:  
CLAAS_fp/section/YYYY/MM/DD/CPP*.nc  
CLAAS_fp/section/YYYY/MM/DD/CTX*.nc  
The sections are different regions of the earth analysed, originally "np" and "sp", representing the northern and southern hemispheres. You can have as many sections as you like. In total, there should be 96 files per day per section. 
2. **Configuration file**  
To run GTE you first need to have an appropriate config .yaml file. An example is given in "config.yaml". It is important to note that this configuration file is separate from the PyFLEXTRKR configuration file used for the tracking algorithm. If you want to simultaneously analyse a whole year of data, we recommend creating an reference configuration file and then using "/configs/config_generator.py" to create a folder with 24 setup files spaning a year. 
3. **TMP_DIR environmental variable**  
If you intend to use the tracking portion of the library, you will also need to set a TMP_DIR environmental variable. The files for every filtered frame will be temporarily copied to this directory during anlysis. On distributed this allows the algorithm to access files from local temporary memory on distributed systems, which is significantly faster than acccess from long-term storage. :
```bash
export TMP_DIR=/**YOUR TEMPORARY DIRECTORY**
```

Currently, GTE is being run as a set of chained Slurm jobs (bash scripts). The job .bsub files and other bash scripts, which can submit multiple of these jobs at once, can be found in the "Slurm_jobs" folder. The bash scripts in "Slurm_jobs/0_combined" use a dependency tree to submit a series of chaned preprocessing, tracking and postprocessing jobs which will output .parquet binaries (loaded as through pandas.read_parquet()) in a directory specified from the configuration file. The 

## 5. Code structure
The processing is divided into the following steps:

1. **Preprocessing**  
   First, the data is *preprocessed* in two steps:
   1. *Aggregation:*  
      Due to computational resource limitations, we aggregate the original data into a coarser resolution. Several sensitivity tests were done, and a special aggregation technique was implemented to ensure that this aggregation has minimal impact on the overall result.
   2. *Filtering:*  
      Each aggregated “frame” is divided into several separate images. Each image contains the CPH information from pixels with cloud top temperatures within a predefined maximum and minimum range. When combined, these images should contain all cloudy pixels in the mixed-phase temperature range, between −38 °C and 0 °C.
2. **Tracking**  
    The preprocessed data is then used as input for a feature tracker, which connects features across multiple timesteps. This task can be divided into two sub-processes:
   1. *Feature identification:*  
      Within each filtered “frame,” pixels forming continuous objects larger than a predefined threshold are assigned unique feature numbers.
   2. *Feature tracking:*  
      By analyzing consecutive frames, the algorithm determines which identified features persist over multiple timesteps. Pixels within features that remain for a predefined duration are marked, forming *cloud fragment tracks*.
3. **Postprocessing**  
   A postprocessing algorithm then analyses the individual cloud fragment tracks to extract the time evolution of all properties of interest, such as cloud top phase, cloud fragment size, mean cloud optical thickness, etc.

The processing pipeline is visualised in the figure below:  
![preprocessing_pipeline_2](https://github.com/user-attachments/assets/ed675179-9c12-4b47-9825-d2b913d64633)

## 6. Manuscript figures
The code in this repository was used to generate the figures in the manuscript "How complete is cloud glaciation?". The following jupyter notebooks contain all the necessary code to reproduce them:
```bash
# ------------------------------------------
# Methods figure
# Figure Code
/Result_analysis/Publication_figures/Methods/Preproc_row.ipynb
/Result_analysis/Publication_figures/Methods/Postprocessing_row.ipynb
# Figure Data
/Publication_figures/Methods/Tracking_data/*
# The data for this figure was generated by tracking mixed-phased clouds in CLAAS-3 
# using the configuration at 
/configs/2008_tracking/01_02.yaml
# ------------------------------------------
# Dataset map and bar chart
# Figure Code
/Result_analysis/Publication_figures/Multiyear_analysis/plot_map.ipynb
# Figure Data
/Result_analysis/Publication_figures/Multiyear_analysis/heatmap_data.npy
/Result_analysis/Publication_figures/Claas_processing_data/*
# Figure Data Generation Code
/Result_analysis/Publication_figures/Multiyear_analysis/Multiyear_map_data.ipynb
/Result_analysis/Publication_figures/Multiyear_analysis/Cover_calculation_jobs/*
# ------------------------------------------
# Occurance rate and peak ice fraction figure
# Figure Code
/Publication_figures/Multiyear_analysis/Plot_occurance_rates.ipynb
# Figure Data
/Result_analysis/Publication_figures/Multiyear_analysis/Occcurance_rate_data/
# Figure Data Generation Code
/Result_analysis/Publication_figures/Multiyear_analysis/Multiyear_occurance_rates.ipynb
/Result_analysis/Publication_figures/Multiyear_analysis/Multiyear_glaciations.ipynb
```
The dataset post-processing used to generate the presented data can be found in
```bash
/Result_analysis/Publication_figures/Claas_processing_data
```
The dataset post-processing used to generate the presented data can be found in
```bash
/Result_analysis/Publication_figures/Multiyear_analysis
```

## 7. Contact 
For additional information you can contact me at the following emails [dnikolo@ethz.ch](dnikolo@ethz.ch) or [dragomird.nikolov@gmail.com](dragomird.nikolov@gmail.com)

## 8. Acknowledgements
I would like to thank Prof. Ulrike Lohmann and Dr. Diego Villanueva for their supervision of this project. I am also grateful to the members of CM-SAF for their rapid and flexible response to our CLAAS-3 data requests. Finally, I wish to express my gratitude to Sylvaine Ferrachat and the other members of the ETH Group of Atmospheric Physics for their assistance in setting up the computational and storage resources needed for this project.

## 9. Future updates
Major updates to the code will be pblished to zenodo in the future. Smaller bugfixes and updates can be found on the [github repository](https://github.com/DragomirNikolov/Glaciation_time_estimator)

<!--  1. **Preprocessing**  
   - Resampling is performed to convert geostationary data to a regular latitude/longitude reference frame.  
//   - Cloud top temperature filtering is applied to split larger clouds into individual temperature homogenious cloud segments
//   - The data is aggregated in n x n bins (usually n=3) for reduced processing time and data storage

//2. **Tracking**  
//   - The PyFLEXTRKR library is utilized to track the resulting cloud segments. The library tracks segments with area larger than 1000 [km^2] surviving more than 45 min 
//
//3. **Postprocessing**  
//   - The tracked fragments are analyzed, and data for each cloud is stored in a Parquet binary file format. 

//4. **Result Analysis**  
   - Cloud glaciation is identified, and the CGT is measured.Text-->
