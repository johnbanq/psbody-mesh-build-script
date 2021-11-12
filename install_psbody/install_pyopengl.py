"""
installation script for pyopengl
handles windows unofficial install automatically as well
"""
import os
import subprocess


from infra import log, run


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