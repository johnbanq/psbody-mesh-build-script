#!/usr/bin/env python
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


# infrastructure #


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
    global do_not_cleanup

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
        '--environment', type=str, default="prepare_environment",
        help='INTERNAL FLAG: DO NOT TOUCH, used to indicate reactivated environment'
    )
    args = parser.parse_args()

    # apply arguments #
    do_not_cleanup = args.no_cleanup
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    # main #
    if args.environment == "prepare_environment":
        env_name = detect_conda_environment()
        log.debug("setting up prepare_environment")
        with prepare_environment():
            run_with_reactivated_environment(env_name, ["python", *sys.argv, "--environment", "execute_build"])
            log.debug("tearing down prepare_environment")
        run_with_reactivated_environment(env_name, ["python", *sys.argv, "--environment", "validate_build"])
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

    try:
        result = subprocess.run(["conda", "info"], stdout=subprocess.PIPE, check=True)
    except subprocess.CalledProcessError as e:
        log.fatal("could not run conda info, do you have conda installed at all?")
        raise e

    lines = result.stdout.decode(encoding=sys.getdefaultencoding()).splitlines()
    lines = [re.match("active environment : (?P<environment>.*)", line.strip()) for line in lines]
    lines = [line for line in lines if line]
    assert len(lines) == 1, "exactly 1 active environment line expected, but got %i !" % len(lines)
    env_name = lines[0].group("environment").strip()

    log.debug("detected environment name: %s", env_name)

    if env_name == "None":
        log.fatal("you are not in a conda environment! Try conda activate base to enter the base environment!")
        raise RuntimeError("cannot run the script outside a conda environment!")
    else:
        log.info("detected environment: %s", env_name)
        return env_name


def run_with_reactivated_environment(env_name: str, commands: List[str]):
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

            script = "conda activate %s" % env_name
            if os.name == "nt":
                script = "@" + script + os.linesep + "if errorlevel 1 exit 1"

            log.debug("activate script: %s", script)
            f.write(script + os.linesep)

            command = " ".join(commands)
            if os.name == "nt":
                command = command + os.linesep + "if errorlevel 1 exit 1"

            log.debug("command: %s", command)
            f.write(command + os.linesep)

        # run script #
        log.debug("jumping into the trampoline, wee!")
        if os.name == "nt":
            run([script_name])
        else:
            run(["chmod", "+x", script_name])
            run(["./" + script_name])
    finally:
        if not do_not_cleanup and os.path.exists(script_name):
            os.unlink(script_name)


def run(*args, **kwargs):
    """
    utils for running subprocess.run,
    will remain silent until something when wrong
    """
    try:
        pipe_or_not = None if log.getEffectiveLevel() == logging.DEBUG else subprocess.PIPE
        subprocess.run(*args, **kwargs, check=True, stderr=pipe_or_not, stdout=pipe_or_not, shell=True)

    except subprocess.CalledProcessError as e:
        log.error("error while executing: %s", str(e.args))
        log.error("stdout: \n%s", e.stdout.decode("UTF-8") if e.stdout else "None")
        log.error("stderr: \n%s", e.stderr.decode("UTF-8") if e.stderr else "None")
        raise e


@contextlib.contextmanager
def inside_git_repository(repo_url, repo_hash=None, dir_name=".bqinstall.repo"):
    """
    clone a git repo into the specified directory and cd into it, then cleanup on exit
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

    yield

    os.chdir("..")
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


# preparing environment #


REPO_URL = "https://github.com/johnbanq/mesh.git"
REPO_REVISION = "0d876727d5184161ed085bd3ef74967441b0a0e8"
REPO_DIR = ".bqinstall.mpi-is.mesh"


@contextlib.contextmanager
def psbody_prepare_environment():
    with inside_git_repository(repo_url=REPO_URL, repo_hash=REPO_REVISION, dir_name=REPO_DIR):
        with install_compiling_dependencies():
            install_boost()
            install_pyopengl()
            yield


@contextlib.contextmanager
def install_compiling_dependencies():
    # note: we obviously can't remove setuptools as python depeneds on it
    # note: we also can't remove cxx-compiler as it causes regression
    # so no teardown logic
    dependencies = ["cxx-compiler", "setuptools"]

    log.info("installing compiling dependencies: %s", str(dependencies))
    run(["conda", "install", "-y", "-c", "conda-forge", *dependencies])

    yield


def install_boost():
    log.info("installing boost")
    run(["conda", "install", "-y", "boost"])


def install_pyopengl():
    log.info("installing pyopengl")
    run(["pip", "install", "pyopengl"])


# execute build #


def psbody_execute_build():
    # note: because of mysterious reason, we need latest pip to install dependencies,
    #     but need the old pip to run the setup.py
    #     hence the setup.py setup is out of the with scope
    log.info("installing python dependencies")
    with with_upgraded_pip():
        run([
            "pip", "install",
            "--upgrade",
            "-r", "requirements.txt"
        ])

    log.info("running setup.py")
    if os.name == "nt":
        boost_location = os.path.join(os.environ["CONDA_PREFIX"], "Library", "include")
    else:
        boost_location = os.path.join(os.environ["CONDA_PREFIX"], "include")
    run([
        "pip", "install",
        "--no-deps",
        '--install-option=--boost-location=%s' % boost_location,
        "--verbose",
        "--no-cache-dir",
        "."
    ])


@contextlib.contextmanager
def with_upgraded_pip():
    result = subprocess.run(["pip", "list"], stdout=subprocess.PIPE, check=True)
    matches = [m for m in result.stdout.decode("UTF-8").splitlines()]
    matches = [re.match(r"pip +(?P<version>\S+\.\S+\.\S+)", m) for m in matches]
    matches = [m for m in matches if m]
    assert len(matches) == 1, \
        "there must be exactly one pip in listed installed packages, found %i!" % len(matches)
    version = matches[0].group("version").strip()

    log.debug("current pip version is %s, upgrading", version)

    run(["pip", "install", "--upgrade", "pip"])
    try:
        yield
    finally:
        log.debug("restoring pip version to %s", version)
        run(["pip", "install", "pip==%s" % version])


# run tests #


def psbody_validate_build():
    with inside_git_repository(repo_url=REPO_URL, repo_hash=REPO_REVISION, dir_name=REPO_DIR):
        log.info("running tests")
        if os.name == "nt":
            run(["python", "-m", "unittest", "-v"])
        else:
            run(["make", "tests"])
        log.info("all test passed, installation successful!")


# main #

if __name__ == '__main__':
    install_script_main(
        package_name="psbody",
        prepare_environment=psbody_prepare_environment,
        execute_build=psbody_execute_build,
        validate_build=psbody_validate_build
    )
