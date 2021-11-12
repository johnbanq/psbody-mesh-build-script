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

yes_everything = False


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


# preparing environment #


REPO_URL = "https://github.com/johnbanq/mesh.git"
REPO_REVISION = "0d876727d5184161ed085bd3ef74967441b0a0e8"
REPO_DIR = ".bqinstall.mpi-is.mesh"


@contextlib.contextmanager
def psbody_prepare_environment():
    with inside_git_repository(
            repo_url=REPO_URL, repo_hash=REPO_REVISION, dir_name=REPO_DIR,
            cleanup=not do_not_cleanup
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


def install_pyopengl():
    log.info("installing pyopengl")
    if os.name == "nt":
        log.info("running windows, installing from https://www.lfd.uci.edu/~gohlke/pythonlibs/")
        if get_pyopengl_version():
            log.warning("pyopengl is already installed in this environment, skipping")
            log.warning("note: MeshViewer will not work if this is not the one in the link above!")
            return

        version, (gl_link, accel_link) = fetch_version_and_links()
        log.info("installing version %s", version)
        run(["pip", "install", gl_link])
        run(["pip", "install", accel_link])
    else:
        run(["pip", "install", "pyopengl"])


def fetch_version_and_links():
    """
    returns the selected version and links (version, (pyopengl_link), (accelerate_link))
    :rtype: Tuple[str, Tuple[str, str]]
    """
    # TODO: build a proper fetching logic for it
    pyopengl_versions = [
        ('PyOpenGL‑3.1.5‑pp37‑pypy37_pp73‑win_amd64.whl', 'PyOpenGL_accelerate‑3.1.5‑pp37‑pypy37_pp73‑win_amd64.whl'),
        ('PyOpenGL‑3.1.5‑cp310‑cp310‑win_amd64.whl', 'PyOpenGL_accelerate‑3.1.5‑cp310‑cp310‑win_amd64.whl'),
        ('PyOpenGL‑3.1.5‑cp310‑cp310‑win32.whl', 'PyOpenGL_accelerate‑3.1.5‑cp310‑cp310‑win32.whl'),
        ('PyOpenGL‑3.1.5‑cp39‑cp39‑win_amd64.whl', 'PyOpenGL_accelerate‑3.1.5‑cp39‑cp39‑win_amd64.whl'),
        ('PyOpenGL‑3.1.5‑cp39‑cp39‑win32.whl', 'PyOpenGL_accelerate‑3.1.5‑cp39‑cp39‑win32.whl'),
        ('PyOpenGL‑3.1.5‑cp38‑cp38‑win_amd64.whl', 'PyOpenGL_accelerate‑3.1.5‑cp38‑cp38‑win_amd64.whl'),
        ('PyOpenGL‑3.1.5‑cp38‑cp38‑win32.whl', 'PyOpenGL_accelerate‑3.1.5‑cp38‑cp38‑win32.whl'),
        ('PyOpenGL‑3.1.5‑cp37‑cp37m‑win_amd64.whl', 'PyOpenGL_accelerate‑3.1.5‑cp37‑cp37m‑win_amd64.whl'),
        ('PyOpenGL‑3.1.5‑cp37‑cp37m‑win32.whl', 'PyOpenGL_accelerate‑3.1.5‑cp37‑cp37m‑win32.whl'),
        ('PyOpenGL‑3.1.5‑cp36‑cp36m‑win_amd64.whl', 'PyOpenGL_accelerate‑3.1.5‑cp36‑cp36m‑win_amd64.whl'),
        ('PyOpenGL‑3.1.5‑cp36‑cp36m‑win32.whl', 'PyOpenGL_accelerate‑3.1.5‑cp36‑cp36m‑win32.whl'),
        ('PyOpenGL‑3.1.5‑cp35‑cp35m‑win_amd64.whl', 'PyOpenGL_accelerate‑3.1.5‑cp35‑cp35m‑win_amd64.whl'),
        ('PyOpenGL‑3.1.5‑cp35‑cp35m‑win32.whl', 'PyOpenGL_accelerate‑3.1.5‑cp35‑cp35m‑win32.whl'),
        ('PyOpenGL‑3.1.5‑cp27‑cp27m‑win_amd64.whl', 'PyOpenGL_accelerate‑3.1.5‑cp27‑cp27m‑win_amd64.whl'),
        ('PyOpenGL‑3.1.5‑cp27‑cp27m‑win32.whl', 'PyOpenGL_accelerate‑3.1.5‑cp27‑cp27m‑win32.whl'),
        ('PyOpenGL‑3.1.3b2‑cp34‑cp34m‑win_amd64.whl', 'PyOpenGL_accelerate‑3.1.3b2‑cp34‑cp34m‑win_amd64.whl'),
        ('PyOpenGL‑3.1.3b2‑cp34‑cp34m‑win32.whl', 'PyOpenGL_accelerate‑3.1.3b2‑cp34‑cp34m‑win32.whl')
    ]

    # figure out a version we can use
    supported_tags = set(get_compatible_tags())

    selected_version = None
    selected_fullnames = None
    for fullname, accel_fullname in pyopengl_versions:
        name, version, *tags = fullname[:-len(".whl")].split("‑")
        accel_name, accel_version, *accel_tags = accel_fullname[:-len(".whl")].split("‑")
        assert tags == accel_tags  # already manually checked, but just in case

        tags = tuple(tags)
        if tags in supported_tags:
            selected_version = version
            selected_fullnames = fullname, accel_fullname
            break

    else:
        log.fatal("cannot find compatible unofficial windows binaries!")
        raise ValueError("could not find installable version!")

    log.debug("selected version: %s, fullnames: %s", str(selected_version), str(selected_fullnames))

    if "‑cp36‑" in selected_fullnames[0]:
        download_template = "https://download.lfd.uci.edu/pythonlibs/w6tyco5e/cp36/%s"
    elif "‑cp35‑" in selected_fullnames[0]:
        download_template = "https://download.lfd.uci.edu/pythonlibs/w6tyco5e/cp35/%s"
    else:
        download_template = "https://download.lfd.uci.edu/pythonlibs/w6tyco5e/%s"
    return (
        version,
        (
            download_template % selected_fullnames[0].replace("‑", "-"),
            download_template % selected_fullnames[1].replace("‑", "-"),
        )
    )


def get_pyopengl_version():
    """
    get version of pyopengl installed, None if not
    """
    try:
        # right way to do it
        import importlib.metadata
        try:
            return importlib.metadata.version("PyOpenGL")
        except importlib.metadata.PackageNotFoundError:
            return None
    except ImportError:
        # hacks
        try:
            from pip._internal.utils.misc import get_installed_distributions
        except ImportError:  # pip<10
            from pip import get_installed_distributions

        installed_packages = get_installed_distributions()
        installed_packages_list = sorted(["%s==%s" % (i.key, i.version) for i in installed_packages])

        for pkg in installed_packages_list:
            if pkg.lower().startswith("pyopengl=="):
                return pkg[len("pyopengl=="):]
        else:
            return None


def get_compatible_tags():
    try:
        # pip 10 compatibility
        from pip._internal.pep425tags import get_supported
        return get_supported()
    except ImportError:
        result = run(["python", "-m", "pip", "debug", "--verbose"], stdout=subprocess.PIPE)

        lines = result.stdout.decode("UTF-8").splitlines()
        while not lines[0].startswith("Compatible tags:"):
            lines.pop(0)
        assert len(lines) > 1, "there must be at least 1 compatible tags!"
        lines.pop(0)

        result = []
        for line in lines:
            line = line.strip()
            if line:
                result.append(tuple(line.split("-")))

        return result

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
    def enhance_on_win(lst):
        if os.name == "nt":
            # to let anaconda uninstall for us
            lst.insert(-2, "--user")
        return lst

    run(enhance_on_win(["python", "-m", "pip", "install", "--upgrade", "pip"]))

    yield

# run tests #


def psbody_validate_build():
    log.info("running tests")
    with inside_git_repository(
            repo_url=REPO_URL, repo_hash=REPO_REVISION, dir_name=REPO_DIR,
            cleanup=not do_not_cleanup
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
