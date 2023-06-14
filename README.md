# Pytest-testmon

This is a pytest plug-in which automatically selects and re-executes
only tests affected by recent changes. How is this possible in dynamic
language like Python and how reliable is it?
Read here: [Determining affected tests](https://testmon.org/determining-affected-tests.html)

## Quickstart

    pip install pytest-testmon

    # build the dependency database and save it to .testmondata
    pytest --testmon

    # change some of your code (with test coverage)

    # only run tests affected by recent changes
    pytest --testmon

To learn more about specifying multiple project directories, configuring
"sticky" testmon and troubleshooting, please head to [testmon.org](https://testmon.org)

## DataRobot Release

**To upload a new version:**

  1. Tag a commit like `v1.2.3` and [Create a new release](https://github.com/datarobot/pytest-rerunfailures/releases/new)
  2. Update `quantum-builder` with the new path to source and uprev in [quantum-builders](https://github.com/datarobot/quantum-builders/blob/master/libraries/python_pure.matrix.yaml)
