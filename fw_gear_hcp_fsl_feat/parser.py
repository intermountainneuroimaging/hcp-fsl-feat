"""Parser module to parse gear config.json."""
from typing import Tuple
from zipfile import ZipFile
from flywheel_gear_toolkit import GearToolkitContext
import os
import logging
import glob
import subprocess as sp
from pathlib import Path
from fw_gear_hcp_fsl_feat.main import searchfiles

log = logging.getLogger(__name__)


def parse_config(
        gear_context: GearToolkitContext,
) -> Tuple[dict, dict]:
    """Parse the config and other options from the context, both gear and app options.

    Returns:
        gear_options: options for the gear
        app_options: options to pass to the app
    """
    # ##   Gear config   ## #

    gear_options = {
        "dry-run": gear_context.config.get("gear-dry-run"),
        "output-dir": gear_context.output_dir,
        "destination-id": gear_context.destination["id"],
        "work-dir": gear_context.work_dir,
        "client": gear_context.client,
        "environ": os.environ,
        "debug": gear_context.config.get("debug"),
        "hcpfunc_zipfile": gear_context.get_input_path("functional_zip"),
        "hcpstruct_zipfile": gear_context.get_input_path("structural_zip"),
        "event_files": gear_context.get_input_path("event-files"),
        "FSF_TEMPLATE": gear_context.get_input_path("FSF_TEMPLATE")
    }

    # set the output dir name for the BIDS app:
    gear_options["output_analysis_id_dir"] = (
            gear_options["output-dir"] / gear_options["destination-id"]
    )

    # ##   App options:   ## #
    app_options_keys = [
        "task-name",
        "output-name",
        "motion-confound",
        "dummy-scans"
    ]
    app_options = {key: gear_context.config.get(key) for key in app_options_keys}

    work_dir = gear_options["work-dir"]
    if work_dir:
        app_options["work-dir"] = work_dir

    if gear_context.get_input_path("icafix_functional_zip"):
        app_options["icafix"] = True
        gear_options["icafix_functional_zip"] = gear_context.get_input_path("icafix_functional_zip")

    else:
        app_options["icafix"] = False

    # pull input filepaths
    log.info("Inputs file path, %s", gear_options["hcpfunc_zipfile"])
    log.info("Inputs file path, %s", gear_options["hcpstruct_zipfile"])
    if app_options["icafix"]:
        log.info("Additional inputs file path, %s", gear_options["icafix_functional_zip"])

    # pull config settings
    gear_options["feat"] = {
        "common_command": "feat",
        "params": ""
    }

    # unzip HCPpipeline files
    unzip_hcp(gear_options, gear_options["hcpstruct_zipfile"])
    unzip_hcp(gear_options, gear_options["hcpfunc_zipfile"])

    if app_options["icafix"]:
        unzip_hcp(gear_options, gear_options["icafix_functional_zip"])

    funcpath = searchfiles(os.path.join(gear_options["work-dir"], "**", "MNINonLinear", "Results", "*"+app_options["task-name"]+"*"))

    if len(funcpath) > 1:
        log.error("Task name not unique")

    app_options["funcpath"] = funcpath[0]

    structpath = searchfiles(os.path.join(gear_options["work-dir"], "**", "MNINonLinear", "T1w_restore_brain.nii.gz"))

    if len(structpath) > 1:
        log.error("More than one qualified structural image present... Not sure what to do.")

    app_options["structpath"] = os.path.dirname(structpath[0])

    destination = gear_context.client.get(gear_context.destination["id"])
    sid = gear_context.client.get(destination.parents.subject)
    sesid = gear_context.client.get(destination.parents.session)

    app_options["sid"] = sid.label
    app_options["sesid"] = sesid.label

    return gear_options, app_options


def unzip_hcp(gear_options, zip_filename):
    """
    unzip_hcp unzips the contents of zipped gear output into the working
    directory.  All of the files extracted are tracked from the
    above process_hcp_zip.
    Args:
        gear_options: The gear context object
            containing the 'gear_dict' dictionary attribute with key/value,
            'gear-dry-run': boolean to enact a dry run for debugging
        zip_filename (string): The file to be unzipped
    """
    hcp_zip = ZipFile(zip_filename, "r")
    log.info("Unzipping hcp outputs, %s", zip_filename)
    if not gear_options["dry-run"]:
        hcp_zip.extractall(gear_options["work-dir"])
        log.debug(f'Unzipped the file to {gear_options["work-dir"]}')
