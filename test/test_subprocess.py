import os
import pytest
from test.coveragepy.coveragetest import CoverageTest

class TestCoverageSubprocess(CoverageTest):

        def test_basic_run(self):
            path1 = self.make_file("subprocesstest.py", """\
            print("hello world")
            """)
            output = self.run_command('python {}'.format(path1))
            assert output == "hello world\n"

        def test_pass_environ(self):
            path1 = self.make_file("subprocesstest.py", """\
            import os
            print(os.environ['TEST_NAME'])
            """)
            os.environ['TEST_NAME'] = 'TEST_VALUE'
            output = self.run_command('python {}'.format(path1))
            assert output == "{}\n".format('TEST_VALUE')

        @pytest.mark.xfail
        def test_coverage_expected_fail(self):
            path1 = self.make_file("subprocesstest.py", """\
            a=1
            """)
            os.environ['COVERAGE_PROCESS_START'] = 'nonexistent_file'
            output = self.run_command('python {}'.format(path1))
            del os.environ['COVERAGE_PROCESS_START']
            assert "Couldn't read 'nonexistent_file' as a config file" in output

        @pytest.mark.xfail
        def test_subprocess(self):
            path1 = self.make_file("subprocesstest.py", """\
            a=1
            """)
            self.make_file('.testmoncoveragerc', """\
                [run]

                data_file = {}/.testmoncoverage
            """.format(os.getcwd()))
            os.environ['COVERAGE_PROCESS_START']='{}/.testmoncoveragerc'.format(os.getcwd())
            self.run_command('python {}'.format(path1))
            subprocess_coverage_exists = os.path.exists('.testmoncoverage')
            assert subprocess_coverage_exists, "Dir: {}".format(os.listdir(os.getcwd()))
            del os.environ['COVERAGE_PROCESS_START']
