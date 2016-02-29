.. image:: https://secure.travis-ci.org/tarpas/pytest-testmon.png?branch=master
   :alt: Build Status
   :target: https://secure.travis-ci.org/tarpas/pytest-testmon.png


This is a py.test plug-in which automatically selects and re-executes only tests affected by recent changes. How is this possible in dynamic language like Python and how reliable is it? Read here: `Determining affected tests <https://github.com/tarpas/pytest-testmon/wiki/Determining-affected-tests>`_

New versions usually have new dataformat, don't forget to rm .testmondata after each upgrade.

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
    # If you want to separate different environments running the same sources.
    run_variant_expression = os.environ.get('DJANGO_SETTINGS_MODULE') + ':python' + str(sys.version_info[:2])
    addopts = --testmon # you can make --testmon a default if you want


More complex `run_variant_expression` can be written: the `os`, `sys` and
`hashlib` modules are available, and there is a helper function `md5(s)` that
will return `hashlib.md5(s.encode()).hexdigest()`.

Configuring subprocess tracking
=================================
If your test suite uses subprocesses testmon supports this. You just have to configure python+coverage
so that the coverage hook is executed with every python process started. You can do this by installing
coverage_pth

::

     pip install coverage_pth 
     
If there is any problem you can still configure your python `manually <http://coverage.readthedocs.org/en/latest/subprocess.html>`_.


Troubleshooting - usual problems
================================
Testmon selects too many tests for execution: Depending you your change it most likely is
by design. If you changed a method parameter name, you effectively changed the whole hierarchy
parameter -> method -> class -> module, so any test using anything from that module will be
re-executed.

If you experience different, even random test outcomes with testmon as opposed to plain py.test
chances are it is NOT a testmon bug. Every time I got a "bug" report about this we found out the tests
depended on each other through some global state. The set of deselected and executed tests with
testmon is highly variable, which means testmon is likely to expose the undesired test
dependencies. That said, hidden test dependencies are a major no-no and you'll run into problems
even without testmon. Fix your tests! 

For filing a bug report, please isolate one test and report the unexpected outcomes of that one test. 
(Most probably you'll experience the same behaviour regardless if you use --testmon or not. Of course 
you should be adding/removing some no-op statement in the test to trigger re-execution)


Roadmap
=======
testmon is approaching completeness. Unfortunatelly the classic console UI is reaching it's usability limits even without testmon.
With testmon it's even a little more difficult to determine which tests are beeing executed, which are failing and why.
Next step would be an implementation or integration of GUI. I don't like any  of the existing graphical test runners, so
if you have some better new concept in mind, get in touch!


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