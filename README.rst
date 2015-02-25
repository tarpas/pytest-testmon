This is a semi-functional sneak peak into http://igg.me/at/testmon -
"Make your Python tests a breeze to execute"

Usage
-----

install via:

::

    git clone https://github.com/tarpas/testmon.git
    pip install -e testmon/

It's a py.test plugin so you need to have a test suite which py.test can
run (should be most test suites after minor adjustments). It adds
--testmon switch to py.test and also a simple watchdog command for file
changes in a directory tree: 'tmon.py'

::

    cd testmon/exampleproject/
    PYTHONPATH=.. tmon.py

In a separate shell

::

    py.test --by-test-count # list of watched project files ordered by 
                            # tests which reach each specific file
    touch b.py # testmon/exampleproject/b.py    

Try with readthedocs.org
------------------------

Example on how to use testmon with a sample django project.

::

    git clone https://github.com/rtfd/readthedocs.org.git 
    (cd readthedocs.org/; git reset --hard 5434369edf8834d9fe4)

    mkvirtualenv readthedocs
    pip install -e testmon
    pip install -e readthedocs.org
    cd readthedocs.org
    pip install -r pip_requirements.txt
    cd readthedocs
    #on mac you have to do
    export LC_ALL=en_US.UTF-8
    export LANG=en_US.UTF-8
    PYTHONPATH=.:$PYTHONPATH DJANGO_SETTINGS_MODULE=settings.test tmon.py

Then edit doc\_builder/environments.py and watch.

Try with whoosh
---------------

Another example on a somewhat computationally intensive project. Not
using tmon.py but periodically running py.test --testmon .

::

    hg clone https://bitbucket.org/mchaput/whoosh
    cd whoosh
    hg update 2.5.x

    py.test --testmon # one test failing

    hg update 999cd5f # some changes, 2 tests failing
    py.test --testmon

TODO
----

Speed-up, reshuffling, clean-up, fancy
dependency graph output, more coverage, py.test 2.7, proper
directory omitting, dependent packages upgrades detection, fixing edge cases
after more projects use testmon. We'll start doing and publishing all that full-force 
once the campaign is successful.

Thoughts
--------
Individual test outcomes depend on many things, but let's write a little about some of them. 

1. 'covered' python code inside the tested project (which presumably changes very frequently, little by little)
2. 'covered' python code in all of the libraries (which presumably change infrequently)
3. data files (txt, xml, other project assets)  
4. environment variables (e.g. DJANGO_SETTINGS_MODULE)

This alpha version deals with incrementally running tests when faced with the 1. category of changes.

Later versions can implement some detection of other categories

2. libraries: It's possible to store modification times of directories and files in sys.path and force a full re-execution of tests in case of change
3. Probably the best bet here is a configuration where the developer would specify which files does a test depend on
4. environemnt variable (DJANGO_SETTINGS_MODULE is a good example and we plan to implement change tracking here)   


