from collections import namedtuple

from testmon.process_code import Module
from test.test_process_code import CodeSample
from testmon.testmon_core import TestmonData as CoreTestmonData, flip_dictionary, unaffected

pytest_plugins = "pytester",

Block = namedtuple('Block', 'checksums')


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
    n1_node_data = {'a.py': [1]}
    original = ({'a.py': 1.0}, ['n1'])
    td = CoreTestmonData(testdir.tmpdir.strpath, 'default')
    td.mtimes, td.lastfailed = original
    td.write_data()
    td.set_dependencies('n1', n1_node_data, )
    td2 = CoreTestmonData(testdir.tmpdir.strpath, 'default')
    td2.read_data()
    assert td2.node_data['n1'] == n1_node_data
    assert original == (td2.mtimes, td2.lastfailed)


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

    def test_affected_list(self):
        changes = {'test_a.py': [102, 103]}

        td = CoreTestmonData('')
        td.node_data = {'node1': {'test_a.py': [101, 102]},
                        'node2': {'test_a.py': [102, 103], 'test_b.py': [200, 201]}}

        assert set(td.file_data()) == set(['test_a.py', 'test_b.py'])

        assert affected_nodeids(td.node_data, changes) == {'node1'}

    def test_affected_list2(self):
        changes = {'test_a.py': [102, 103]}
        dependencies = {'node1': {'test_a.py': [102, 103, 104]}, }
        assert affected_nodeids(dependencies, changes) == {'node1'}


class TestUnaffected():
    def test_nothing_changed(self):
        changed = {'a.py': [101, 102, 103]}
        dependencies = {'node1': {'test_a.py': [201, 202], 'a.py': [101, 102, 103]}}
        assert unaffected(dependencies, blockify(changed))[0] == dependencies

    def test_simple_change(self):
        changed = {'a.py': [101, 102, 151]}
        dependencies = {'node1': {'test_a.py': [201, 202], 'a.py': [101, 102, 103]},
                        'node2': {'test_b.py': [301, 302], 'a.py': [151]}}

        nodes, files = unaffected(dependencies, blockify(changed))

        assert set(nodes) == {'node2'}
        assert set(files) == {'test_b.py'}


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


def test_variants_separation(testdir):
    testmon1_data = CoreTestmonData(testdir.tmpdir.strpath, variant='1')
    testmon1_data.node_data['node1'] = {'a.py': 1}
    testmon1_data.write_data()

    testmon2_data = CoreTestmonData(testdir.tmpdir.strpath, variant='2')
    testmon2_data.node_data['node1'] = {'a.py': 2}
    testmon2_data.write_data()

    testmon_check_data = CoreTestmonData(testdir.tmpdir.strpath, variant='1')
    testmon_check_data.read_fs()
    assert testmon1_data.node_data['node1'] == {'a.py': 1}


def test_flip():
    node_data = {'X': {'a': [1, 2, 3], 'b': [3, 4, 5]}, 'Y': {'b': [3, 6, 7]}}
    files = flip_dictionary(node_data)
    assert files == {'a': {'X': [1, 2, 3]}, 'b': {'X': [3, 4, 5], 'Y': [3, 6, 7]}}


global_reports = []


def serialize_report(rep):
    import py
    d = rep.__dict__.copy()
    if hasattr(rep.longrepr, 'toterminal'):
        d['longrepr'] = str(rep.longrepr)
    else:
        d['longrepr'] = rep.longrepr
    for name in d:
        if isinstance(d[name], py.path.local):
            d[name] = str(d[name])
        elif name == "result":
            d[name] = None  # for now
    return d


def test_serialize(testdir):
    class PlugWrite:
        def pytest_runtest_logreport(self, report):
            global global_reports
            global_reports.append(report)

    class PlugRereport:
        def pytest_runtest_protocol(self, item, nextitem):
            hook = getattr(item.ihook, 'pytest_runtest_logreport')
            for g in global_reports:
                hook(report=g)
            return True

    testdir.makepyfile("""
    def test_a():
        raise Exception('exception from test_a')
    """)

    testdir.runpytest_inprocess(plugins=[PlugWrite()])

    testdir.makepyfile("""
    def test_a():
        pass
    """)

    result = testdir.runpytest_inprocess(plugins=[PlugRereport()])

    print(result)
