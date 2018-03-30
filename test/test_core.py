import pytest
from collections import namedtuple

from testmon.process_code import Module, read_file_with_checksum
from test.test_process_code import CodeSample
from testmon.testmon_core import TestmonData as CoreTestmonData, SourceTree, flip_dictionary, unaffected, \
    checksums_to_blob, CHECKUMS_ARRAY_TYPE, blob_to_checksums

import sqlite3

pytest_plugins = "pytester",

Block = namedtuple('Block', 'checksums')
from array import array


class TestGeneral(object):

    def test_flip(self):
        node_data = {'X': {'a': [1, 2, 3], 'b': [3, 4, 5]}, 'Y': {'b': [3, 6, 7]}}
        files = flip_dictionary(node_data)
        assert files == {'a': {'X': [1, 2, 3]}, 'b': {'X': [3, 4, 5], 'Y': [3, 6, 7]}}

    def test_sqlite_assumption(self):
        assert array(CHECKUMS_ARRAY_TYPE).itemsize == 4

        checksums = [4294967295, 123456]

        blob = checksums_to_blob(checksums)

        con = sqlite3.connect(':memory:')
        con.execute('CREATE TABLE a (c BLOB)')
        con.execute('INSERT INTO a VALUES (?)', [blob])

        cursor = con.execute('SELECT c FROM A')
        assert checksums == blob_to_checksums(cursor.fetchone()[0])

        cursor = con.execute('SELECT length(c) FROM A')
        assert cursor.fetchone()[0] == len(checksums) * 4

    def test_write_data(self, testdir):
        td = CoreTestmonData(testdir.tmpdir.strpath, 'V1')
        td._write_attribute('1', {})

    def test_write_read_data(self, testdir):
        td = CoreTestmonData(testdir.tmpdir.strpath, 'V1')
        with td.connection:
            td._write_attribute('1', {'a': 1})
        td2 = CoreTestmonData(testdir.tmpdir.strpath, 'V1')
        assert td2._fetch_attribute('1') == {'a': 1}

    def test_read_nonexistent(self, testdir):
        td = CoreTestmonData(testdir.tmpdir.strpath, 'V2')
        assert td._fetch_attribute('1') == None

    def test_write_read_data2(self, testdir):
        n1_node_data = {'a.py': [1]}
        td = CoreTestmonData(testdir.tmpdir.strpath, 'default')
        td.lastfailed = ['n1']
        td.write_data()
        td.set_dependencies('n1', n1_node_data, [])
        td2 = CoreTestmonData(testdir.tmpdir.strpath, 'default')
        td2.read_data()
        assert td2.node_data['n1'] == n1_node_data


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
        assert is_dependent({'a.py': [101, 102]}, changed_py_files) == False
        assert is_dependent({'a.py': [105, 106], 'b.py': [107, 108]}, changed_py_files) == True

    def test_two_modules_combination2(self):
        changed_py_files = {'b.py': get_modules([103, 104])}
        assert is_dependent({'a.py': [101, 102]}, changed_py_files) == False
        assert is_dependent({'a.py': [101], 'b.py': [107]}, changed_py_files) == True

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

        assert is_dependent({'test_s.py': [bs1[0].checksum, bs1[2].checksum]},
                            {'test_s.py': [b.checksum for b in bs2]}) == True
        assert is_dependent({'test_s.py': [bs1[1].checksum, bs1[2].checksum]},
                            {'test_s.py': [b.checksum for b in bs2]}) == True

    def test_affected_list(self, testdir):
        changes = {'test_a.py': [102, 103]}

        td = CoreTestmonData(testdir.tmpdir.strpath)
        td.node_data = {'node1': {'test_a.py': [101, 102]},
                        'node2': {'test_a.py': [102, 103], 'test_b.py': [200, 201]}}

        assert set(td.file_data()) == set(['test_a.py', 'test_b.py'])

        assert affected_nodeids(td.node_data, changes) == {'node1'}

    def test_affected_list2(self):
        changes = {'test_a.py': [102, 103]}
        dependencies = {'node1': {'test_a.py': [102, 103, 104]}, }
        assert affected_nodeids(dependencies, changes) == {'node1'}


def get_changed_files(dependencies, changes):
    changed_files = {}
    file_data = flip_dictionary(dependencies)
    for change, remove in changes.items():
        changed_files[change] = []
        for sublist in file_data[change].values():
            for checksum in sublist:
                if checksum not in remove:
                    changed_files[change].append(checksum)
    return changed_files


