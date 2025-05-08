from glaciation_time_estimator.cloud_tracking.send_results import send_results
from glaciation_time_estimator.auxiliary_func.config_reader import read_config

if __name__ == "__main__":
    send_results(read_config())