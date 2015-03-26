def add(a, b):
    return a + b

def subtract(a, b):
    return a - b

def test_add():
    assert add(1, 2) == 3

def test_subtract():
    assert subtract(4, 3) == 1

def test_both():
    assert add(1, 3) == 4
    assert subtract (2, 1) == 1
