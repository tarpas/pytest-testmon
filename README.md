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

## Shared cache in S3 (this fork)

    pip install "pytest-testmon[s3]"
    pytest --testmon-s3=s3://bucket/prefix

Each branch reads and writes `s3://bucket/prefix/<branch>/.testmondata`. A branch
with no data, or with no data for the current packages hash (e.g. after a
requirements bump on the target branch), is seeded from the PR target branch
(`GITHUB_BASE_REF` etc.) and then `testmon_s3_fallback_branch` (default `main`).

The packages hash comes from the installed packages, or from the files named in
`testmon_packages_from`: requirements files, or a `uv.lock` (Python 3.11+), which
gives one `name==version` per locked package plus the source of a package that
does not come from a registry (a git dependency's commit).

    # pyproject.toml
    [tool.pytest.ini_options]
    testmon_packages_from = ["uv.lock"]

`--testmon-s3-read-branch=master` selects against a read-only snapshot of that
branch's object only: no local `.testmondata`, no seeding, no upload, and an
error if the object does not exist. Pair it with `--testmon-nocollect` on CI
pull-request runs so a PR runs the tests affected by its diff against master
and never writes its own object.

## Call for opensource projects: try testmon in CI with no effort or risk.

We would like to run testmon within your project, collect data and improve!
We'll prepare the PR for you and set everything up so that no tests are deselected initially.
You can start using the full functionality whenever the reliability and time savings seem right!
Please <a href="https://www.testmon.net/">SIGN UP</a> and we'll contact you shortly.
