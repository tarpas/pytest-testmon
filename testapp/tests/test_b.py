from app.b import multiply, divide

class TestB:
    def test_multiply(self):
        """test multiplying"""
        assert multiply(1, 2) == 2

    def test_divide(self):
        """test division"""
        assert divide(1, 2) == 0
