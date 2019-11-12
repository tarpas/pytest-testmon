from setuptools import setup

setup(
    name='pytest-testmon',
    description='automatically selects tests affected by changed files and methods',
    long_description='TODO',
    version='1.0.0a4',
    license='AGPL',
    platforms=['linux', 'osx', 'win32'],
    packages=['testmon'],
    url='https://testmon.org',
    author_email='tibor.arpas@infinit.sk',
    author='Tibor Arpas, Daniel Hahler, Tomas Matlovic, Martin Racak',
    entry_points={
        'pytest11': [
            'testmon = testmon.pytest_testmon',
        ],
        'tox': [
            'testmon = testmon.tox_testmon',
        ],
    },
    install_requires=['pytest>=5,<6', 'coverage>=4,<5'],
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Operating System :: POSIX',
        'Operating System :: Microsoft :: Windows',
        'Operating System :: MacOS :: MacOS X',
        'Topic :: Software Development :: Testing',
        'Topic :: Software Development :: Libraries',
        'Topic :: Utilities',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3 :: Only'],
)
