# Glaciation Time Estimator

## 1. Introduction
**Glaciation Time Estimator (GTE)** is a climate data analysis tool used to measure cloud glaciation time (CGT) in stratiform clouds. It analyses cloud top data from the CLAAS-3 dataset (L2 product of the SEVIRI instrument onboard Meteosat Second Generation) to identify and track individual cloud tops in the mixed-phase temperature range, from 0 to -38°C. The software uses snapshots of the global cloud mask and cloud top temperature (CTT) to isolate stratiform clouds with nearly uniform CTT. Then, from consecutive snapshots, it tracks the movement of those cloud tops using the [PyFLEXTRK](https://github.com/FlexTRKR/PyFLEXTRKR) feature tracker. Finally, the evolution of the thermodynamic phase (liquid, ice or mixed) of these cloud tops is measured and analysed to yield a dataset of the glaciation events that have occured and the properties of the tracked cloud tops.

## 1. Structure
The processing is divided into the following steps:

1. **Preprocessing**  
   - Resampling is performed to convert geostationary data to a regular latitude/longitude reference frame.  
   - Cloud top temperature filtering is applied to split larger clouds into individual temperature homogenious cloud segments
   - The data is aggregated in n x n bins (usually n=3) for reduced processing time and data storage

2. **Tracking**  
   - The PyFLEXTRKR library is utilized to track the resulting cloud segments. The library tracks segments with area larger than 1000 [km^2] surviving more than 45 min 

3. **Postprocessing**  
   - The tracked fragments are analyzed, and data for each cloud is stored in a Parquet binary file format. 

4. **Result Analysis**  
   - Cloud glaciation is identified, and the CGT is measured.
