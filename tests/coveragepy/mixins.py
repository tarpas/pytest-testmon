# Licensed under the Apache License: http://www.apache.org/licenses/LICENSE-2.0
# For details: https://github.com/nedbat/coveragepy/blob/master/NOTICE.txt

"""
Test class mixins

Some of these are transitional while working toward pure-pytest style.
"""

import importlib
import os
import os.path
import shutil
import sys

import pytest

from tests.coveragepy.helpers import change_dir, make_file, remove_files


class PytestBase:
    """A base class to connect to pytest in a test class hierarchy."""

    @pytest.fixture(autouse=True)
    def connect_to_pytest(self, request, monkeypatch):
        """Captures pytest facilities for use by other test helpers."""
        # pylint: disable=attribute-defined-outside-init
        self._pytest_request = request
        self._monkeypatch = monkeypatch
        self.setup_test()

    # Can't call this setUp or setup because pytest sniffs out unittest and
    # nosetest special names, and does things with them.
    # https://github.com/pytest-dev/pytest/issues/8424
    def setup_test(self):
        """Per-test initialization. Override this as you wish."""
        pass

    def addCleanup(self, fn, *args):
        """Like unittest's addCleanup: code to call when the test is done."""
        self._pytest_request.addfinalizer(lambda: fn(*args))

    def set_environ(self, name, value):
        """Set an environment variable `name` to be `value`."""
        self._monkeypatch.setenv(name, value)

    def del_environ(self, name):
        """Delete an environment variable, unless we set it."""
        self._monkeypatch.delenv(name, raising=False)


class TempDirMixin:
    """Provides temp dir and data file helpers for tests."""

    # Our own setting: most of these tests run in their own temp directory.
    # Set this to False in your subclass if you don't want a temp directory
    # created.
    run_in_temp_dir = True

    @pytest.fixture(autouse=True)
    def _temp_dir(self, tmpdir_factory):
        """Create a temp dir for the tests, if they want it."""
        if self.run_in_temp_dir:
            tmpdir = tmpdir_factory.mktemp("t")
            self.temp_dir = str(tmpdir)
            with change_dir(self.temp_dir):
                # Modules should be importable from this temp directory.  We don't
                # use '' because we make lots of different temp directories and
                # nose's caching importer can get confused.  The full path prevents
                # problems.
                sys.path.insert(0, os.getcwd())

                yield None
        else:
            yield None

    def make_file(self, filename, text="", bytes=b"", newline=None):
        """Make a file. See `tests.helpers.make_file`"""
        # pylint: disable=redefined-builtin     # bytes
        assert self.run_in_temp_dir, "Only use make_file when running in a temp dir"
        return make_file(filename, text, bytes, newline)
