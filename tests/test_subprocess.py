import os
import sys
import pytest
from tests.coveragepy.coveragetest import CoverageTest
from testmon.testmon_core import TestmonCollector as CoreTestmon


class TestCoverageSubprocess(CoverageTest):
    def test_basic_run(self):
        path1 = self.make_file(
            "subprocesstest.py",
            """\
        print("hello world")
        """,
        )
        output = self.run_command("{} {}".format(sys.executable, path1))
        assert output == "hello world\n"

    def test_pass_environ(self):
        path1 = self.make_file(
            "subprocesstest.py",
            """\
        import os
        print(os.environ['TEST_NAME'])
        """,
        )
        self.set_environ("TEST_NAME", "TEST_VALUE")
        output = self.run_command("{} {}".format(sys.executable, path1))
        assert output == "{}\n".format("TEST_VALUE")

    @pytest.mark.skipif(
        "cov6" not in os.environ.get("TOX_ENV_NAME", "cov"),
        reason="requires pytest-cov version 6 in TOX",
    )
    def test_coverage_expected_fail(self):
        path1 = self.make_file(
            "subprocesstest.py",
            """\
        a=1
        """,
        )
        self.set_environ("COV_CORE_SOURCE", "yes")
        self.set_environ("COV_CORE_CONFIG", "nonexistent_file")
        self.set_environ("COV_CORE_DATAFILE", "bla")
        output = self.run_command("python {}".format(path1))

        assert "Couldn't read 'nonexistent_file' as a config file" in output

    def test_subprocess_pytest_cov(self):
        path1 = self.make_file(
            "subprocesstest.py",
            """\
        a=1
        """,
        )
        self.make_file(
            ".testmoncoveragerc",
            """\
            [run]

            data_file = {}/.testmoncoverage
        """.format(os.getcwd()),
        )
        self.set_environ("COV_CORE_SOURCE", "yes")
        self.set_environ("COV_CORE_CONFIG", "{}/.testmoncoveragerc".format(os.getcwd()))
        self.set_environ("COV_CORE_DATAFILE", ".testmoncoverage")
        self.run_command("python {}".format(path1))
        assert ".testmoncoverage" in "{}".format(os.listdir(os.getcwd())), os.listdir(
            os.getcwd()
        )

    def test_subprocess_testmon(self):
        testmon = CoreTestmon(rootdir=os.getcwd())
        testmon.setup_coverage(subprocess=True)
        testmon.start_testmon("1")
        path1 = self.make_file(
            "subprocesstest.py",
            """\
        a=1
        """,
        )
        self.run_command(f"python {path1}")
        testmon.discard_current()
        testmon.close()
        base = os.path.basename(testmon.sub_cov_file)
        files = os.listdir(os.path.join(os.getcwd(), ".tmontmp"))
        assert base in files
        # the subprocess wrote its own parallel-mode data file next to it
        assert any(f.startswith(base + ".") for f in files), files
