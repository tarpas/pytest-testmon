from project import a_file
import out

#
def test_a():
    b()


def b():
    a_file.a()


def test_outside():
    out.m_out()
