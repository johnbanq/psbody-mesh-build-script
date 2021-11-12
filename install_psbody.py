#!/usr/bin/env python
import argparse
import contextlib
import logging
import os
import re
import shutil
import subprocess
from logging import getLogger


# logger #


log = getLogger("install_psbody")


# global variables #


do_not_cleanup = False


# functions #


def run(*args, **kwargs):
    """
    utils for running subprocess.run,
    will remain slient until something when wrong
    """
    try:
        pipe_or_not = None if log.getEffectiveLevel() == logging.DEBUG else subprocess.PIPE
        subprocess.run(*args, **kwargs, check=True, stderr=pipe_or_not, stdout=pipe_or_not)

    except subprocess.CalledProcessError as e:
        log.error("error while executing: %s", str(e.args))
        log.error("stdout: \n%s", e.stdout.decode("UTF-8") if e.stdout else "None")
        log.error("stderr: \n%s", e.stderr.decode("UTF-8") if e.stderr else "None")
        raise e


def check_is_in_conda_environment():
    log.info("checking is in conda environment")
    prefix = os.getenv("CONDA_PREFIX")
    log.debug("content of prefix: %s", prefix)
    if prefix:
        log.info("it is!")
    else:
        log.fatal("cannot fetch environ CONDA_PREFIX, we are very likely not in a conda environment!")
        raise RuntimeError("cannot run the script outside a conda environment!")


@contextlib.contextmanager
def install_building_dependencies():
    dependencies = ["cxx-compiler", "setuptools", "libgomp"]
    dependencies_to_uninstall = list(set(dependencies) - {"setuptools", "libgomp"})

    log.info("installing compiling dependencies: %s", str(dependencies))
    run(["conda", "install", "-y", "-c", "conda-forge", *dependencies])
    try:
        yield
    finally:
        pass
        # note: it appears that removing cxx-compiler will break the install, so we had to keep it *shrug*
        # if not do_not_cleanup:
        #     log.info("removing compiling dependencies: %s", str(dependencies_to_uninstall))
        #     run(["conda", "uninstall", "-y", "-c", "conda-forge", *dependencies_to_uninstall])


def install_boost():
    log.info("installing boost")
    run(["conda", "install", "-y", "boost"])


def install_pyopengl():
    log.info("installing pyopengl")
    run(["pip", "install", "pyopengl"])


REPO_DIR = ".bqinstall.mpi-is.psbody-mesh"
REPO_URL = "https://github.com/johnbanq/mesh.git"
REPO_REVISION = "0d876727d5184161ed085bd3ef74967441b0a0e8"


@contextlib.contextmanager
def download_and_cd_into_repo():
    log.info("cloning the code")
    if os.path.exists(REPO_DIR):
        log.info("previous clone detected, removing it")
        shutil.rmtree(REPO_DIR)
    try:
        run(["git", "clone", REPO_URL, REPO_DIR])
        os.chdir(REPO_DIR)
        run(["git", "checkout", REPO_REVISION])
        yield
    finally:
        if not do_not_cleanup:
            shutil.rmtree(REPO_DIR, ignore_errors=True)


@contextlib.contextmanager
def with_upgraded_pip():
    result = subprocess.run(["pip", "list"], stdout=subprocess.PIPE, check=True)
    matches = [m for m in result.stdout.decode("UTF-8").splitlines()]
    matches = [re.match(r"pip +(?P<version>\S+\.\S+\.\S+)", m) for m in matches]
    matches = [m for m in matches if m]
    assert len(matches) == 1,\
        "there must be exactly one pip in listed installed packages, found %i!" % len(matches)
    version = matches[0].group("version").strip()

    log.debug("current pip version is %s, upgrading", version)

    run(["pip", "install", "--upgrade", "pip"])
    try:
        yield
    finally:
        log.debug("restoring pip version to %s", version)
        run(["pip", "install", "pip==%s" % version])


def build_install_package():
    """
    note:
        because for mysterious reason, we need latest pip to install dependencies,
        but need the old pip to run the setup.py
    hence the setup.py setup is out of the with scope
    """
    log.info("installing python dependencies")
    with with_upgraded_pip():
        run([
            "pip", "install",
            "--upgrade",
            "-r", "requirements.txt"
        ])

    log.info("running setup.py")
    boost_location = os.path.join(os.environ["CONDA_PREFIX"], "include")

    run([
        "pip", "install",
        "--no-deps",
        '--install-option=--boost-location=%s' % boost_location,
        "--verbose",
        "--no-cache-dir",
        "."
    ])


def test_package():
    log.info("running tests")
    run(["make", "tests"])


def main():
    check_is_in_conda_environment()

    with install_building_dependencies():
        install_boost()
        install_pyopengl()
        with download_and_cd_into_repo():
            build_install_package()

    test_package()

    log.info("installation complete!")


if __name__ == '__main__':
    # parse arguments #
    parser = argparse.ArgumentParser(description='psbody installation script')
    parser.add_argument(
        '--no-cleanup', action='store_true',
        help='do not cleanup the dependencies & files when exiting, helpful for debugging'
    )
    parser.add_argument(
        '--verbose', action='store_true',
        help='print debug log along the way'
    )
    args = parser.parse_args()

    # apply arguments #
    do_not_cleanup = args.no_cleanup
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    # run #
    main()
