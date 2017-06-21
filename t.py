import pytest

if __name__ == '__main__':
    # test/test_testmon.py::TestmonDeselect::test_nonfunc_class
    # test/test_testmon.py::TestmonDeselect::test_tlf
    pytest.main("--tb=native -v" )
    #pytest.main("-v -n 2 --tx=popen//python=python3")
    #pytest.main("--help -v")
