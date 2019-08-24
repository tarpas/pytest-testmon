from setuptools import setup

setup(
    name='runtime-info',
    description='Python counterpart of a Pycharm plugin with the same name. https://plugins.jetbrains.com/plugin/11425-runtime-info',
    long_description='Python counterpart of a Pycharm plugin with the same name. https://plugins.jetbrains.com/plugin/11425-runtime-info',
    version='0.15.14',
    license='MIT',
    platforms=['linux', 'osx', 'win32'],
    packages=['runtime_info0'],
    author_email='tibor.arpas@infinit.sk',
    author='Tibor Arpas',
    entry_points={
        'pytest11': [
            'runtime_info0 = runtime_info0.pytest_runtime_info'
        ],
    },
    install_requires=['pytest>=4,<6'],
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
