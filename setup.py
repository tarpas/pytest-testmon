import codecs
import os

from setuptools import setup

with codecs.open("README.md", "r", "utf-8") as fh:
    long_description = fh.read()

CURRENT_SCM_PRETEND_VERSION = os.environ.get("SETUPTOOLS_SCM_PRETEND_VERSION")
if CURRENT_SCM_PRETEND_VERSION is not None:
    os.environ["SETUPTOOLS_SCM_PRETEND_VERSION"] = f"{CURRENT_SCM_PRETEND_VERSION}+dr"


setup(
    name="pytest-testmon",
    description="selects tests affected by changed files and methods",
    long_description=long_description,
    license="AGPL",
    platforms=["linux", "osx", "win32"],
    packages=["testmon"],
    url="https://testmon.org",
    author_email="tibor.arpas@infinit.sk",
    author="Tibor Arpas, Tomas Matlovic, Daniel Hahler, Martin Racak",
    entry_points={
        "pytest11": [
            "testmon = testmon.pytest_testmon",
        ],
        "tox": [
            "testmon = testmon.tox_testmon",
        ],
    },
    install_requires=["pytest>=7,<8", "coverage>=4,<6"],
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Operating System :: POSIX",
        "Operating System :: Microsoft :: Windows",
        "Operating System :: MacOS :: MacOS X",
        "Topic :: Software Development :: Testing",
        "Topic :: Software Development :: Libraries",
        "Topic :: Utilities",
        "Programming Language :: Python",
    ],
    setup_requires=["setuptools-scm==5.0.2", "wheel"],
    python_requires=">=3.7",
    use_scm_version=dict(version_scheme="python-simplified-semver", local_scheme="no-local-version"),
)
