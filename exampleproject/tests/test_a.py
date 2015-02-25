import unittest

from ..a import add, subtract
from ..d import always_fail
import time
import pytest


class TestA(unittest.TestCase):
    # @unittest.skip('')
    def test_add(self):
        """test adding"""
        self.assertEqual(add(1, 2), 3)

    def test_subtract(self):
        """test subtracting"""
        self.assertEqual(subtract(1, 2), -1)
        
    @pytest.mark.xfail(True, reason="Division by zero not implemented yet.")
    def test_always_fail(self):
        always_fail()
        
    @pytest.mark.skipif(True, reason="Not available on this platform")
    def test_skip_always_fail(self):
        always_fail()

