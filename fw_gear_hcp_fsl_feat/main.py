"""Main module."""

import logging
import os
import os.path as op
import glob
from pathlib import Path
from typing import List, Tuple
import subprocess as sp
import numpy as np
import pandas as pd
import sys
import re
import shutil
import tempfile
from collections import OrderedDict
from zipfile import ZIP_DEFLATED, ZipFile
import errorhandler
from typing import List, Tuple, Union
import nibabel as nib
import stat
from flywheel_gear_toolkit.utils.zip_tools import zip_output

from utils.command_line import exec_command
from utils.feat_html_singlefile import main as flathtml

log = logging.getLogger(__name__)

# Track if message gets logged with severity of error or greater
error_handler = errorhandler.ErrorHandler()

# Also log to stderr
stream_handler = logging.StreamHandler(stream=sys.stderr)
log.addHandler(stream_handler)


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

    # prepare inputs files (cp input files w/ correct names to workdir)
    app_options = generate_input_files(gear_options, app_options)

    # prepare confounds file
    app_options = generate_confounds_file(gear_options, app_options)

    # prepare events files
    app_options = generate_event_files(gear_options, app_options)

    # prepare fsf design file
    app_options = generate_design_file(gear_options, app_options)

    # generate command
    command = generate_command(gear_options, app_options)

    if error_handler.fired:
        log.critical('Failure: exiting with code 1 due to logged errors')
        run_error = 1
        return run_error

    # This is what it is all about
    stdout, stderr, run_error = exec_command(
        command,
        dry_run=gear_options["dry-run"],
        shell=True,
        cont_output=True,
        cwd=gear_options["work-dir"]
    )

    if not gear_options["dry-run"]:

        # move result feat directory to outputs
        featdir = searchfiles(os.path.join(gear_options["work-dir"], "*.feat"))

        # Create output directory
        output_analysis_id_dir = os.path.join(gear_options["destination-id"], "sub-" + app_options["sid"], "ses-" + app_options["sesid"])
        Path(os.path.join(gear_options["work-dir"], output_analysis_id_dir)).mkdir(parents=True, exist_ok=True)

        log.info("Using output path %s", os.path.join(output_analysis_id_dir, os.path.basename(featdir[0])))

        shutil.copytree(featdir[0], os.path.join(gear_options["work-dir"], output_analysis_id_dir, os.path.basename(featdir[0])),dirs_exist_ok=True)

        # flatten html to single file
        flathtml(os.path.join(featdir[0], "report.html"))

        # make copies of design.fsf and html outside featdir before zipping
        inpath = os.path.join(featdir[0], "index.html")
        outpath = os.path.join(featdir[0], "report.html.zip")
        with ZipFile(outpath, "w", compression=ZIP_DEFLATED) as zf:
            zf.write(inpath, os.path.basename(inpath))

        shutil.copy(os.path.join(featdir[0], "report.html.zip"), os.path.join(gear_options["output-dir"], "report.html.zip"))
        shutil.copy(os.path.join(featdir[0], "design.fsf"), os.path.join(gear_options["output-dir"], "design.fsf"))

        cmd = "zip -r " + os.path.join(gear_options["output-dir"], os.path.basename(featdir[0])) + ".zip " + gear_options["destination-id"]
        execute_shell(cmd, dryrun=gear_options["dry-run"], cwd=gear_options["work-dir"])

        cmd = "chmod -R a+rwx " + os.path.join(gear_options["output-dir"])
        execute_shell(cmd, dryrun=gear_options["dry-run"], cwd=gear_options["output-dir"])

    else:
        shutil.copy(app_options["design_file"], os.path.join(gear_options["output-dir"], "design.fsf"))

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

    log.info("Building confounds file...")

    if app_options["motion-confound"]:
        motion_path = searchfiles(os.path.join(app_options["funcpath"], "Movement_Regressors.txt"))
        log.info("Selected file for movement confounds: %s", str(motion_path))

        app_options["confounds_file"] = motion_path[0]

    if app_options["dummy-scans"] > 0:

        # replace initial non-steady volumes with white noise
        app_options = replace_vols(gear_options, app_options)

        # get volume count from functional path
        cmd = "fslnvols " + app_options["func_file"]
        log.debug("\n %s", cmd)
        terminal = sp.Popen(
            cmd, shell=True, stdout=sp.PIPE, stderr=sp.PIPE, universal_newlines=True
        )
        stdout, stderr = terminal.communicate()
        log.debug("\n %s", stdout)
        log.debug("\n %s", stderr)

        nvols = int(stdout.strip("\n"))
        dummy_scans = app_options["dummy-scans"]

        arr = np.zeros([nvols, dummy_scans])

        for idx in range(0, dummy_scans):
            arr[idx][idx] = 1

        pd.DataFrame(arr).to_csv(os.path.join(app_options["funcpath"], 'dummyvols-confounds.txt'), sep=" ", index=False,
                                 header=False)

        if app_options["motion-confound"]:
            cmd = 'paste -d " " ' + os.path.join(app_options["funcpath"], 'dummyvols-confounds.txt') + ' ' + \
                  motion_path[0] + ' > ' + os.path.join(app_options["funcpath"], 'movement-dummyvols-confounds.txt')
            log.debug("\n %s", cmd)
            terminal = sp.Popen(
                cmd, shell=True, stdout=sp.PIPE, stderr=sp.PIPE, universal_newlines=True
            )
            stdout, stderr = terminal.communicate()
            log.debug("\n %s", stdout)
            log.debug("\n %s", stderr)

            app_options["confounds_file"] = os.path.join(app_options["funcpath"], 'movement-dummyvols-confounds.txt')

        else:
            app_options["confounds_file"] = os.path.join(app_options["funcpath"], 'dummyvols-confounds.txt')

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
    if app_options["icafix"]:
        funcfile = searchfiles(os.path.join(app_options["funcpath"], "*clean.nii.gz"))
        app_options["func_file"] = funcfile[0]
    else:
        funcfile = searchfiles(os.path.join(app_options["funcpath"], "*_bold.nii.gz"))
        app_options["func_file"] = funcfile[0]

    highresfile = searchfiles(os.path.join(app_options["structpath"], "T1w_restore_brain.nii.gz"))
    app_options["highres_file"] = highresfile[0]

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

    # for now, assume evs are bids format tsvs.... update this!!!

    outpath = os.path.join(app_options["funcpath"], "events")
    os.makedirs(outpath, exist_ok=True)

    evformat = "bids"
    if evformat == "bids":
        df = pd.read_csv(gear_options["event_files"], sep="\t")

        groups = df["trial_type"].unique()

        for g in groups:
            ev = df[df["trial_type"] == g]
            ev1 = ev.copy()
            ev1.loc[:, "weight"] = pd.Series([1 for x in range(len(df.index))])

            ev1 = ev1.drop(columns=["trial_type"])

            filename = os.path.join(outpath,
                                    os.path.basename(gear_options["event_files"]).replace(".tsv", "-" + g + ".txt"))
            ev1.to_csv(filename, sep=" ", index=False, header=False)

    app_options["event_dir"] = outpath

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

    design_file = os.path.join(gear_options["work-dir"], os.path.basename(gear_options["FSF_TEMPLATE"]))
    app_options["design_file"] = design_file

    shutil.copy(gear_options["FSF_TEMPLATE"], design_file)

    # add sed replace in template file for:
    # 1. output name
    if app_options["output-name"]:
        replace_line(design_file, r'set fmri\(outputdir\)', 'set fmri(outputdir) "' + os.path.join(gear_options["work-dir"], os.path.basename(app_options["output-name"])) + '"')

    # 2. func path
    replace_line(design_file, r'set feat_files\(1\)', 'set feat_files(1) "' + app_options["func_file"] + '"')

    # 3. total func length??
    cmd = "fslnvols " + app_options["func_file"]
    log.debug("\n %s", cmd)
    terminal = sp.Popen(
        cmd, shell=True, stdout=sp.PIPE, stderr=sp.PIPE, universal_newlines=True
    )
    stdout, stderr = terminal.communicate()
    nvols = stdout.strip("\n")
    replace_line(design_file, r'set fmri\(npts\)', 'set fmri(npts) ' + nvols)

    # TODO check registration consistency

    # 4. highres/standard -- don't use highres for HCPPipeline models!
    stdname = locate_by_pattern(design_file, r'set fmri\(regstandard\) "(.*)"')
    stdname = os.path.join(os.environ["FSLDIR"], "data", "standard", os.path.basename(stdname[0]))
    replace_line(design_file, r'set fmri\(regstandard\) ', 'set fmri(regstandard) "' + stdname + '"')

    # check confounds parser consistency...
    confound_yn = locate_by_pattern(design_file, r'set fmri\(confoundevs\) (.*)')
    if not confound_yn[0] and "confounds_file" in app_options:
        log.critical("Error: confounds file selected in gear options, but not set in FSF TEMPLATE")
    elif confound_yn[0] and "confounds_file" not in app_options:
        log.critical("Error: confounds file was not selected in gear options, but is set in FSF TEMPLATE")

    # 5. if confounds: confounds path
    if "confounds_file" in app_options:
        replace_line(design_file, r'set confoundev_files\(1\)',
                     'set confoundev_files(1) "' + app_options["confounds_file"] + '"')

    # 6. events - find events by event name in desgin file

    # locate all evtitle calls in template
    ev_numbers = locate_by_pattern(design_file, r'set fmri\(evtitle(\d+)')

    # for each ev, return name, find file pattern, it checks pass replace filename
    allfiles = []
    for num in ev_numbers:
        name = locate_by_pattern(design_file, r'set fmri\(evtitle' + num + '\) "(.*)"')
        evname = name[0]

        log.info("Located explanatory variable %s: %s", num, evname)

        evfiles = searchfiles(os.path.join(app_options["event_dir"], "*" + evname + "*"))

        if len(evfiles) > 1 or evfiles[0] == '':
            log.error("Problem locating event files programatically... check event names and re-run.")
        else:
            log.info("Found match... EV %s: %s", evname, evfiles[0])
            replace_line(design_file, r'set fmri\(custom' + num + '\)',
                         'set fmri(custom' + num + ') "' + evfiles[0] + '"')
            allfiles.append(evfiles[0])

    if allfiles:
        app_options["ev_files"] = allfiles

    return app_options


