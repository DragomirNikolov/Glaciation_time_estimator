import os
import subprocess
import re
import sys
from tqdm import tqdm

def get_cdo_command(nc_file_path):
    if "/wolke_scratch/dnikolo/CLAAS_Data/np" in nc_file_path or "/wolke_scratch/dnikolo/CLAAS_Data/sp" in nc_file_path:
        return f"cdo -selname,cph,ctt info {nc_file_path}"
    elif "/wolke_scratch/dnikolo/CLAAS_Data/Resampled_Data" in nc_file_path:
        return f"cdo -selname,cph_resampled,ctt_resampled info {nc_file_path}"
    elif "/wolke_scratch/dnikolo/CLAAS_Data/Filtered_Data" in nc_file_path:
        return f"cdo -selname,cph_filtered info {nc_file_path}"
    else:
        return f"cdo info {nc_file_path}"

def process_nc_files(target_folder):
    cdo_info_file = os.path.join(target_folder, "cdo_info.txt")
    failed_validation_file = os.path.join(target_folder, "failed_validation.txt")
    
    # Ensure files exist before overwriting
    with open(cdo_info_file, "w") as f:
        pass
    with open(failed_validation_file, "w") as f:
        pass
    
    nc_files = sorted([f for f in os.listdir(target_folder) if f.endswith(".nc")])
    
    with open(failed_validation_file, "w") as fail_file, tqdm(total=len(nc_files), desc=f"Processing {target_folder}", unit="file") as pbar:
        for filename in nc_files:
            nc_file_path = os.path.join(target_folder, filename)
            
            # Select the correct CDO command
            command = get_cdo_command(nc_file_path)
            result = subprocess.run(command, shell=True, capture_output=True, text=True)
            
            if result.returncode != 0 and "Abort" in result.stderr:
                # If CDO fails to open the file and processing is aborted, mark it as invalid
                fail_file.write(f"{nc_file_path}\n")
                print(f"CDO failed to process: {nc_file_path}")
            else:
                with open(cdo_info_file, "w") as cdo_file:
                    cdo_file.write(f"\nFile: {filename}\n")
                    cdo_file.write(result.stdout)
                    cdo_file.write("\n")
                
                # Check for 'nan' in the Mean column
                for line in result.stdout.split("\n"):
                    match = re.search(r'\s+\d+ : [\d-]+ [\d:]+\s+\d+\s+\d+\s+\d+ :\s+([-0-9.e]+|nan|0.0000)', line)
                    if match and (match.group(1) == "nan" or match.group(1) == "0.0000"):
                        fail_file.write(f"{nc_file_path}\n")
                        break  # No need to check further if a 'nan' or '0.0000' is found
            
            pbar.update(1)

def combine_failed_validations(base_folder):
    combined_failed_validation = os.path.join(base_folder, "failed_validation.txt")
    with open(combined_failed_validation, "w") as combined_file:
        for root, _, files in os.walk(base_folder):
            if "failed_validation.txt" in files:
                failed_validation_path = os.path.join(root, "failed_validation.txt")
                with open(failed_validation_path, "r") as fail_file:
                    combined_file.write(fail_file.read())

def delete_invalid_files(base_folder):
    combined_failed_validation = os.path.join(base_folder, "failed_validation.txt")
    deleted_count = 0
    
    if os.path.exists(combined_failed_validation):
        with open(combined_failed_validation, "r") as fail_file:
            file_paths = fail_file.read().splitlines()
        
        for file_path in file_paths:
            if not (file_path.startswith("/wolke_scratch/dnikolo/CLAAS_Data/np") or 
                    file_path.startswith("/wolke_scratch/dnikolo/CLAAS_Data/sp")):
                try:
                    os.remove(file_path)
                    print(f"Deleted: {file_path}")
                    deleted_count += 1
                except OSError as e:
                    print(f"Error deleting {file_path}: {e}")
    
    print(f"Total deleted files: {deleted_count}")

def process_all_subfolders(base_folder):
    subfolders = [root for root, dirs, files in os.walk(base_folder) if any(file.endswith(".nc") for file in files)]
    
    with tqdm(total=len(subfolders), desc="Processing subfolders", unit="folder") as pbar:
        for folder in subfolders:
            process_nc_files(folder)
            pbar.update(1)
    combine_failed_validations(base_folder)
    #delete_invalid_files(base_folder)

def process_specific_folders(date_str):
    base_paths = [
        f"/wolke_scratch/dnikolo/CLAAS_Data/Filtered_Data/np/{date_str[:4]}/{date_str[5:]}",
        f"/wolke_scratch/dnikolo/CLAAS_Data/Filtered_Data/sp/{date_str[:4]}/{date_str[5:]}",
        f"/wolke_scratch/dnikolo/CLAAS_Data/Resampled_Data/np/{date_str[:4]}/{date_str[5:]}",
        f"/wolke_scratch/dnikolo/CLAAS_Data/Resampled_Data/sp/{date_str[:4]}/{date_str[5:]}"
    ]
    # Process each folder and its subfolders
    for folder in base_paths:
        if os.path.exists(folder):
            process_all_subfolders(folder)
        else:
            raise FileExistsError(f"Folder doesn't exist: {folder}")
    
    # ========================
    # New code starts here
    # Combine the four failed_validation.txt files into one file in the Validation_results folder.
    validation_results_dir = "/wolke_scratch/dnikolo/CLAAS_Data/Validation_results"
    os.makedirs(validation_results_dir, exist_ok=True)
    # Use the date_str to name the combined file as YYYY_DD_Preproc.txt.
    # (If your date string is e.g. "2025_02", then the output file will be "2025_02_Preproc.txt")
    combined_file_name = f"{date_str[:4]}_{date_str[5:]}_Preproc.txt"
    combined_file_path = os.path.join(validation_results_dir, combined_file_name)

    with open(combined_file_path, "w") as outfile:
        for folder in base_paths:
            failed_file = os.path.join(folder, "failed_validation.txt")
            if os.path.exists(failed_file):
                with open(failed_file, "r") as infile:
                    content = infile.read()
                    # Optionally, write a header to identify the source folder:
                    outfile.write(f"### Source: {failed_file} ###\n")
                    outfile.write(content)
                    outfile.write("\n")
    print(f"Combined failed validations saved to {combined_file_path}")
    # New code ends here
    # ========================

if __name__ == "__main__":
    if "--final" in sys.argv:
        index = sys.argv.index("--final")
        if index + 1 < len(sys.argv):
            date_str = sys.argv[index + 1]
            process_specific_folders(date_str)
        else:
            print("Error: Missing date argument for --final")
            sys.exit(1)
    elif len(sys.argv) < 2:
        print("Usage: python script.py <folder_path> or python script.py --final YYYY_MM")
        sys.exit(1)
    else:
        target_folder = sys.argv[1]
        process_all_subfolders(target_folder)
