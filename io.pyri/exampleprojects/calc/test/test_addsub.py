# If you get testmon errors
# Run this file with pytest -m 'notestmon' -p no:testmon
# import pytest
# import unittest

from ..addsub import add, subtract, multiply, divide

def test_add():
    assert add(1, 2) == 3

def test_substract():
    assert subtract(5, 3) == 2

def test_multiply():
    assert multiply(5, 3) == 15

def test_divide():
    assert divide(6, 3) == 2
