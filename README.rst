This is a pytest plug-in which automatically selects and re-executes only tests affected by recent changes. How is this possible in dynamic language like Python and how reliable is it? Read here: `Determining affected tests <https://testmon.org/determining-affected-tests.html>`_

Quickstart
===========

::

    pip install pytest-testmon

    # build the dependency database and save it to .testmondata
    pytest --testmon

    # change some of your code (with test coverage)

    # only run tests affected by recent changes
    pytest --testmon


To learn more about specifying multiple project directories and troubleshooting, please head to `testmon.org <https://testmon.org>`_
