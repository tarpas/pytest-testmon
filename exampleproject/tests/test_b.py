import unittest

from ..b import divide, multiply


class TestB(unittest.TestCase):
    def test_multiply(self):
        """test multiplying"""
        self.assertEqual(multiply(1, 2), 2)

    def test_divide(self):
        """test division"""
        self.assertEqual(divide(1, 2), 0)
