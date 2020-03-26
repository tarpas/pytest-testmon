

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


To learn more about specifying multiple project directories, configuring “sticky” testmon and troubleshooting, please head to `testmon.org <https://testmon.org>`_

DataRobot Release
=================

To upload a new version:
- Uprev the version in ``setup.py`` to something like ``0.19.8.post4``
- Upload with `python setup.py sdist upload -r datarobot-python-dev` in a clean repo.
- Update quantum-builder with the new path to source and uprev there in https://github.com/datarobot/quantum-builders/blob/master/libraries/python_pure.matrix.yaml.
- Tag as ``v0.19.8.post4`` and push.
