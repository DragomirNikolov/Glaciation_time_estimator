import os
import sys
import logging
import dask
from dask.distributed import Client, LocalCluster
from pyflextrkr.ft_utilities import load_config, setup_logging
from pyflextrkr.idfeature_driver import idfeature_driver
from pyflextrkr.tracksingle_driver import tracksingle_driver
from pyflextrkr.gettracks import gettracknumbers
from pyflextrkr.trackstats_driver import trackstats_driver
from pyflextrkr.link_mergesplit_tracks import link_mergesplit_tracks
from pyflextrkr.mapfeature_driver import mapfeature_driver

# Purpose: Main script for tracking generic features
# Author: Zhe Feng (zhe.feng@pnnl.gov)

def run_generic_tracking(pyflextrkr_config_file):
    # Load configuration file
    config_file = sys.argv[1]
    config = load_config(pyflextrkr_config_file)

    # Set the logging message level
    setup_logging(config)
    logger = logging.getLogger(__name__)
    logger.info("START OF A NEW RUN")
    logger.debug("Logger set up succesfully")
    # Specify track statistics file basename and pixel-level output directory
    # for mapping track numbers to pixel files
    finalstats_filebase = config['finalstats_filebase']  # MCS tracks defined by Tb-only
    logging.debug(config)

    ################################################################################################
    # Parallel processing options
    if config['run_parallel'] == 1:
        # Set Dask temporary directory for workers
        dask_tmp_dir = config.get("dask_tmp_dir", "./")
        dask.config.set({'temporary-directory': dask_tmp_dir})
        # Local cluster
        cluster = LocalCluster(n_workers=config['nprocesses'], threads_per_worker=1)
        client = Client(cluster)
        client.run(setup_logging, config)
    elif config['run_parallel'] == 2:
        # Dask-MPI
        scheduler_file = os.path.join(os.environ["SCRATCH"], "scheduler.json")
        client = Client(scheduler_file=scheduler_file)
        client.run(setup_logging, config)
    else:
        logger.info(f"Running in serial.")

    # Step 1 - Identify features
    if config['run_idfeature']:
        logger.info('\n#########\nRUNING IDFEATURE\n#########')
        idfeature_driver(config)

    # Step 2 - Link features in time adjacent files
    if config['run_tracksingle']:
        logger.info('\n#########\nRUNING TRACKSINGLE\n#########')
        tracksingle_driver(config)

    # Step 3 - Track features through the entire dataset
    if config['run_gettracks']:
        logger.info('\n#########\nRUNING GETTRACKS\n#########')
        tracknumbers_filename = gettracknumbers(config)

    # Step 4 - Calculate track statistics
    if config['run_trackstats']:
        logger.info('\n#########\nRUNING TRACKSTATS\n#########')
        trackstats_filename = trackstats_driver(config)

    # Step 5 - Link merge/split tracks to main tracks
    if config['run_mergesplit']:
        finaltrackstats_filename = link_mergesplit_tracks(config)

    # Step 6 - Map tracking to pixel files
    if config['run_mapfeature']:
        mapfeature_driver(config, trackstats_filebase=finalstats_filebase)
    # If Step 5 (link merge/split tracks) is not desired, it can be skipped (comment it out)
    # In that case, use the following for Step 6 (no need to provide trackstats_filebase argument)
    # # Step 6 - Map tracking to pixel files
    # if config['run_mapfeature']:
    #     mapfeature_driver(config)

if __name__ == '__main__':
    config_file = sys.argv[1]
    run_generic_tracking(config_file)
    

    