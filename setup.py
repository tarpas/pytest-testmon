from setuptools import setup

setup(
    name='pytest-testmon',
    description='take TDD to a new level with py.test and testmon',
    long_description=''.join(open('README.rst').readlines()),
    version='0.8.3',
    license='MIT',
    platforms=['linux', 'osx', 'win32'],
    packages=['testmon'],
    url='https://github.com/tarpas/pytest-testmon/',
    author_email='tibor.arpas@infinit.sk',
    author='Tibor Arpas, Jozef Knaperek, Martin Riesz',
    entry_points={
        'pytest11': [
            'testmon = testmon.pytest_testmon',
        ]
    },
    install_requires=['pytest>=2.7.0,<3.1', 'coverage>=4'],
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
