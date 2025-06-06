#!/usr/bin/env python3
"""
generate_glac_configs.py

Reads a “template” YAML file and creates multiple YAML files by varying:
  - year  (in start_time / end_time strings)
  - glac_threshold (0.2, 0.3, 0.4, 0.5)
  - postprocessing_output_dir  (either “eu:/cluster/…/Cloud_analysis/” or “/wolke_scratch/dnikolo/”)

Produced filenames follow:
  eu_{year}_thresh_{int(threshold*10):02}.yaml
  n2o_{year}_thresh_{int(threshold*10):02}.yaml

Usage:
  python generate_glac_configs.py
"""

import os
import yaml

# Path to your “template” YAML file. Adjust as needed.
TEMPLATE_PATH = "/wolke_scratch/dnikolo/Glaciation_time_estimator/configs/glac_configs/2009_thresh_02.yaml"

# List of years you want to generate configs for.
# (Each year will replace the YYYY in start_time/end_time.)
YEARS = [year for year in range(2007,2017)]

# List of glac_threshold values (floats).  Each will appear in the new files.
THRESHOLDS = [0.2, 0.3, 0.4, 0.5]

# Two “modes” for postprocessing_output_dir → output filename prefix
POST_DIRS = [
    # (filename_prefix, new_postprocessing_output_dir)
    ("eu", "eu:/cluster/work/climate/dnikolo/Cloud_analysis/"),
    ("n2o", "/wolke_scratch/dnikolo/"),
]


def load_template(path):
    """Load the YAML template into a Python dictionary."""
    with open(path, "r") as f:
        data = yaml.safe_load(f)
    return data


def tweak_times(template_dict, new_year):
    """
    Given a dict with keys 'start_time' and 'end_time' in the form "YYYYMMDD_HHMM",
    return two strings where only the 4-digit year is replaced by new_year.
    """
    out = {}
    for key in ("start_time", "end_time"):
        original = template_dict.get(key, "")
        # original is e.g. "20090515_1500"
        if isinstance(original, str) and len(original) >= 9 and "_" in original:
            date_part, time_part = original.split("_", 1)
            # date_part is "20090515".  Keep month-day = date_part[4:],
            # so new_date = f"{new_year}{date_part[4:]}"
            new_date_part = f"{new_year}{date_part[4:]}"
            out[key] = f"{new_date_part}_{time_part}"
        else:
            # If it’s missing or not in the expected format, just leave it as-is
            out[key] = original
    return out["start_time"], out["end_time"]


def main():
    # 1) load the template once
    template = load_template(TEMPLATE_PATH)

    # 2) remember the original start_time/end_time so we can parse out MMDD_HHMM
    original_start = template.get("start_time", "")
    original_end = template.get("end_time", "")

    if not original_start or "_" not in original_start:
        raise ValueError("Template's start_time is missing or not in YYYYMMDD_HHMM format.")
    if not original_end or "_" not in original_end:
        raise ValueError("Template's end_time is missing or not in YYYYMMDD_HHMM format.")

    # 3) loop over all combinations
    for year in YEARS:
        # 3a) compute the two new time strings
        new_start, new_end = tweak_times(template, year)

        for threshold in THRESHOLDS:
            for prefix, post_dir in POST_DIRS:
                # a) deep‐copy the template dict so we don’t overwrite it
                new_conf = dict(template)  # top-level shallow copy is OK, since we only overwrite scalars

                # b) set the new year-adjusted times
                new_conf["start_time"] = new_start
                new_conf["end_time"] = new_end

                # c) set the new glac_threshold
                new_conf["glac_threshold"] = threshold

                # d) set the new postprocessing_output_dir
                new_conf["postprocessing_output_dir"] = post_dir

                # e) choose output filename
                #    int(threshold*10) gives 2,3,4,5 → formatted as 02,03,...
                thresh_int = int(threshold * 10)
                filename = f"{prefix}_{year}_thresh_{thresh_int:02}.yaml"

                # f) write it out
                with open(filename, "w") as out_f:
                    # Use safe_dump to produce a clean, readable YAML.
                    # Setting default_flow_style=False ensures block style (not inline)
                    yaml.safe_dump(
                        new_conf,
                        out_f,
                        default_flow_style=False,
                        sort_keys=False,  # keep the same key order as in template if possible
                    )

                print(f"Written → {filename}")

    print("All configurations generated.")


if __name__ == "__main__":
    main()
