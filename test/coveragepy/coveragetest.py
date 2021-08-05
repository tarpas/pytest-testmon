# Licensed under the Apache License: http://www.apache.org/licenses/LICENSE-2.0
# For details: https://github.com/nedbat/coveragepy/blob/master/NOTICE.txt

"""Base test case class for coverage.py testing."""

import os
import os.path
import random
import shlex
import sys

import pytest

import coverage
import importlib


from test.coveragepy.helpers import nice_file, run_command
from test.coveragepy.mixins import PytestBase, TempDirMixin


def import_local_file(modname, modfile=None):
    """Import a local file as a module.

    Opens a file in the current directory named `modname`.py, imports it
    as `modname`, and returns the module object.  `modfile` is the file to
    import if it isn't in the current directory.

    """
    if modfile is None:
        modfile = modname + ".py"
    spec = importlib.util.spec_from_file_location(modname, modfile)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)

    return mod


# Status returns for the command line.
OK, ERR = 0, 1

# The coverage/tests directory, for all sorts of finding test helping things.
TESTS_DIR = os.path.dirname(__file__)


class CoverageTest(
    TempDirMixin,
    PytestBase,
):
    """A base class for coverage.py test cases."""

    # Standard unittest setting: show me diffs even if they are very long.
    maxDiff = None

    # Tell newer unittest implementations to print long helpful messages.
    longMessage = True

    # Let stderr go to stderr, pytest will capture it for us.
    show_stderr = True

    def setup_test(self):
        super().setup_test()

        # Attributes for getting info about what happened.
        self.last_command_status = None
        self.last_command_output = None
        self.last_module_name = None

    def start_import_stop(self, cov, modname, modfile=None):
        """Start coverage, import a file, then stop coverage.

        `cov` is started and stopped, with an `import_local_file` of
        `modname` in the middle. `modfile` is the file to import as `modname`
        if it isn't in the current directory.

        The imported module is returned.

        """
        cov.start()
        try:  # pragma: nested
            # Import the Python file, executing it.
            mod = import_local_file(modname, modfile)
        finally:  # pragma: nested
            # Stop coverage.py.
            cov.stop()
        return mod

    def get_module_name(self):
        """Return a random module name to use for this test run."""
        self.last_module_name = "coverage_test_" + str(random.random())[2:]
        return self.last_module_name

    def run_command(self, cmd):
        """Run the command-line `cmd` in a sub-process.

        `cmd` is the command line to invoke in a sub-process. Returns the
        combined content of `stdout` and `stderr` output streams from the
        sub-process.

        See `run_command_status` for complete semantics.

        Use this when you need to test the process behavior of coverage.

        Compare with `command_line`.

        """
        _, output = self.run_command_status(cmd)
        return output

    def run_command_status(self, cmd):
        """Run the command-line `cmd` in a sub-process, and print its output.

        Use this when you need to test the process behavior of coverage.

        Compare with `command_line`.

        Handles the following command names specially:

        * "python" is replaced with the command name of the current
            Python interpreter.

        * "coverage" is replaced with the command name for the main
            coverage.py program.

        Returns a pair: the process' exit status and its stdout/stderr text,
        which are also stored as `self.last_command_status` and
        `self.last_command_output`.

        """
        # Make sure "python" and "coverage" mean specifically what we want
        # them to mean.
        split_commandline = cmd.split()
        command_name = split_commandline[0]
        command_args = split_commandline[1:]

        if command_name == "python":
            # Running a Python interpreter in a sub-processes can be tricky.
            # Use the real name of our own executable. So "python foo.py" might
            # get executed as "python3.3 foo.py". This is important because
            # Python 3.x doesn't install as "python", so you might get a Python
            # 2 executable instead if you don't use the executable's basename.
            command_words = [os.path.basename(sys.executable)]

        elif command_name == "coverage":
            if env.JYTHON:  # pragma: only jython
                # Jython can't do reporting, so let's skip the test now.
                if command_args and command_args[0] in (
                    "report",
                    "html",
                    "xml",
                    "annotate",
                ):
                    pytest.skip("Can't run reporting commands in Jython")
                # Jython can't run "coverage" as a command because the shebang
                # refers to another shebang'd Python script. So run them as
                # modules.
                command_words = "jython -m coverage".split()
            else:
                # The invocation requests the coverage.py program.  Substitute the
                # actual coverage.py main command name.
                command_words = [self.coverage_command]

        else:
            command_words = [command_name]

        cmd = " ".join([shlex.quote(w) for w in command_words] + command_args)

        # Add our test modules directory to PYTHONPATH.  I'm sure there's too
        # much path munging here, but...
        pythonpath_name = "PYTHONPATH"

        testmods = nice_file(self.working_root(), "tests/modules")
        zipfile = nice_file(self.working_root(), "tests/zipmods.zip")
        pypath = os.getenv(pythonpath_name, "")
        if pypath:
            pypath += os.pathsep
        pypath += testmods + os.pathsep + zipfile
        self.set_environ(pythonpath_name, pypath)

        self.last_command_status, self.last_command_output = run_command(cmd)
        print(self.last_command_output)
        return self.last_command_status, self.last_command_output

    def working_root(self):
        """Where is the root of the coverage.py working tree?"""
        return os.path.dirname(nice_file(coverage.__file__, ".."))

    def report_lines(self, report):
        """Return the lines of the report, as a list."""
        lines = report.split("\n")
        assert lines[-1] == ""
        return lines[:-1]

    def line_count(self, report):
        """How many lines are in `report`?"""
        return len(self.report_lines(report))

    def squeezed_lines(self, report):
        """Return a list of the lines in report, with the spaces squeezed."""
        lines = self.report_lines(report)
        return [re.sub(r"\s+", " ", l.strip()) for l in lines]

    def last_line_squeezed(self, report):
        """Return the last line of `report` with the spaces squeezed down."""
        return self.squeezed_lines(report)[-1]

    def get_measured_filenames(self, coverage_data):
        """Get paths to measured files.

        Returns a dict of {filename: absolute path to file}
        for given CoverageData.
        """
        return {
            os.path.basename(filename): filename
            for filename in coverage_data.measured_files()
        }


class UsingModulesMixin:
    """A mixin for importing modules from tests/modules and tests/moremodules."""

    def setup_test(self):
        super().setup_test()

        # Parent class saves and restores sys.path, we can just modify it.
        sys.path.append(nice_file(TESTS_DIR, "modules"))
        sys.path.append(nice_file(TESTS_DIR, "moremodules"))


def command_line(args):
    """Run `args` through the CoverageScript command line.

    Returns the return code from CoverageScript.command_line.

    """
    script = CoverageScript()
    ret = script.command_line(shlex.split(args))
    return ret
