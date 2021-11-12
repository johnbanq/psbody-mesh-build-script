"""
infrastructure functions, should be more applicable than this script
"""
import argparse
import contextlib
import logging
import os
import re
import shutil
import stat
import subprocess
import sys
from logging import getLogger
from typing import List


# global variables #


log = getLogger("install_script")
do_not_cleanup = False
yes_everything = False


# functions #


def get_do_not_cleanup():
    return do_not_cleanup


def install_script_main(
        package_name,
        prepare_environment,
        execute_build,
        validate_build
):
    """
    entry point(main function) of the entire build script.

    this function accepts:
    * a context managers function: prepare_environment
    * a function: execute_build
    * a function: validate_build

    ideally, you should:
    * put git clone & dependency install in prepare_environment
    * put build logic in execute_build
    * put tests in validate_build

    the build process is structured as follows:
    * detect conda environment
    * run prepare_environment()
    *     re-activate conda environment to refresh environment variables
    *     run execute_build()
    * run cleanup in prepare_environment()
    *     re-activate conda environment to refresh environment variables
    *     run validate_build()

    note: the re-activation sequence is used to give conda a chance to update all the environs
    note: and it is done by using a trampoline script,
    note: and indicating its in reactivated environment by additional environment
    """
    global do_not_cleanup, yes_everything

    # parse arguments #
    parser = argparse.ArgumentParser(description='%s installation script' % package_name)

    parser.add_argument(
        '--no-cleanup', action='store_true',
        help='do not cleanup the dependencies & files when exiting, helpful for debugging'
    )
    parser.add_argument(
        '--verbose', action='store_true',
        help='print debug log along the way'
    )
    parser.add_argument(
        '--yes', action='store_true',
        help='say yes to all options in the install'
    )
    parser.add_argument(
        '--environment', type=str, default="prepare_environment",
        help='INTERNAL FLAG: DO NOT TOUCH, used to indicate reactivated environment'
    )
    args = parser.parse_args()

    # apply arguments #
    do_not_cleanup = args.no_cleanup
    yes_everything = args.yes
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    script_path = os.path.abspath(__file__)
    segments = os.path.normpath(script_path).split(os.path.sep)
    has_pyz = any([s.endswith(".pyz") for s in segments])
    if has_pyz:
        # because os.path treats C:// as 'C:', '', concat segments will lead to wrong path!
        while not segments[-1].endswith(".pyz"):
            script_path = os.path.dirname(script_path)
            segments.pop()

    # main #
    if args.environment == "prepare_environment":
        env_name = detect_conda_environment()
        log.debug("setting up prepare_environment")
        with prepare_environment():
            run_with_reactivated_environment(
                env_name, [
                    "python", script_path,
                    *sys.argv[1:], "--environment", "execute_build"
                ],
                cleanup=not do_not_cleanup
            )
            log.debug("tearing down prepare_environment")
        run_with_reactivated_environment(
            env_name, [
                "python", script_path,
                *sys.argv[1:], "--environment", "validate_build"
            ],
            cleanup=not do_not_cleanup
        )
    elif args.environment == "execute_build":
        log.debug("running execute_build")
        execute_build()
    elif args.environment == "validate_build":
        log.debug("running validate_build")
        validate_build()


def detect_conda_environment():
    """
    detect the current conda environment, and return its name
    """
    log.info("detecting conda environment")

    env_name = parse_conda_info("active environment")
    log.debug("detected environment name: %s", env_name)

    if env_name == "None":
        log.fatal("you are not in a conda environment! Try conda activate base to enter the base environment!")
        raise RuntimeError("cannot run the script outside a conda environment!")
    else:
        log.info("detected environment: %s", env_name)
        return env_name


def detect_conda_activate_script():
    log.debug("detecting conda activation script location")

    base_folder = parse_conda_info("base environment")
    if base_folder.endswith(")"):
        base_folder = base_folder[:base_folder.rfind("(")]
    base_folder = base_folder.strip()

    if os.name != "nt":
        script = os.path.join(base_folder, "bin", "activate")
    else:
        script = os.path.join(base_folder, "Scripts", "activate.bat")
    log.debug("detected: %s", script)

    return script


