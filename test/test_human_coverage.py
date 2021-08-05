import ast

from .coveragepy.coveragetest import CoverageTest
from test.test_process_code import code_samples
from testmon.process_code import (
    Module,
    function_lines,
    GAP_MARKS,
    create_fingerprints,
    covered_unused_statement,
)
import textwrap
from coverage import coverage
from coverage.parser import PythonParser
import sys
from os.path import abspath

import re

blank_re = re.compile(r"\s*(#|$)")
else_finally_re = re.compile(r"\s*(else|finally)\s*:\s*(#|$)")


def human_coverage(source, statements, missing):
    result = set()

    i = 0
    j = 0
    covered = True
    for lineno, line in enumerate(source.splitlines(True), start=1):
        while i < len(statements) and statements[i] < lineno:
            i += 1
        while j < len(missing) and missing[j] < lineno:
            j += 1
        if i < len(statements) and statements[i] == lineno:
            covered = j >= len(missing) or missing[j] > lineno
        if blank_re.match(line):
            result.add(lineno)
        if else_finally_re.match(line):
            if i >= len(statements) or j >= len(missing):
                result.add(lineno)
            elif statements[i] == missing[j]:
                pass
            else:
                result.add(lineno)
        elif covered:
            result.add(lineno)
        else:
            pass

    return result


class TestmonCoverageTest(CoverageTest):
    def write_and_run(self, text):
        modname = self.get_module_name()
        filename = self.make_file(modname + ".py", text)
        cov = coverage()
        cov.erase()
        mod = self.start_import_stop(cov, modname)
        del sys.modules[modname]
        coverage_lines = cov.get_data().lines(abspath(modname + ".py"))
        return coverage_lines, filename

    def check_human_coverage(self, text, lines=None, fingerprints=None):

        text = textwrap.dedent(text)

        coverage_lines, _ = self.write_and_run(text)

        m = Module(source_code=text)

        parser = PythonParser(text=text)
        parser.parse_source()

        statements = parser.statements

        executed = coverage_lines
        executed = parser.translate_lines(executed)

        hc = sorted(
            human_coverage(text, sorted(statements), sorted(statements - executed))
        )

        assert hc == lines
        if fingerprints:
            assert create_fingerprints(m.lines, m.special_blocks, lines) == fingerprints

    def check_construct_fingerprints(self, text, liness=None, fingerprints=None):

        text = textwrap.dedent(text)

        coverage_lines, _ = self.write_and_run(text)

        m = Module(source_code=text)

        passed = False
        for lines in liness:
            passed = (sorted(coverage_lines) == lines) or passed
        assert passed, "None of the provided liness matches actual coverage"
        if fingerprints:
            assert create_fingerprints(m.lines, m.special_blocks, lines) == fingerprints


class TestCoverageAndFingeprintsAssumptions(TestmonCoverageTest):
    def test_covered_pass(self):
        assert covered_unused_statement(1, 2, {2}) == True
        assert covered_unused_statement(1, 2, {3}) == False

    def test_pass_1st_position(self):
        self.check_construct_fingerprints(
            """\
            a = 1
            def b():
                pass
                1
            b()
            """,
            [[1, 2, 4, 5], [1, 2, 3, 4, 5]],
        )


class BasicTestmonCoverageTest(TestmonCoverageTest):
    def test_simple(self):
        self.check_human_coverage(
            """\
        a = 1
        b = 2

        c = 4
        # Nothing here
        d = 6
        """,
            [1, 2, 3, 4, 5, 6],
            fingerprints=[
                "a = 1",
                "b = 2",
                "c = 4",
                "d = 6",
            ],
        )

    def test_indentation_wackiness(self):
        self.check_human_coverage(
            """\
            import sys
            if not sys.path:
                a = 1
                """,
            [1, 2],
        )

    def test_multiline_initializer(self):
        self.check_human_coverage(
            """\
            d = {
                'foo': 1+2,
                'bar': (lambda x: x+1)(1),
                'baz': str(1),
            }

            e = { 'foo': 1, 'bar': 2 }
            """,
            [1, 2, 3, 4, 5, 6, 7],
            "",
        )

    def test_multiline_with_class(self):
        self.check_human_coverage(
            """\
            class a:
                def a1():
                    a = [1,
            2]
            
            a.a1()
            """,
            [1, 2, 3, 4, 5, 6],
            "",
        )

    def test_list_comprehension(self):
        self.check_human_coverage(
            """\
            l = [
                2*i for i in range(10)
                if i > 5
                ]
            assert l == [12, 14, 16, 18]
            """,
            [1, 2, 3, 4, 5],
            "",
        )

    def test_method_surrounding(self):
        self.check_human_coverage(
            """\
            a = 1
            def b():
                pass
            c = 1
            """,
            [1, 2, 4],
            fingerprints=[
                "a = 1",
                "def b():",
                GAP_MARKS[3],
                "c = 1",
            ],
        )


