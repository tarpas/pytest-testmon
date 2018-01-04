import unittest

import pytest

from ..a import add, subtract
from ..b import multiply, divide
from ..d import always_fail


def test_add():
    assert add(1, 2) == 3

def test_subtract():
    assert subtract(1 , 2) == -1

def test_add_and_multiply():
    assert add(multiply(2, 1), 1) == 3

def test_error3():
    pass


@pytest.mark.xfail(True, reason="Division by zero not implemented yet.")
def test_always_fail(self):
    always_fail()

def test_skip_always_fail():
    return
    always_fail()
