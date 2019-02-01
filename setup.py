from setuptools import setup

setup(
    name='runtime-info',
    description='TODO',
    long_description='TODO',
    version='0.15.10',
    license='MIT',
    platforms=['linux', 'osx', 'win32'],
    packages=['runtime_info0'],
    #url='https://github.com/tarpas/pytest-testmon/',
    author_email='tibor.arpas@infinit.sk',
    author='Tibor Arpas',
    entry_points={
        'pytest11': [
            'runtime_info0 = runtime_info0.pytest_runtime_info'
        ],
    },
    install_requires=['pytest>=3.3.0,<5'],
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
