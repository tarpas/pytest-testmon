import unittest

import pytest

from ..a import add, subtract
from ..d import always_fail


class TestAUnittest(unittest.TestCase):
    @unittest.skip('')
    def test_add(self):
        """test adding"""
        self.assertEqual(add(1, 2), 3)

    def test_subtract(self):
        """test subtracting"""
        pass
        self.assertEqual(subtract(1 , 2), -1)

    @pytest.mark.xfail(True, reason="Division by zero not implemented yet.")
    def test_always_fail(self):
        pass
        always_fail()

    def test_skip_always_fail(self):
        return
        always_fail()
