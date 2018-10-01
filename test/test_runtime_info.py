from runtime_info import pytest_runtime_info
import os
import json
import pytest


@pytest.fixture
def lib_py(testdir):
    return testdir.makepyfile(lib="""
        def multiply():
            return 2 * 4 / 0

        def call_multiply():
            multiply()
    """)


@pytest.fixture
def a_py(testdir):
    return testdir.makepyfile(test_a="""
        import lib

        def test_a():
            lib.call_multiply();
    """)


@pytest.fixture
def b_py(testdir):
    return testdir.makepyfile(test_b="""
        def test_b():
            assert False

        def test_pass():
            assert True
    """)


def test_plugin(testdir, lib_py, a_py, b_py):
    result_file = pytest_runtime_info.get_temp_file_path()
    try:
        file_modified = os.stat(result_file).st_mtime
    except Exception:
        file_modified = 0
    test_result = testdir.runpytest()
    # test if failed
    test_result.assert_outcomes(failed=2, passed=1)
    # test if result file was modified
    assert file_modified != os.stat(result_file).st_mtime
    with open(result_file) as result_stream:
        result_json = result_stream.read()
        result = json.loads(result_json)
    a_file = os.path.join(str(testdir.tmpdir), "test_a.py")
    b_file = os.path.join(str(testdir.tmpdir), "test_b.py")
    lib_file = os.path.join(str(testdir.tmpdir), "lib.py")
    assert len(result["exceptions"]) == 2
    assert len([x for x in result["exceptions"] if x["path"] == lib_file]) == 1
    assert len([x for x in result["exceptions"] if x["path"] == b_file]) == 1
    assert len(result["fileMarkList"]) == 3
    assert len([x for x in result["fileMarkList"] if x["path"] == lib_file]) == 1
    assert len([x for x in result["fileMarkList"] if x["path"] == b_file]) == 1
    assert len([x for x in result["fileMarkList"] if x["path"] == a_file]) == 1
    fileMarksA = [x for x in result["fileMarkList"] if x["path"] == a_file][0]
    fileMarksB = [x for x in result["fileMarkList"] if x["path"] == b_file][0]
    fileMarksLib = [x for x in result["fileMarkList"] if x["path"] == lib_file][0]
    assert len(fileMarksA["marks"]) == 3
    assert len(fileMarksB["marks"]) == 2
    assert len(fileMarksLib["marks"]) == 7
    gutterMarks = [x for x in fileMarksLib["marks"] if x["type"] == "GutterLink"]
    assert len(gutterMarks) == 3
    assert len([x for x in gutterMarks if x["targetPath"] == lib_file]) == 2
    assert len([x for x in gutterMarks if x["targetPath"] == a_file]) == 1
