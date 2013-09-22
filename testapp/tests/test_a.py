from app.a import add, subtract

def test_add():
    """test adding"""
    assert add(1, 2) == 3 

def test_subtract():
    """test subtracting"""
    assert subtract(1, 2) == -1
