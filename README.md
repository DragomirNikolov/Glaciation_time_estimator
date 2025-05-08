# Glaciation Time Estimator

## 1. Introduction
**Glaciation Time Estimator (GTE)** is a climate data analysis tool used to measure how long cloud tops take to freeze, otherwise known as cloud glaciation time (CGT) in stratiform clouds. It analyses cloud top data from the CLAAS-3 dataset (L2 product of the SEVIRI instrument onboard Meteosat Second Generation) to identify and track individual cloud tops in the mixed-phase temperature range, from 0 to -38°C. The software uses snapshots of the global cloud mask and cloud top temperature (CTT) to isolate stratiform clouds with nearly uniform CTT. Then, from consecutive snapshots, it tracks the movement of those cloud tops using the [PyFLEXTRK](https://github.com/FlexTRKR/PyFLEXTRKR) feature tracker. Finally, the thermodynamic phase (CPH; liquid, ice or mixed) evolution of these cloud tops is analysed to yield a dataset of the glaciation events that have occurred and the properties of the tracked cloud tops.
## 2. Processed dataset
Dataset of the properties of the ~3.5 million mixed-phase clouds and the corresponding ~100,000 detected glaciations will be made available upon request by email to dnikolo@ethz.ch.
## 3. Installing GTE
First, we advise you to create and activate a virtual environment for the project (e.g. in /venv_dir):  
```bash
python3 -m venv /venv_dir
source /venv_dir/bin/activate   # on macOS/Linux
/venv_dir\Scripts\activate      # on Windows
```
Then head over to the page of [PyFLEXTRK](https://github.com/FlexTRKR/PyFLEXTRKR) and install the package.  
Once PyFLEXTRK is installed, you can proceed to installing GTE. For this purpose you will need to first pull the package from GitHub to a local directory (/GTE_DIR). In terminal:  
```bash
git clone https://github.com/FlexTRKR/PyFLEXTRKR.git
```
With the git page cloned, simply change directory to the folder where you downloaded it and install the package:
```bash
cd /GTE_DIR
pip install -e .
```
The dependencies are listed in the pyproj.toml file and should install automatically.
## 4. Running GTE

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
