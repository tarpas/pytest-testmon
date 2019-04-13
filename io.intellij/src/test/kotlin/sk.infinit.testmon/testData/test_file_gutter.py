
def a():
    raise Exception('some exception')

def b():
    a()

def test_a():
    b()