def replace_vols(gear_options: dict, app_options: dict):
    with tempfile.TemporaryDirectory(dir=gear_options["work-dir"]) as tmpdir:
        # 1. create a noise image
        img = nib.load(app_options["func_file"])
        noise = np.random.randn(img.shape[0], img.shape[1], img.shape[2], app_options["dummy-scans"])
        nim = nib.Nifti1Image(noise.astype('f'), img.affine, img.header)
        noise_fname = os.path.join(tmpdir, 'noise.nii.gz')
        nib.save(nim, noise_fname)

        # 2. from orginal image, create a trimmed series
        trim_fname = os.path.join(tmpdir, 'trimmed.nii.gz')
        cmd = "fslroi " + app_options["func_file"] + " " + trim_fname + " " + str(app_options["dummy-scans"]) + " -1"
        execute_shell(cmd, gear_options["dry-run"])

        # 3. using trimmed file, compute temporal mean
        tmean_fname = os.path.join(tmpdir, Path(app_options["func_file"]).name.replace(".nii.gz", "_meanfunc.nii.gz"))
        cmd = "fslmaths " + trim_fname + " -Tmean " + tmean_fname
        execute_shell(cmd, gear_options["dry-run"])

        # 4 remove temporal mean from trimmed datset
        demeaned_fname = os.path.join(tmpdir, 'trimmed_zerocenter.nii.gz')
        cmd = "fslmaths " + trim_fname + " -sub " + tmean_fname + " " + demeaned_fname + " -odt float"
        execute_shell(cmd, gear_options["dry-run"])

        # 5. concatenate adjusted noise model and trimmed timeseries
        output_zerocenter = os.path.join(tmpdir, Path(app_options["func_file"]).name.replace(".nii.gz", "_withnoise.nii.gz"))
        cmd = "fslmerge -t " + output_zerocenter + " " + noise_fname + " " + demeaned_fname
        execute_shell(cmd, gear_options["dry-run"])

        # 6. add temporal mean back to adjusted dataset
        final_output = app_options["func_file"].replace(".nii.gz", "_withnoise.nii.gz")
        cmd = "fslmaths " + output_zerocenter + " -add " + tmean_fname + " " + final_output
        execute_shell(cmd, gear_options["dry-run"])

        app_options["func_file"] = app_options["func_file"].replace(".nii.gz", "_withnoise.nii.gz")

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
    cmd.append(gear_options["feat"]["common_command"])
    cmd.append(app_options["design_file"])

    return cmd


