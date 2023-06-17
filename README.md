<img src=https://user-images.githubusercontent.com/135344/219700265-0a9b152f-7285-4607-bbce-0c9aeddd520b.svg width=300>

This is a pytest plug-in which automatically selects and re-executes
only tests affected by recent changes. How is this possible in dynamic
language like Python and how reliable is it? Read here: [Determining
affected tests](https://testmon.org/blog/determining-affected-tests/)

## Quickstart

    pip install pytest-testmon

    # build the dependency database and save it to .testmondata
    pytest --testmon

    # change some of your code (with test coverage)

    # only run tests affected by recent changes
    pytest --testmon

To learn more about different options you can use with testmon, please
head to [testmon.org](https://testmon.org)

## Call for opensource projects: try testmon in CI with no effort or risk.

We would like to run testmon within your project, collect data and improve!
We'll prepare the PR for you and set everything up so that no tests are deselected initially.
You can start using the full functionality whenever the reliability and time savings seem right!
Please <a href="https://www.testmon.net/">SIGN UP</a> and we'll contact you shortly.
