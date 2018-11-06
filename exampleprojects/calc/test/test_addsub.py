# If you get testmon errors
# Run this file with pytest -m 'notestmon' -p no:testmon
# import pytest
# import unittest

from ..addsub import add, subtract


def test_add():
    assert add(1, 2) == 3

def test_subtract():
    assert subtract(5, 3) == 2