def execute_shell(cmd, dryrun=False, cwd=os.getcwd()):
    log.info("\n %s", cmd)
    if not dryrun:
        terminal = sp.Popen(
            cmd,
            shell=True,
            stdout=sp.PIPE,
            stderr=sp.PIPE,
            universal_newlines=True,
            cwd=cwd
        )
        stdout, stderr = terminal.communicate()
        log.debug("\n %s", stdout)
        log.debug("\n %s", stderr)

        return stdout


def searchfiles(path, dryrun=False) -> list[str]:
    cmd = "ls -d " + path

    log.debug("\n %s", cmd)

    if not dryrun:
        terminal = sp.Popen(
            cmd, shell=True, stdout=sp.PIPE, stderr=sp.PIPE, universal_newlines=True
        )
        stdout, stderr = terminal.communicate()
        log.debug("\n %s", stdout)
        log.debug("\n %s", stderr)

        files = stdout.strip("\n").split("\n")
        return files


def sed_inplace(filename, pattern, repl):
    """
    Perform the pure-Python equivalent of in-place `sed` substitution: e.g.,
    `sed -i -e 's/'${pattern}'/'${repl}' "${filename}"`.
    """
    # For efficiency, precompile the passed regular expression.
    pattern_compiled = re.compile(pattern)

    # For portability, NamedTemporaryFile() defaults to mode "w+b" (i.e., binary
    # writing with updating). This is usually a good thing. In this case,
    # however, binary writing imposes non-trivial encoding constraints trivially
    # resolved by switching to text writing. Let's do that.
    with tempfile.NamedTemporaryFile(dir=os.getcwd(), mode='w', delete=False) as tmp_file:
        with open(filename) as src_file:
            for line in src_file:
                tmp_file.write(pattern_compiled.sub(repl, line))

    # Overwrite the original file with the munged temporary file in a
    # manner preserving file attributes (e.g., permissions).
    shutil.copystat(filename, tmp_file.name)
    shutil.move(tmp_file.name, filename)


