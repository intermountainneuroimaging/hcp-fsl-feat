"""Main module."""

import logging
import os
import os.path as op
from pathlib import Path
from typing import List, Tuple
import subprocess as sp
import sys
import re
import shutil
from collections import OrderedDict
from zipfile import ZIP_DEFLATED, ZipFile

from flywheel_gear_toolkit import GearToolkitContext
from flywheel_gear_toolkit.interfaces.command_line import (
    build_command_list,
    exec_command,
)

log = logging.getLogger(__name__)

def prepare(
    gear_options: dict,
    app_options: dict,
) -> Tuple[List[str], List[str]]:
    """Prepare everything for the algorithm run.

    It should:
     - Install FreeSurfer license (if needed)

    Same for FW and RL instances.
    Potentially, this could be BIDS-App independent?

    Args:
        gear_options (Dict): gear options
        app_options (Dict): options for the app

    Returns:
        errors (list[str]): list of generated errors
        warnings (list[str]): list of generated warnings
    """
    # pylint: disable=unused-argument
    # for now, no errors or warnings, but leave this in place to allow future methods
    # to return an error
    errors: List[str] = []
    warnings: List[str] = []

    return errors, warnings
    # pylint: enable=unused-argument



def run(gear_options: dict, app_options: dict) -> int:
    """Run FSL-FEAT using HCPPipeline inputs.

    Arguments:
        gear_options: dict with gear-specific options
        app_options: dict with options for the BIDS-App

    Returns:
        run_error: any error encountered running the app. (0: no error)
    """
    log.info("This is the beginning of the run file")

    output_analysis_id_dir = Path(gear_options["output-dir"]) / Path(
        gear_options["destination-id"]
    )

    # prepare confounds file
    app_options = generate_confounds_file(gear_options, app_options)

    # prepare inputs files (cp input files w/ correct names to workdir)
    app_options = generate_input_files(gear_options, app_options)

    # prepare events files
    app_options = generate_event_files(gear_options, app_options)

    # prepare fsf design file
    app_options = generate_design_file(gear_options, app_options)

    # generate command
    command = generate_command(gear_options, app_options)

    # Create output directory
    log.info("Creating output directory %s", output_analysis_id_dir)
    Path(output_analysis_id_dir).mkdir(parents=True, exist_ok=True)

    # This is what it is all about
    exec_command(
        command,
        dry_run=gear_options["dry-run"],
        shell=True,
        cont_output=True,
    )

    # if we made it this far, return success:
    run_error = 0

    return run_error


def generate_confounds_file(gear_options: dict, app_options: dict):
    """
    Method specific to HCPPipeline preprocessed inputs. Builds a confounds file based on config options "motion_confound",
        "dummy-scans". If motion confound and dummy scans should be included, generate a text file containing all confounds.
    Args:
        gear_options (dict): options for the gear, from config.json
        app_options (dict): options for the app, from config.json

    Returns:
        app_options (dict): updated options for the app, from config.json
    """



    return app_options



def generate_input_files(gear_options: dict, app_options: dict):
    """
    Method specific to HCPPipeline preprocessed inputs. Use "task-name" and "icafix" passed in config to select correct
    functional preprocessed file for FEAT. Select correct T1w_brain and T1w image. HCPPipeline results are already MNI152
    registered, no registration should be applied.
    Args:
        gear_options (dict): options for the gear, from config.json
        app_options (dict): options for the app, from config.json

    Returns:
        app_options (dict): updated options for the app, from config.json
    """

    return app_options



def generate_event_files(gear_options: dict, app_options: dict):
    """
    Method used for all fsl-feat gear methods. Event file will be passed as (1) BIDS format, (2) 3-column custom format,
     (3) 1-entry per volume format. Check first if events are pasted as zip (do nothing except unzip). If tsv BIDS
     formatted, convert to 3-column custom format with standard naming convention.

    Args:
        gear_options (dict): options for the gear, from config.json
        app_options (dict): options for the app, from config.json

    Returns:
        app_options (dict): updated options for the app, from config.json
    """

    return app_options


def generate_design_file(gear_options: dict, app_options: dict):
    """
    Method specific to HCPPipeline preprocessed inputs. Check for correct registration method. Apply correct output directory
    name and path (name from config). Apply correct input set.

    Args:
        gear_options (dict): options for the gear, from config.json
        app_options (dict): options for the app, from config.json

    Returns:
        app_options (dict): updated options for the app, from config.json
    """

    return app_options


def generate_command(
    gear_options: dict,
    app_options: dict,
) -> List[str]:
    """Build the main command line command to run.

    This method should be the same for FW and XNAT instances. It is also BIDS-App
    generic.

    Args:
        gear_options (dict): options for the gear, from config.json
        app_options (dict): options for the app, from config.json
    Returns:
        cmd (list of str): command to execute
    """

    cmd = []

    return cmd