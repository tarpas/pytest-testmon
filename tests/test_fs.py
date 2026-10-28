import os
import time

import pytest
from .test_core import CoreTestmonDataForTest, FINGERPRINT1


pytest_plugins = ("pytester",)


@pytest.fixture
def tmdatafs(testdir):
    return CoreTestmonDataForTest()


class TestFileSystem(object):
    def test_filesystem_time_fractions(self, testdir):
        def check_mtime():
            tf = testdir.maketxtfile("akd3")
            time.sleep(0.001)
            return os.path.getmtime(tf.basename) % 1 != 0

        assert check_mtime() or check_mtime()

    def test_mtime_difference(self, testdir, tmdatafs: CoreTestmonDataForTest):
        file_a = testdir.makepyfile(test_a="1")
        # let's execute some minimal but realistic work
        # which should happen between executions
        tmdatafs.write_fixture("test_a.py::n1", {"test_a.py": FINGERPRINT1})
        CoreTestmonDataForTest()
        file_b = testdir.makepyfile(file_b="print('hello')")
        assert (file_b.mtime() - file_a.mtime()) != 0
