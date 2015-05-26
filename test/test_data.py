from testmon.testmon_core import TestmonData

pytest_plugins = "pytester",


def test_write_data(testdir):
    td = TestmonData(testdir.tmpdir.strpath, 'V1')
    td._write_attribute('1', {})


def test_write_read_data(testdir):
    td = TestmonData(testdir.tmpdir.strpath, 'V1')
    with td.connection:
        td._write_attribute('1', {'a': 1})
    td2 = TestmonData(testdir.tmpdir.strpath, 'V1')
    assert td2._fetch_attribute('1') == {'a': 1}


def test_read_nonexistent(testdir):
    td = TestmonData(testdir.tmpdir.strpath, 'V2')
    assert td._fetch_attribute('1') == None


def test_write_read_data(testdir):
    td = TestmonData(testdir.tmpdir.strpath, 'default')
    td.mtimes = {'a.py': 1.0}
    td.node_data = {'n1': {'a.py': [1]}}
    td.lastfailed = ['n1']
    td.write_data()
    td2 = TestmonData(testdir.tmpdir.strpath, 'default')
    td2.read_data()
    assert td == td2