class SimpleStatementTest(TestmonCoverageTest):
    def test_assert(self):
        self.check_human_coverage(
            """\
            assert (1 + 2)
            assert (1 +
                2)
            assert (1 + 2), 'the universe is broken'
            assert (1 +
                2), \\
                'something is amiss'
            """,
            [1, 2, 3, 4, 5, 6, 7],
            "",
        )

    def test_assignment(self):
        self.check_human_coverage(
            """\
            a = (1 + 2)
            b = (1 +
                2)
            c = \\
                1
            """,
            [1, 2, 3, 4, 5],
            "",
        )

    def test_assign_tuple(self):
        self.check_human_coverage(
            """\
            a = 1
            a,b,c = 7,8,9
            assert a == 7 and b == 8 and c == 9
            """,
            [1, 2, 3],
            "",
        )

    def test_more_assignments(self):
        self.check_human_coverage(
            """\
            x = []
            d = {}
            d[
                4 + len(x)
                + 5
            ] = \\
            d[
                8 ** 2
            ] = \\
                9
            """,
            [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
            "",
        )

    def test_attribute_assignment(self):
        self.check_human_coverage(
            """\
            class obj: pass
            o = obj()
            o.foo = (1 + 2)
            o.foo = (1 +
                2)
            o.foo = \\
                1
            """,
            [1, 2, 3, 4, 5, 6, 7],
            "",
        )

    def test_list_of_attribute_assignment(self):
        self.check_human_coverage(
            """\
            class obj: pass
            o = obj()
            o.a, o.b = (1 + 2), 3
            o.a, o.b = (1 +
                2), (3 +
                4)
            o.a, o.b = \\
                1, \\
                2
            """,
            [1, 2, 3, 4, 5, 6, 7, 8, 9],
            "",
        )

    def test_augmented_assignment(self):
        self.check_human_coverage(
            """\
            a = 1
            a += 1
            a += (1 +
                2)
            a += \\
                1
            """,
            [1, 2, 3, 4, 5, 6],
            "",
        )

    def test_pass(self):
        self.check_human_coverage(
            """\
            if 1==1:
                pass
            """,
            [1, 2],
            "",
        )
        self.check_human_coverage(
            """\
            def foo():
                pass
            foo()
            """,
            [1, 2, 3],
            "",
        )
        self.check_human_coverage(
            """\
            def foo():
                "doc"
                pass
            foo()
            """,
            [1, 2, 3, 4],
            "",
        )
        self.check_human_coverage(
            """\
            class Foo:
                def foo(self):
                    pass
            Foo().foo()
            """,
            [1, 2, 3, 4],
            "",
        )
        self.check_human_coverage(
            """\
            class Foo:
                def foo(self):
                    "Huh?"
                    pass
            Foo().foo()
            """,
            [1, 2, 3, 4, 5],
            "",
        )

    def test_del(self):
        self.check_human_coverage(
            """\
            d = { 'a': 1, 'b': 1, 'c': 1, 'd': 1, 'e': 1 }
            del d['a']
            del d[
                'b'
                ]
            del d['c'], \\
                d['d'], \\
                d['e']
            assert(len(d.keys()) == 0)
            """,
            [1, 2, 3, 4, 5, 6, 7, 8, 9],
            "",
        )

    def test_raise(self):
        self.check_human_coverage(
            """\
            try:
                raise Exception(
                    "hello %d" %
                    17)
            except:
                pass
            """,
            [1, 2, 3, 4, 5, 6],
            "",
        )

    def test_return(self):
        self.check_human_coverage(
            """\
            def fn():
                a = 1
                return a

            x = fn()
            assert(x == 1)
            """,
            [
                1,
                2,
                3,
                4,
                5,
                6,
            ],
            "",
        )
        self.check_human_coverage(
            """\
            def fn():
                a = 1
                return (
                    a +
                    1)

            x = fn()
            assert(x == 2)
            """,
            [1, 2, 3, 4, 5, 6, 7, 8],
            "",
        )
        self.check_human_coverage(
            """\
            def fn():
                a = 1
                return (a,
                    a + 1,
                    a + 2)

            x,y,z = fn()
            assert x == 1 and y == 2 and z == 3
            """,
            [1, 2, 3, 4, 5, 6, 7, 8],
            "",
        )

    def test_yield(self):
        self.check_human_coverage(
            """\
            def gen():
                yield 1
                yield (2+
                    3+
                    4)
                yield 1, \\
                    2
            a,b,c = gen()
            assert a == 1 and b == 9 and c == (1,2)
            """,
            [1, 2, 3, 4, 5, 6, 7, 8, 9],
            "",
        )

    def test_break(self):
        self.check_human_coverage(
            """\
            for x in range(10):
                a = 2 + x
                break
                a = 4
            assert a == 2
            """,
            [1, 2, 3, 5],
        )

    def test_continue(self):
        self.check_human_coverage(
            """\
            for x in range(10):
                a = 2 + x
                continue
                a = 4
            assert a == 11
            """,
            [1, 2, 3, 5],
        )

    def test_strange_unexecuted_continue(self):
        self.skipTest("Expected failure: peephole optimization of jumps to jumps")
        self.check_human_coverage(
            """\
            a = b = c = 0
            for n in range(100):
                if n % 2:
                    if n % 4:
                        a += 1
                    continue    # <-- This line may not be hit.
                else:
                    b += 1
                c += 1
            assert a == 50 and b == 50 and c == 50

            a = b = c = 0
            for n in range(100):
                if n % 2:
                    if n % 3:
                        a += 1
                    continue    # <-- This line is always hit.
                else:
                    b += 1
                c += 1
            assert a == 33 and b == 50 and c == 50
            """,
            [1, 2, 3, 4, 5, 6, 8, 9, 10, 12, 13, 14, 15, 16, 17, 19, 20, 21],
            "",
        )

    def test_import(self):
        self.check_human_coverage(
            """\
            import string
            from sys import path
            a = 1
            """,
            [1, 2, 3],
            "",
        )
        self.check_human_coverage(
            """\
            import string
            if 1 == 2:
                from sys import path
            a = 1
            """,
            [1, 2, 4],
        )
        self.check_human_coverage(
            """\
            import string, \\
                os, \\
                re
            from sys import path, \\
                stdout
            a = 1
            """,
            [1, 2, 3, 4, 5, 6],
            "",
        )
        self.check_human_coverage(
            """\
            import sys, sys as s
            assert s.path == sys.path
            """,
            [1, 2],
            "",
        )
        self.check_human_coverage(
            """\
            import sys, \\
                sys as s
            assert s.path == sys.path
            """,
            [1, 2, 3],
            "",
        )
        self.check_human_coverage(
            """\
            from sys import path, \\
                path as p
            assert p == path
            """,
            [1, 2, 3],
            "",
        )
        self.check_human_coverage(
            """\
            from sys import \\
                *
            assert len(path) > 0
            """,
            [1, 2, 3],
            "",
        )

    def test_global(self):
        self.check_human_coverage(
            """\
            g = h = i = 1
            def fn():
                global g
                global h, \\
                    i
                g = h = i = 2
            fn()
            assert g == 2 and h == 2 and i == 2
            """,
            [1, 2, 3, 4, 5, 6, 7, 8],
            "",
        )
        self.check_human_coverage(
            """\
            g = h = i = 1
            def fn():
                global g; g = 2
            fn()
            assert g == 2 and h == 1 and i == 1
            """,
            [1, 2, 3, 4, 5],
            "",
        )

        self.check_human_coverage(
            """\
            a = 0; b = 0
            try:
                a = 1
                raise IOError("foo")
            except ImportError:
                a = 99
            except IOError:
                a = 17
            except:
                a = 123
            finally:
                b = 2
            assert a == 17 and b == 2
            """,
            [1, 2, 3, 4, 5, 7, 8, 11, 12, 13],
        )
        self.check_human_coverage(
            """\
            a = 0; b = 0
            try:
                a = 1
            except:
                a = 99
            else:
                a = 123
            finally:
                b = 2
            assert a == 123 and b == 2
            """,
            [1, 2, 3, 6, 7, 8, 9, 10],
        )
        self.check_human_coverage(
            """\
            a = 0; b = 0
            try:
                a = 1
                raise Exception("foo")
            except:
                a = 99
            else:
                a = 123
            finally:
                b = 2
            assert a == 99 and b == 2
            """,
            [1, 2, 3, 4, 5, 6, 9, 10, 11],
        )


class NewTestmonCoverageTest:
    def parse(self, text):
        code = textwrap.dedent(text)
        tree = ast.parse(code)
        return tree, len(text.splitlines())

    def test_function_lines(self):
        tree, line_count = self.parse(
            """\
                def a():
                    1
                    2
                    3
                2
            """
        )
        assert (function_lines(tree, line_count)) == [(2, 4)]

    def test_function_lines_decorator(self):
        tree, line_count = self.parse(
            """\
                def a():
                    1
                    2
                    3
                @dec_b
                def b():
                    pass          
            """
        )
        assert (function_lines(tree, line_count)) == [(2, 4), (7, 8)]


class TestCoverageAssumptions(TestmonCoverageTest):
    def test_easy(self):
        for name, mod_cov in code_samples.items():
            if mod_cov.expected_coverage:
                coverage_lines, _ = self.write_and_run(mod_cov.source_code)
                assert (
                    sorted(coverage_lines) == mod_cov.expected_coverage
                ), "This is for code_sample['{}']".format(name)
