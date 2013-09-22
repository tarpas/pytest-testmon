import unittest

from ..a import add, subtract
import time

class TestA(unittest.TestCase):
    # @unittest.skip('')
    def test_add(self):
        """test adding"""
        self.assertEqual(add(1, 2), 3)

    def test_subtract(self):
        """test subtracting"""
        time.sleep(2)
        self.assertEqual(subtract(1, 2), -1)
