#!/usr/bin/env python3
"""
generate_configs.py
-------------------
Create 24 half‑monthly tracking‑config YAMLs for a given YEAR.

Example
-------
python /cluster/work/climate/dnikolo/n2o/Glaciation_time_estimator/configs/config_generator.py 2007 \
    /cluster/work/climate/dnikolo/n2o/Glaciation_time_estimator/configs/2007_tracking/01_01.yaml \
    /cluster/work/climate/dnikolo/n2o/Glaciation_time_estimator/configs

python /cluster/work/climate/dnikolo/n2o/Glaciation_time_estimator/configs/config_generator.py 2008 \
    /cluster/work/climate/dnikolo/n2o/Glaciation_time_estimator/configs/Model_grid_tests/short_test.yaml \
    /cluster/work/climate/dnikolo/n2o/Glaciation_time_estimator/configs/Model_grid_tests

python /cluster/work/climate/dnikolo/n2o/Glaciation_time_estimator/configs/config_generator.py 2007 \
    /cluster/work/climate/dnikolo/n2o/Glaciation_time_estimator/configs/Validation/2007_tracking/01_01.yaml \
    /cluster/work/climate/dnikolo/n2o/Glaciation_time_estimator/configs/Model_grid_tests

/cluster/work/climate/dnikolo/n2o/Glaciation_time_estimator/configs/April_testing/euler_template.yaml \
"""
import argparse
import os
from datetime import datetime

TIME_FMT = "%Y%m%d_%H%M"


def replace_times(template_str: str, start: str, end: str) -> str:
    """Replace the start_time and end_time lines in one go (no YAML lib needed)."""
    new_lines = []
    for ln in template_str.splitlines():
        stripped = ln.lstrip()
        if stripped.startswith("start_time:"):
            new_lines.append(f'start_time: "{start}"')
        elif stripped.startswith("end_time:"):
            new_lines.append(f'end_time: "{end}"')
        else:
            new_lines.append(ln)
    return "\n".join(new_lines) + "\n"


def main(year: int, template_path: str, output_root: str) -> None:
    with open(template_path, "r") as fp:
        template = fp.read()

    out_dir = os.path.join(output_root, f"{year}_tracking")
    os.makedirs(out_dir, exist_ok=True)

    for month in range(1, 13):
        # -------- segment 1: 1st 00:00  -->  15th 00:00 --------
        if month== 1:
            s1 = datetime(year, month, 1, 0, 0)
        else:
            s1 = datetime(year, month, 1, 0, 0)
        e1 = datetime(year, month, 15, 0, 0)
        txt1 = replace_times(template, s1.strftime(TIME_FMT), e1.strftime(TIME_FMT))
        with open(os.path.join(out_dir, f"{month:02d}_01.yaml"), "w") as f:
            f.write(txt1)

         # -------- segment 2: 15th 00:00  -->  end of month --------
        s2 = datetime(year, month, 15, 0, 0)
        if month == 12:
            e2 = datetime(year, 12, 31, 23, 45)
        else:
            e2 = datetime(year, month + 1, 1, 0, 0)
        txt2 = replace_times(template, s2.strftime(TIME_FMT), e2.strftime(TIME_FMT))
        with open(os.path.join(out_dir, f"{month:02d}_02.yaml"), "w") as f:
            f.write(txt2)

        # # The two sections overlap in one timestep so that the corresponding clouds can be joined
        # # -------- segment 3: 15th 15:00  -->  1st of next month 00:00 --------
        # s3 = datetime(year, month, 15, 15, 0)
        # if month == 12:
        #     e3 = datetime(year, 12, 31, 23, 45)
        # else:
        #     e3 = datetime(year, month + 1, 1, 0, 0)
        # txt3 = replace_times(template, s3.strftime(TIME_FMT), e3.strftime(TIME_FMT))
        # with open(os.path.join(out_dir, f"{month:02d}_03.yaml"), "w") as f:
        #     f.write(txt3)
        
       

        print(f"Wrote {month:02d}_01.yaml and {month:02d}_02.yaml")

    print(f"\nAll configs stored in: {out_dir}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Generate half‑monthly tracking configs")
    p.add_argument("year", type=int, help="e.g. 2007")
    p.add_argument("template_path", help="Full path to euler_template.yaml")
    p.add_argument(
        "output_root",
        help="Parent folder that will receive the {YEAR}_tracking/ directory",
    )
    args = p.parse_args()
    main(args.year, args.template_path, args.output_root)
