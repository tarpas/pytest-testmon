python-autotest
===============

Test runner that watches source files for changes and runs relevant tests automatically as needed.

It currently uses nose for task discovery and running and coverage.py for determining which files are being used by which tests.

Usage:
    cd testapp/
    python ../autotest.py

It is still early alpha.