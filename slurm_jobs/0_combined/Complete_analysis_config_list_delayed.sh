#!/usr/bin/env bash
set -euo pipefail

print_usage() {
  cat >&2 <<'EOF'
Usage:
  submit_configs.sh -c CFG [-c CFG2 ...] [-w WAIT_MIN] [-m gte|msgi] [-d GTE_DIR] [-s MSGI_DIR] [-p PREPROC_CFG] [-y YEAR] [-g GLAC_CFG] [--dry-run]

Required:
  -c CFG            Tracking config file (repeatable). You can pass multiple -c.

Optional:
  -m MODE           Preprocessing mode: gte (default) or msgi
  -p PREPROC_CFG    Required when MODE=msgi (separate preprocessing configuration)
  -d GTE_DIR        Path to GTE root (defaults to $GTE_DIR if set)
  -s MSGI_DIR       Path to MSGI root (defaults to $MSGI_DIR if set)
  -w WAIT_MIN       Delay each config submission by index*WAIT_MIN minutes (0-based)
  -y YEAR           Year used for downstream scripts/job names if needed
  -g GLAC_CFG       Glaciation detection config (default: $GTE_DIR/configs/${YEAR}_tracking/01_01.yaml if YEAR is set)
  --dry-run         Print commands instead of submitting

Examples:
  # GTE preprocessing per config
  ./submit_configs.sh -d /path/to/GTE -c a.yaml -c b.yaml

  # MSGI preprocessing per config (same preproc config reused for each)
  ./submit_configs.sh -d /path/to/GTE -s /path/to/MSGI -m msgi -p preproc.yaml -c a.yaml -c b.yaml

  # Add a 10-minute stagger between configs
  ./submit_configs.sh -c a.yaml -c b.yaml -w 10
EOF
}

# Example usage:
# bash /cluster/work/climate/dnikolo/n2o/Glaciation_time_estimator/slurm_jobs/0_combined/Complete_analysis_config_list.sh -c /cluster/work/climate/dnikolo/n2o/Glaciation_time_estimator/configs/Model_grid_tests/online_model_data_resampled_geostationary.yaml -m msgi -p /cluster/work/climate/dnikolo/MSGI/configs/testing/ryan_nudged_test.yaml

# Defaults from env if present
GTE_DIR="${GTE_DIR:-}"
MSGI_DIR="${MSGI_DIR:-}"
MODE="gte"
wait_time=""
YEAR=""
GLAC_CFG=""
DRY_RUN=0

configs=()

# --- add this near the top, before getopts loop ---
DRY_RUN=0
_filtered=()
for a in "$@"; do
  case "$a" in
    (--dry-run|--dry_run) DRY_RUN=1 ;;   # accept both spellings
    *) _filtered+=("$a") ;;
  esac
done
set -- "${_filtered[@]}"
# --- end patch ---

# Parse flags (repeatable -c)
while getopts ':c:w:m:d:s:p:y:g:' flag; do
  case "${flag}" in
    c) configs+=("${OPTARG}") ;;
    w) wait_time="${OPTARG}" ;;
    m) MODE="${OPTARG}" ;;
    d) GTE_DIR="${OPTARG}" ;;
    s) MSGI_DIR="${OPTARG}" ;;
    p) PREPROC_CFG="${OPTARG}" ;;
    y) YEAR="${OPTARG}" ;;
    g) GLAC_CFG="${OPTARG}" ;;
    :)
      echo "Error: -${OPTARG} requires an argument." >&2
      print_usage
      exit 1
      ;;
    \?)
      print_usage
      exit 1
      ;;
  esac
done
shift $((OPTIND - 1))

