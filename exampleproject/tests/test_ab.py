import unittest

from ..a import add
from ..b import multiply

# what s
class TestAB(unittest.TestCase):
    def test_add_and_multiply(self):
        """test adding and multiplying at the same time"""
        self.assertEqual(add(2, 3), 5)
        self.assertEqual(multiply(2, 3), 6)
