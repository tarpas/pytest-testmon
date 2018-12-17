import pytest


@pytest.mark.parametrize("test_input", range(1000))
def test_eval(test_input):
    assert test_input == 5