# Allow configs as positional args too (after flags)
if [[ $# -gt 0 ]]; then
  for x in "$@"; do
    [[ "$x" == "--dry-run" ]] && continue
    configs+=("$x")
  done
fi

if [[ ${#configs[@]} -eq 0 ]]; then
  echo "Error: Provide at least one config via -c or positional args." >&2
  print_usage
  exit 1
fi

if [[ -z "${GTE_DIR}" ]]; then
  echo "Error: GTE_DIR not set. Provide -d or export GTE_DIR." >&2
  exit 1
fi

if [[ "${MODE}" != "gte" && "${MODE}" != "msgi" ]]; then
  echo "Error: -m must be 'gte' or 'msgi'." >&2
  exit 1
fi

if [[ "${MODE}" == "msgi" ]]; then
  if [[ -z "${MSGI_DIR}" ]]; then
    echo "Error: MODE=msgi requires MSGI_DIR. Provide -s or export MSGI_DIR." >&2
    exit 1
  fi
  if [[ -z "${PREPROC_CFG:-}" ]]; then
    echo "Error: MODE=msgi requires -p PREPROC_CFG (separate preprocessing configuration file)." >&2
    exit 1
  fi
  if [[ ! -f "${PREPROC_CFG}" ]]; then
    echo "Error: PREPROC_CFG not found: ${PREPROC_CFG}" >&2
    exit 1
  fi
fi

# Validate configs exist
for cfg in "${configs[@]}"; do
  if [[ ! -f "${cfg}" ]]; then
    echo "Error: Config not found: ${cfg}" >&2
    exit 1
  fi
done

# Paths to job scripts
GTE_PREPROC_JOB="${GTE_DIR%/}/slurm_jobs/1_preprocessing/preproc_job.bsub"
GTE_COMBINED_SH="${GTE_DIR%/}/slurm_jobs/0_combined/All_t_tracking_and_post.sh"
GTE_GLAC_JOB="${GTE_DIR%/}/slurm_jobs/3_postprocessing/glaciation_detection.bsub"
MSGI_PREPROC_JOB="${MSGI_DIR%/}/slurm/model_preprocessing.bsub"

postproc_job_ids=()

run_cmd() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "+ $*"
  else
    eval "$@"
  fi
}

# If YEAR not provided, try to infer a 4-digit year from the first config name/path (best effort)
if [[ -z "${YEAR}" ]]; then
  if [[ "${configs[0]}" =~ ([0-9]{4}) ]]; then
    YEAR="${BASH_REMATCH[1]}"
  fi
fi

echo "Preprocessing mode: ${MODE}"
echo "Configs (${#configs[@]}):"
for c in "${configs[@]}"; do echo "  - $c"; done
[[ -n "${wait_time}" ]] && echo "Stagger: index*${wait_time} minutes"
[[ -n "${YEAR}" ]] && echo "YEAR: ${YEAR}"

for i in "${!configs[@]}"; do
  CONFIG_FILE="${configs[$i]}"
  tag="$(basename "${CONFIG_FILE}")"
  tag="${tag%.*}"  # strip .yaml/.yml
  
  # optional delay
  begin_arg=""
  if [[ -n "${wait_time}" ]]; then
    delay_minutes=$(( i * wait_time + 360 ))
    begin_arg="--begin=now+${delay_minutes}minutes"
  fi
  if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "+ sbatch --parsable ${begin_arg} -J \"${tag}_preproc\" \"${GTE_PREPROC_JOB}\" -c \"${CONFIG_FILE}\""
  echo "+ bash \"${GTE_COMBINED_SH}\" -c \"${CONFIG_FILE}\" -d <PREPROC_JOBID> ${YEAR:+-y \"$YEAR\"}"
  continue
  fi
  # Submit preprocessing
  if [[ "${MODE}" == "gte" ]]; then
    if [[ ! -f "${GTE_PREPROC_JOB}" ]]; then
      echo "Error: GTE preprocessing job script not found: ${GTE_PREPROC_JOB}" >&2
      exit 1
    fi
    cmd="sbatch --parsable ${begin_arg} -J \"${tag}_preproc\" \"${GTE_PREPROC_JOB}\" -c \"${CONFIG_FILE}\""
    preproc_id=$(run_cmd "$cmd")
  else
    if [[ ! -f "${MSGI_PREPROC_JOB}" ]]; then
      echo "Error: MSGI preprocessing job script not found: ${MSGI_PREPROC_JOB}" >&2
      exit 1

    fi
    # NOTE: exports TRACK_CONFIG for convenience if your MSGI job script wants to know the tracking config.
    cmd="sbatch --parsable ${begin_arg} -J \"${tag}_preproc\" \"${MSGI_PREPROC_JOB}\" -c \"${CONFIG_FILE}\" -m \"${PREPROC_CFG}\""
    preproc_id=$(run_cmd "$cmd")
  fi
    
  # Submit tracking + post-processing (depends on preproc_id)
  if [[ ! -f "${GTE_COMBINED_SH}" ]]; then
    echo "Error: Combined tracking/post script not found: ${GTE_COMBINED_SH}" >&2
    exit 1
  fi

  if [[ -n "${YEAR}" ]]; then
    raw=$(bash "${GTE_COMBINED_SH}" -c "${CONFIG_FILE}" -d "${preproc_id}" -y "${YEAR}")
  else
    # If your combined script truly requires -y, then pass -y explicitly via CLI.
    raw=$(bash "${GTE_COMBINED_SH}" -c "${CONFIG_FILE}" -d "${preproc_id}")
  fi

  # Determine glaciation config if not explicitly set
  if [[ -z "${GLAC_CFG}" && -n "${YEAR}" ]]; then
    GLAC_CFG=$CONFIG_FILE
  fi
  

  # Extract numeric job id after "ID: "
  postproc_job_id="${raw##*ID: }"
  postproc_job_ids+=( "${postproc_job_id}" )

  glac_name="${tag}_glac"
  cmd="sbatch --dependency=afterok:${postproc_job_id} -J \"${glac_name}\" \"${GTE_GLAC_JOB}\" -c \"${CONFIG_FILE}\""
  glac_id=$(run_cmd "$cmd")

  echo "Config: ${CONFIG_FILE}"
  echo "  preproc:  ${preproc_id}"
  echo "  postproc: ${postproc_job_id}"
  echo "  glac: ${glac_id}"
done

# # Glaciation detection after all postproc jobs
# if [[ ${#postproc_job_ids[@]} -gt 0 ]]; then
#   dependency_list=$(IFS=,; echo "${postproc_job_ids[*]}")

#   # Determine glaciation config if not explicitly set
#   if [[ -z "${GLAC_CFG}" && -n "${YEAR}" ]]; then
#     GLAC_CFG=configs[0]
#   fi

#   if [[ -n "${GLAC_CFG}" ]]; then
#     if [[ ! -f "${GTE_GLAC_JOB}" ]]; then
#       echo "Error: Glaciation detection job script not found: ${GTE_GLAC_JOB}" >&2
#       exit 1
#     fi
#     if [[ ! -f "${GLAC_CFG}" ]]; then
#       echo "Error: Glaciation config not found: ${GLAC_CFG}" >&2
#       exit 1
#     fi

#     glac_name="${YEAR:-glac}_glac"
#     cmd="sbatch --dependency=afterok:${dependency_list} -J \"${glac_name}\" \"${GTE_GLAC_JOB}\" -c \"${GLAC_CFG}\""
#     run_cmd "$cmd"
#     echo "Glaciation detection job submitted (name): ${glac_name}"
#   else
#     echo "Skipping glaciation detection (no -g provided and YEAR not available to infer default)."
#   fi
# fi