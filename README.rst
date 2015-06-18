.. image:: https://secure.travis-ci.org/tarpas/pytest-testmon.png?branch=master
   :alt: Build Status
   :target: https://secure.travis-ci.org/tarpas/pytest-testmon.png


This is a py.test plug-in which automatically selects and re-executes only tests affected by recent changes. How is this possible in dynamic language like Python and how reliable is it? Read here: `Determining affected tests <https://github.com/tarpas/pytest-testmon/wiki/Determining-affected-tests>`_

New versions usually have new dataformat, don't forget to rm .testmondata after each upgrade.

testmon is approaching completeness. Unfortunatelly the classic console UI is reaching it's usability limits even without testmon.
With testmon it's even a little more difficult to determine which tests are beeing executed, which are failing and why.
Next step would be an implementation or integration of GUI. I don't like any  of the existing graphical test runners, so
if you have some better new concept in mind, get in touch!

Usage
=====

::

    pip install pytest-testmon

    # build the dependency database and save it to .testmondata
    py.test --testmon

    # list of watched project files ordered by tests which reach each specific file
    py.test --by-test-count

    # change some of your code (with test coverage)

    # only run tests affected by recent changes
    py.test --testmon

    # start from scratch (if needed)
    rm .testmondata

    # automatic re-execution on every file change with pytest-watch (https://github.com/joeyespo/pytest-watch)
    pip install pytest-watch
    ptw -- --testmon


Other switches
~~~~~~~~~~~~~~

**--project-directory=** only files in under this directory will be tracked by coveragepy. Default is rootdir, can be repeated

Configuration
=============
Add testmon to the pytest.ini

::

    [pytest]
    #if you want to separate different environments running the same sources
    run_variant_expression = os.environ.get('DJANGO_SETTINGS_MODULE') + ':python' + str(sys.version_info[:2])
    addopts = --testmon # you can make --testmon a default if you want


Thoughts
=============
Individual test outcomes depend on many things, so let's write a little about some of them.

#. executed python code inside the tested project (which presumably changes very frequently, little by little)

#. environment variables (e.g. DJANGO_SETTINGS_MODULE), python version (the run_variant_expression config value denotes these)

#. executed python code in all of the **libraries** (which presumably change infrequently)

#. **data files** (txt, xml, other project assets)

#. external services (reached through network)

**testmon** so far deals with incrementally running tests when faced with the 1. and 2. category of changes.

Later versions can implement some detection of other categories

**libraries**: we could compare pip freeze between runs, but it's slow

**data files**: Probably the best bet here is a configuration where the developer would specify which files does a test depend on

Sponsors
=============
Big thanks to Qvantel, `Nick Coghlan <http://www.curiousefficiency.org/>`_
,  `Abilian SAS <https://www.abilian.com/>`_ and `Infinit <http://www.infinit.sk>`_ for beeing silver sponsors of the first release of **testmon**. List of all contributors to our campaing is `here <https://www.indiegogo.com/projects/testmon#pledges>`_ . Thanks a lot to all contributors.