class TestUnaffected():
    def test_nothing_changed(self):
        changed = {'a.py': [101, 102, 103]}
        dependencies = {'test_a.py::node1': {'test_a.py': [201, 202], 'a.py': [101, 102, 103]}}
        assert unaffected(dependencies, blockify(changed))[0] == dependencies

    def test_simple_change(self):
        changed = {'a.py': [101, 102, 151]}
        dependencies = {'test_a.py::node1': {'test_a.py': [201, 202], 'a.py': [101, 102, 103]},
                        'test_b.py::node2': {'test_b.py': [301, 302], 'a.py': [151]}}

        nodes, files = unaffected(dependencies, blockify(changed))

        assert set(nodes) == {'test_b.py::node2'}
        assert set(files) == {'test_b.py'}

    def test_dependent_test_modules(self):
        dependencies = {'test_a.py::test_1': {'test_a.py': [1],
                                              'test_b.py': [3]},
                        'test_b.py::test_2': {'test_b.py': [2]}}
        changed = {'test_a.py': [-1]}

        nodes, files = unaffected(dependencies, blockify(changed))
        assert set(nodes) == {'test_b.py::test_2'}
        assert set(files) == {'test_b.py'}

        changed = {'test_b.py': [3]}
        nodes, files = unaffected(dependencies, blockify(changed))
        assert set(nodes) == {'test_a.py::test_1'}
        assert set(files) == {'test_a.py'}

    def test_dependent_test_modules2(self):
        dependencies = {'test_a.py::test_1': {'test_a.py': [1],
                                              'test_b.py': [3],
                                              'c.py': [4, 5]},
                        'test_b.py::test_2': {'test_b.py': [2]}}

        changed_files = get_changed_files(dependencies, {'c.py': [4]})
        nodes, files = unaffected(dependencies, blockify(changed_files))
        assert set(nodes) == {'test_b.py::test_2'}
        assert set(files) == {'test_b.py'}

        changed_files = get_changed_files(dependencies, {'test_b.py': [2]})
        nodes, files = unaffected(dependencies, blockify(changed_files))
        assert set(nodes) == {'test_a.py::test_1'}
        assert set(files) == {'test_a.py', 'c.py'}


def get_modules(checksums):
    return checksums


def is_dependent(dependencies, changes):
    result = affected_nodeids({'testnode': dependencies}, changes)
    return result == {'testnode'}


def affected_nodeids(dependencies, changes):
    unaffected_nodes, files = unaffected(dependencies, blockify(changes))
    return set(dependencies) - set(unaffected_nodes)


def blockify(changes):
    block_changes = {key: Block(value) for key, value in changes.items()}
    return block_changes


global_reports = []


class TestSourceTree():
    @pytest.fixture
    def a_py(self, testdir):
        return testdir.makepyfile(a="""
        def test_a():
            return 0
        """)

    def test_basic(self, testdir, a_py):
        code, checksum = read_file_with_checksum('a.py')
        assert checksum == 'ea4739bb5b0069cafb92af3874891898617ef590'

        fs_data = SourceTree(rootdir=testdir.tmpdir.strpath, mtimes={'a.py': a_py.mtime()},
                             checksums={'a.py': checksum})
        changed_files = fs_data.get_changed_files()
        assert changed_files == {}

    def test_basic_checksum(self, testdir, a_py):
        code, checksum = read_file_with_checksum('a.py')
        fs_data = SourceTree(rootdir=testdir.tmpdir.strpath, mtimes={'a.py': a_py.mtime()},
                             checksums={'a.py': checksum})

        a_py.setmtime(1424880936)
        changed_files = fs_data.get_changed_files()
        assert changed_files == {}
        assert fs_data.mtimes['a.py'] == 1424880936

        testdir.makepyfile(a="""
        def test_a():
            return 0 # comment
        """)
        fs_data = SourceTree(rootdir=testdir.tmpdir.strpath, mtimes={'a.py': -100}, checksums={'a.py': checksum})
        changed_files = fs_data.get_changed_files()
        assert 'a.py' in changed_files
        assert [type(c) for c in changed_files['a.py'].checksums] == [int, int]
        assert fs_data.checksums['a.py'] == 'ec1fd361d4d73353c3f65cb10b86fcea4e0d0e42'

    def test_get_file(self, testdir, a_py):
        fs_data = SourceTree(rootdir=testdir.tmpdir.strpath, mtimes={'a.py': -100}, checksums={'a.py': -200})
        fs_data.get_file('a.py')
        fs_data.mtimes['a.py'] = a_py.mtime
        fs_data.checksums['a.py'] = 'ec1fd361d4d73353c3f65cb10b86fcea4e0d0e42'

    def test_disappeared(self, testdir, a_py):
        fs_data = SourceTree(rootdir=testdir.tmpdir.strpath, mtimes={'b.py': -100}, checksums={'b.py': -200})
        fs_data.get_changed_files()
        pytest.raises((OSError, IOError), fs_data.get_file, 'c.py')

        # parse_fs_changes(stored_version={'a.py': [a_py.mtime, hash(a_py.read_mtime)]})