def parse_conda_info(key: str):
    """
    parse value of a key in output of conda info
    :rtype: str
    """
    try:
        result = run(["conda", "info"], stdout=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        log.fatal("could not run conda info, do you have conda installed?")
        raise e

    lines = result.stdout.decode(encoding=sys.getdefaultencoding()).splitlines()
    lines = [re.match("%s +: +(?P<value>.*)" % key, line.strip()) for line in lines]
    lines = [line for line in lines if line]
    assert len(lines) == 1, "exactly 1 %s line expected, but got %i !" % (key, len(lines))
    value = lines[0].group("value").strip()

    return value


TRAMPOLINE_SCRIPT_WINDOWS = """\
@echo off
@call %(activate_script_path)s %(environment)s
if errorlevel 1 exit 1

%(command)s
if errorlevel 1 exit 1
"""
TRAMPOLINE_SCRIPT_BASH = """\
#!/usr/bin/env bash
source %(activate_script_path)s %(environment)s
%(command)s
"""


def run_with_reactivated_environment(env_name: str, commands: List[str], cleanup=True):
    """
    run with re-activated conda environment
    """
    if os.name == "nt":
        script_name = ".bqinstall.trampoline.bat"
    else:
        script_name = ".bqinstall.trampoline.sh"

    try:
        # write script #
        with open(script_name, "w") as f:
            log.debug("writing trampoline script: %s", f.name)
            template = TRAMPOLINE_SCRIPT_WINDOWS if os.name == "nt" else TRAMPOLINE_SCRIPT_BASH
            template = template % {
                "activate_script_path": detect_conda_activate_script(),
                "environment": env_name,
                "command": (" ".join(commands))
            }
            for line in template.splitlines():
                line = line.strip()
                f.write(line+os.linesep)

        # run script #
        log.debug("jumping into the trampoline, wee!")
        if os.name == "nt":
            run([script_name], stdout=None, stderr=None)  # force stdout & stderr
        else:
            run(["chmod", "+x", script_name])
            run(["./" + script_name], stdout=None, stderr=None)  # force stdout & stderr
    finally:
        if cleanup and os.path.exists(script_name):
            os.unlink(script_name)


def run(*args, **kwargs):
    """
    utils for running subprocess.run,
    will remain silent until something when wrong
    note: will auto enable shell on windows as most commands seems
    to require it to function
    """
    try:
        # enable shell on windows
        if os.name == "nt":
            kwargs["shell"] = True

        # override-able stdout/stderr config
        normal_pipe_or_not = None if log.getEffectiveLevel() == logging.DEBUG else subprocess.PIPE
        kwargs["stdout"] = kwargs.get("stdout", normal_pipe_or_not)
        kwargs["stderr"] = kwargs.get("stderr", normal_pipe_or_not)
        return subprocess.run(*args, **kwargs, check=True)

    except subprocess.CalledProcessError as e:
        log.error("error while executing: %s", str(e.args))
        log.error("stdout: \n%s", e.stdout.decode("UTF-8") if e.stdout else "None")
        log.error("stderr: \n%s", e.stderr.decode("UTF-8") if e.stderr else "None")
        raise e


@contextlib.contextmanager
def inside_git_repository(repo_url, repo_hash=None, dir_name=".bqinstall.repo", cleanup=True):
    """
    clone a git repo into the specified directory and cd into it, then cleanup on exit
    :type cleanup: bool
    :type dir_name: str
    :type repo_url: str
    :type repo_hash: str | None
    """
    if os.path.exists(dir_name):
        log.debug("path exists, removing it")
        rmtree_git_repo(dir_name)

    run(["git", "clone", repo_url, dir_name])
    os.chdir(dir_name)
    run(["git", "checkout", repo_hash if repo_hash else ""])

    try:
        yield
    finally:
        os.chdir("..")
        if cleanup:
            rmtree_git_repo(dir_name)


def rmtree_git_repo(dirpath: str):
    # note: because you can't programmatically delete .git on windows in the naive way
    # see: https://my.oschina.net/hechunc/blog/3078597
    def readonly_handler(func, path, execinfo):
        exc, exc_inst, _ = execinfo
        if os.name == "nt" and isinstance(exc_inst, PermissionError) and exc_inst.args[0] == 13:
            os.chmod(path, stat.S_IWRITE)
            func(path)
        else:
            raise

    shutil.rmtree(dirpath, onerror=readonly_handler)


@contextlib.contextmanager
def with_upgraded_pip():
    def enhance_on_win(lst):
        if os.name == "nt":
            # to let anaconda uninstall for us
            lst.insert(-2, "--user")
        return lst

    run(enhance_on_win(["python", "-m", "pip", "install", "--upgrade", "pip"]))

    yield