def locate_by_pattern(filename, pattern):
    """
    Locates all instances that meet pattern and returns value from file.
    Args:
        filename: text file
        pattern: regex

    Returns:

    """
    # For efficiency, precompile the passed regular expression.
    pattern_compiled = re.compile(pattern)
    arr = []
    with open(filename) as src_file:
        for line in src_file:
            num = re.findall(pattern_compiled, line)
            if num:
                arr.append(num[0])

    return arr


def replace_line(filename, pattern, repl):
    """
        Perform the pure-Python equivalent of in-place `sed` substitution: e.g.,
        `sed -i -e 's/'${pattern}'/'${repl}' "${filename}"`.
        """
    # For efficiency, precompile the passed regular expression.
    pattern_compiled = re.compile(pattern)

    # For portability, NamedTemporaryFile() defaults to mode "w+b" (i.e., binary
    # writing with updating). This is usually a good thing. In this case,
    # however, binary writing imposes non-trivial encoding constraints trivially
    # resolved by switching to text writing. Let's do that.
    with tempfile.NamedTemporaryFile(dir=os.getcwd(), mode='w', delete=False) as tmp_file:
        with open(filename) as src_file:
            for line in src_file:
                if re.findall(pattern_compiled, line):
                    tmp_file.write(repl)
                else:
                    tmp_file.write(line)

    # Overwrite the original file with the munged temporary file in a
    # manner preserving file attributes (e.g., permissions).
    shutil.copystat(filename, tmp_file.name)
    shutil.move(tmp_file.name, filename)

