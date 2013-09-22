from app.a import add
from app.b import multiply

def test_add_and_multiply():
    assert add(2, 3) == 5
    assert multiply(2, 3) == 6
