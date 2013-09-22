from setuptools import setup

setup(
    name='testmon',
    description='Test Runner for Python',
    version='0.1.1a2',
    license='MIT',
    platforms=['linux', 'osx', 'win32'],
    packages=['testmon'],
    scripts=['testmon/tmon.py'],
    url='http://igg.me/at/testmon',
    author_email='tibor.arpas@infinit.sk',
    author='Tibor Arpas, Jozef Knaperek, Martin Riesz',
    data_files=([('', ['README.md']), ]),
    entry_points={
        'pytest11': [
            'testmon = testmon.plugin',
        ]
    },
    install_requires=['pytest<2.7', 'pytest-cache>=1.0', 'watchdog>=0.8'],
    setup_requires=['setuptools-markdown'],
    long_description_markdown_filename='README.md',
    classifiers=[
            'Development Status :: 3 - Alpha',
            'Intended Audience :: Developers',
            'Operating System :: POSIX',
            'Operating System :: Microsoft :: Windows',
            'Operating System :: MacOS :: MacOS X',
            'Topic :: Software Development :: Testing',
            'Topic :: Software Development :: Libraries',
            'Topic :: Utilities',
            'Programming Language :: Python', ],
)
