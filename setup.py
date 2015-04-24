from setuptools import setup

setup(
    name='testmon',
    description='take TDD to a new level with py.test and testmon',
    version='0.2.9',
    license='MIT',
    platforms=['linux', 'osx', 'win32'],
    packages=['testmon'],
    py_module=['sitecustomize.py'],
    scripts=['testmon/tmon.py'],
    url='https://github.com/tarpas/testmon/',
    author_email='tibor.arpas@infinit.sk',
    author='Tibor Arpas, Jozef Knaperek, Martin Riesz',
    data_files=([('', ['README.rst']), ]),
    entry_points={
        'pytest11': [
            'testmon = testmon.pytest_testmon',
        ]
    },
    install_requires=['pytest>=2.7.0,<2.8', 'pytest-cache>=1.0', 'watchdog>=0.8',
                      'coverage>=3.7.1,<4.0', 'coverage_pth'],
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Operating System :: POSIX',
        'Operating System :: Microsoft :: Windows',
        'Operating System :: MacOS :: MacOS X',
        'Topic :: Software Development :: Testing',
        'Topic :: Software Development :: Libraries',
        'Topic :: Utilities',
        'Programming Language :: Python', ],
)
