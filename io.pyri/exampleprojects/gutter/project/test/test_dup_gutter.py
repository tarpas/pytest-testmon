def exc(s):
    raise Exception(s)


def half_way(s):
    exc(s)

def caller(m, s):
    m(s)

def mid_1(m, s):
    caller(m, s)

def test_1():
    mid_1(half_way, "Exception test 1 longer")




def mid_2(m, s):
    caller(m, s)

def mid_22(m, s):
    mid_2(m, s)

def test_2():
    # caller(half_way, "Exception")
    mid_22(half_way, "Exception test 2")