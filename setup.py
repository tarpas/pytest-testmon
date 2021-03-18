from setuptools import setup


long_description = "".join(open("README.rst").readlines())


setup(
    name="pytest-testmon",
    description="selects tests affected by changed files and methods",
    long_description=long_description,
    version="1.1.0",
    license="AGPL",
    platforms=["linux", "osx", "win32"],
    packages=[
        "testmon",
    ],
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
    python_requires=">=3.6",
    install_requires=["pytest>=5,<7", "coverage>=4,<6"],
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
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3 :: Only",
    ],
)
