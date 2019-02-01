from . import a_file


def test_a():
    b()


def b():
    a_file.a()


