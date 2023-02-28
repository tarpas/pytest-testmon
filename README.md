<img src=https://user-images.githubusercontent.com/135344/219700265-0a9b152f-7285-4607-bbce-0c9aeddd520b.svg width=300>

# Testmon-skip-libaries
This is a fork of pytest-testmon that adds functionality to ignore changes to
libraries used by the code. The standard version of pytest-testmon looks not
only at the python code for changes, but also versions of dependencies. This
makes it unsuitable for sharing among developers (who may have a different local
set of dependencies), or CI/CD systems where your local, staging and production
environments may differ in the number and versions of dependencies used.

From the original repo:

This is a pytest plug-in which automatically selects and re-executes
only tests affected by recent changes. How is this possible in dynamic
language like Python and how reliable is it? Read here: [Determining
affected tests](https://testmon.org/determining-affected-tests.html)

## Quickstart

    pip install pytest-testmon-skip-libraries

    # build the dependency database and save it to .testmondata
    pytest --testmon

    # change some of your code (with test coverage)

    # only run tests affected by recent changes
    pytest --testmon

    # only run tests affected by recent changes while ignoring changes
    # to any libraries used by the code
    pytest --testmon --skip-libraries

To learn more about different options you can use with testmon, please
head to [testmon.org](https://testmon.org)