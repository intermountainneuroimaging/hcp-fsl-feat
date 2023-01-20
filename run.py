#!/usr/bin/env python
"""The run script."""
import json
import logging
import os
import shutil
import sys
from pathlib import Path
from typing import List, Tuple, Union

from flywheel_bids.results.zip_intermediate import (
    zip_all_intermediate_output,
    zip_intermediate_selected,
)
from flywheel_bids.utils.download_run_level import download_bids_for_runlevel
from flywheel_bids.utils.run_level import get_analysis_run_level_and_hierarchy
from flywheel_gear_toolkit import GearToolkitContext
from flywheel_gear_toolkit.licenses.freesurfer import install_freesurfer_license
from flywheel_gear_toolkit.utils.file import sanitize_filename
from flywheel_gear_toolkit.utils.metadata import Metadata
from flywheel_gear_toolkit.utils.zip_tools import zip_output

# This design with the main interfaces separated from a gear module (with main and
# parser) allows the gear module to be publishable, so it can then be imported in
# another project, which enables chaining multiple gears together.
from fw_gear_hcp_fsl_feat.main import prepare, run
from fw_gear_hcp_fsl_feat.parser import parse_config
from utils.dry_run import pretend_it_ran
from utils.zip_htmls import zip_htmls

from utils.singularity import run_in_tmp_dir

# The gear is split up into 2 main components. The run.py file which is executed
# when the container runs. The run.py file then imports the rest of the gear as a
# module.

log = logging.getLogger(__name__)

# pylint: disable=too-many-locals,too-many-statements
def main(context: GearToolkitContext):
    FWV0 = Path.cwd()
    log.info("Running gear in %s", FWV0)
    output_dir = context.output_dir
    log.info("output_dir is %s", output_dir)
    work_dir = context.work_dir
    log.info("work_dir is %s", work_dir)

    #initiat return_code
    return_code = 0

    """Parses config and runs."""
    # For now, don't allow runs at the project level:
    destination = context.client.get(context.destination["id"])
    if destination.parent.type == "project":
        log.exception(
            "This version of the gear does not run at the project level. "
            "Try running it for each individual subject."
        )
        # sys.exit(1)
        return_code = 1


    # Errors and warnings will always be logged when they are detected.
    # Keep a list of errors and warning to print all in one place at end of log
    # Any errors will prevent the BIDS App from running.
    errors = []
    warnings = []

    # Call the fw_gear_bids_qsiprep.parser.parse_config function
    # to extract the args, kwargs from the context (e.g. config.json).
    gear_options, app_options = parse_config(context)

    # #adding the usual environment call
    # environ = get_and_log_environment()

    prepare_errors, prepare_warnings = prepare(
        gear_options=gear_options,
        app_options=app_options,
    )
    errors += prepare_errors
    warnings += prepare_warnings

    # if len(errors) == 0:
    #
    #     # Pseudo code
    #
    #     # 1... get inputs
    #     # 2... check fsf file and inputs for inconsistencies
    #     # 3... add all config options to fsf file
    #     # 4... add all inputs to fsf file
    #     # 5... execute FEAT  --> do that below
    #     # 6... cleanup.. flatten zip file, zip *.feat directory
    #
    #     # errors += get_input_errors
    #
    #
    #
    # else:
    #     run_label = "error"
    #     log.info("Did not download BIDS because of previous errors")
    #     print(errors)
    #
    # if len(errors) > 0:
    #     e_code = 1
    #     log.info("Command was NOT run because of previous errors.")
    #
    # elif gear_options["dry-run"]:
    #     e_code = 0
    #     pretend_it_ran(gear_options, app_options)
    #     save_metadata(
    #         context,
    #         gear_options["output_analysis_id_dir"] / "qsiprep",
    #         {"dry-run": "true"},
    #     )
    #     e = "gear-dry-run is set: Command was NOT run."
    #     log.warning(e)
    #     warnings.append(e)
    #
    # else:
    #     try:
    #         # Pass the args, kwargs to fw_gear_qsiprep.main.run function to execute
    #         # the main functionality of the gear.
    #         e_code = run(gear_options, app_options)
    #
    #
    #     except RuntimeError as exc:
    #         e_code = 1
    #         errors.append(str(exc))
    #         log.critical(exc)
    #         log.exception("Unable to execute command.")
    #
    #     else:
    #         # We want to save the metadata only if the run was successful.
    #         # We want to save partial outputs in the event of the app crashing, because
    #         # the partial outputs can help pinpoint what the exact problem was. So we
    #         # have `post_run` further down.
    #         save_metadata(context, gear_options["output_analysis_id_dir"] / "qsiprep")
    #
    # # Cleanup, move all results to the output directory.
    # # post_run should be run regardless of dry-run or exit code.
    # # It will be run even in the event of an error, so that the partial results are
    # # available for debugging.
    # post_run(
    #     gear_name=context.manifest["name"],
    #     gear_options=gear_options,
    #     analysis_output_dir=str(gear_options["output_analysis_id_dir"]),
    #     run_label=run_label,
    #     errors=errors,
    #     warnings=warnings,
    # )

    # gear_builder = context.manifest.get("custom").get("gear-builder")
    # # gear_builder.get("image") should be something like:
    # # flywheel/bids-qsiprep:0.0.1_0.15.1
    # container = gear_builder.get("image").split(":")[0]
    # log.info("%s Gear is done.  Returning %s", container, e_code)

    # Exit the python script (and thus the container) with the exit
    # code returned by fw_gear_bids_qsiprep.main.run function.
    # sys.exit(e_code)
    # return_code = e_code
    # return return_code


# pylint: enable=too-many-locals,too-many-statements


# Only execute if file is run as main, not when imported by another module
if __name__ == "__main__":  # pragma: no cover
    # Get access to gear config, inputs, and sdk client if enabled.
    with GearToolkitContext() as gear_context:
        scratch_dir = run_in_tmp_dir(gear_context.config["gear-writable-dir"])
    # Has to be instantiated twice here, since parent directories might have
    # changed
    with GearToolkitContext() as gear_context:

        # # Initialize logging, set logging level based on `debug` configuration
        # # key in gear config.
        # gear_context.init_logging()

        # Pass the gear context into main function defined above.
        return_code = main(gear_context)
    # clean up (might be necessary when running in a shared computing environment)
    if scratch_dir:
        log.debug("Removing scratch directory")
        for thing in scratch_dir.glob("*"):
            if thing.is_symlink():
                thing.unlink()  # don't remove anything links point to
                log.debug("unlinked %s", thing.name)
        shutil.rmtree(scratch_dir)
        log.debug("Removed %s", scratch_dir)

    sys.exit(return_code)
