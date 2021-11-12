#!/usr/bin/env python
import contextlib
import os
import shutil


from infra import log, install_script_main, run, inside_git_repository, with_upgraded_pip, \
    get_do_not_cleanup
from install_pyopengl import install_pyopengl


# preparing environment #


REPO_URL = "https://github.com/johnbanq/mesh.git"
REPO_REVISION = "0d876727d5184161ed085bd3ef74967441b0a0e8"
REPO_DIR = ".bqinstall.mpi-is.mesh"


@contextlib.contextmanager
def psbody_prepare_environment():
    with inside_git_repository(
            repo_url=REPO_URL, repo_hash=REPO_REVISION, dir_name=REPO_DIR,
            cleanup=not get_do_not_cleanup()
    ):
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


# run tests #


def psbody_validate_build():
    log.info("running tests")
    with inside_git_repository(
            repo_url=REPO_URL, repo_hash=REPO_REVISION, dir_name=REPO_DIR,
            cleanup=not get_do_not_cleanup()
    ):
        # fix the stupid CRLF issue
        shutil.rmtree("data")
        run(["git", "checkout", "data"])

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
