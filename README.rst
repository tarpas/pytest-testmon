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

P.S.
----

The code is a result of stripping down a lot of exploratory code
originating from researching possibilities and techniques. We're aware
of many of its deficiencies. Speed-up, reshuffling, clean-up, fancy
dependency graph output, unit tests, py.test 2.7, python 3+, proper
directory omitting, dependent packages upgrades detection, field-tested
bugs. We'll start doing and publishing all that full-force once the
campaign is successful.
