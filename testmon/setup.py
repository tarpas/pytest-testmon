from setuptools import setup

setup(
    name='pytest-testmon',
    description='take TDD to a new level with py.test and testmon',
    long_description=''.join(open('../README.rst').readlines()),
    version='0.9.16',
    license='MIT',
    platforms=['linux', 'osx', 'win32'],
    
    url='https://github.com/tarpas/pytest-testmon/',
    author_email='tibor.arpas@infinit.sk',
    author='Tibor Arpas, Jozef Knaperek, Martin Riesz, Daniel Hahler',
    entry_points={
        'pytest11': [
            'testmon = pytest_testmon',
        ],
        'tox': [
            'testmon = tox_testmon',
        ],
    },
    install_requires=['pytest>=5,<6', 'coverage>=4'],
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
