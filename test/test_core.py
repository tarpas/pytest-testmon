from testmon.process_code import Module
from test.test_process_code import CodeSample
from test.test_testmon import get_modules
from testmon.testmon_core import TestmonData as CoreTestmonData
from testmon.testmon_core import is_dependent, affected_nodeids

pytest_plugins = "pytester",


def test_write_data(testdir):
    td = CoreTestmonData(testdir.tmpdir.strpath, 'V1')
    td._write_attribute('1', {})


def test_write_read_data(testdir):
    td = CoreTestmonData(testdir.tmpdir.strpath, 'V1')
    with td.connection:
        td._write_attribute('1', {'a': 1})
    td2 = CoreTestmonData(testdir.tmpdir.strpath, 'V1')
    assert td2._fetch_attribute('1') == {'a': 1}


def test_read_nonexistent(testdir):
    td = CoreTestmonData(testdir.tmpdir.strpath, 'V2')
    assert td._fetch_attribute('1') == None


def test_write_read_data2(testdir):
    td = CoreTestmonData(testdir.tmpdir.strpath, 'default')
    td.mtimes = {'a.py': 1.0}
    td.node_data = {'n1': {'a.py': [1]}}
    td.lastfailed = ['n1']
    td.write_data()
    td2 = CoreTestmonData(testdir.tmpdir.strpath, 'default')
    td2.read_data()
    assert td == td2


class TestDepGraph():
    def test_dep_graph1(self):
        assert is_dependent({'a.py': [101, 102]}, {'a.py': [101, 102, 3]}) == False

    def test_dep_graph_new(self):
        assert is_dependent({'a.py': [101, 102]}, {'new.py': get_modules([101, 102, 3]),
                                                   'a.py': get_modules([101, 102, 3])}) == False

    def test_dep_graph2(self):
        assert is_dependent({'a.py': [101, 102]}, {'a.py': get_modules([101, 102])}) == False

    def test_dep_graph3(self):
        assert is_dependent({'a.py': [101, 102]}, {'a.py': get_modules([101, 102, 103])}) == False

    def test_dep_graph4(self):
        assert is_dependent({'a.py': [101, 102]}, {'a.py': get_modules([101, 103])}) == True

    def test_dep_graph_two_modules(self):
        changed_py_files = {'b.py': get_modules([])}
        assert is_dependent({'a.py': [101, 102]}, changed_py_files) == False
        assert is_dependent({'b.py': [103, 104]}, changed_py_files) == True

    def test_two_modules_combination(self):
        changed_py_files = {'b.py': get_modules([])}
        assert is_dependent( {'a.py': [101, 102]}, changed_py_files) == False
        assert is_dependent({'a.py': [105, 106], 'b.py': [107, 108]}, changed_py_files) == True

    def test_two_modules_combination2(self):
        changed_py_files = {'b.py': get_modules([103, 104])}
        assert is_dependent({'a.py': [101, 102]}, changed_py_files) == False
        assert is_dependent({'a.py': [101], 'b.py': [107]}, changed_py_files) == True

    def test_two_modules_combination3(self):
        changed_py_files = {'b.py': get_modules([103, 104])}
        assert is_dependent('test_1', changed_py_files) == False
        assert is_dependent('test_both', changed_py_files) == False

    def test_classes_depggraph(self):
        module1 = Module(CodeSample("""\
            class TestA(object):
                def test_one(self):
                    print("1")

                def test_two(self):
                    print("2")
        """).source_code)
        bs1 = module1.blocks

        module2 = Module(CodeSample("""\
            class TestA(object):
                def test_one(self):
                    print("1")

                def test_twob(self):
                    print("2")
        """).source_code)
        bs2 = module2.blocks

        assert bs1[0] == bs2[0]
        assert bs1[1] != bs2[1]
        assert bs1[2] != bs2[2]

        assert len(module1.blocks) == len(module2.blocks) == 3
        assert (bs1[1].start,
                bs1[1].end,
                bs1[1].checksum) == (bs2[1].start,
                                     bs2[1].end,
                                     bs2[1].checksum)
        assert (bs1[1].name) != (bs2[1].name)


        assert is_dependent({'test_s.py': [bs1[0].checksum, bs1[2].checksum]}, {'test_s.py': [b.checksum for b in bs2]}) == True
        assert is_dependent({'test_s.py': [bs1[1].checksum, bs1[2].checksum]}, {'test_s.py': [b.checksum for b in bs2]}) == True


    def test_affected_list(self):
        changes = {'test_a.py': [102, 103]}

        td = CoreTestmonData('')
        td.node_data = {'node1': {'test_a.py': [101, 102]},
                        'node2': {'test_a.py': [102, 103], 'test_b.py': [200, 201]}}

        assert set(td.modules_test_counts()) == set(['test_a.py', 'test_b.py'])

        assert affected_nodeids(td.node_data, changes) == ['node1']


    def test_affected_list2(self):
        changes = {'test_a.py': [102, 103]}
        dependencies = {'node1': {'test_a.py': [102, 103, 104]},}
        assert affected_nodeids(dependencies, changes) == ['node1']


def test_variants_separation(testdir):
    testmon1_data = CoreTestmonData(testdir.tmpdir.strpath, variant='1')
    testmon1_data.node_data['node1'] = {'a.py': 1}
    testmon1_data.write_data()

    testmon2_data = CoreTestmonData(testdir.tmpdir.strpath, variant='2')
    testmon2_data.node_data['node1'] = {'a.py': 2}
    testmon2_data.write_data()

    testmon_check_data = CoreTestmonData(testdir.tmpdir.strpath, variant='1')
    testmon_check_data.read_fs()
    assert testmon1_data.node_data['node1'] == {'a.py': 1 }

