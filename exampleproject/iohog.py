import os

PATH = '/tmp/foo.bar'


def touch_file(i):
    """
    This is just a simple demonstration of IO heavy task.

    The purpose is to compare the performance when executed
    by Testmon vs standard unittest runner.
    """
    for i in range(i):
        os.system('touch %s' % PATH)
        with open(PATH, 'a'):
            os.utime(PATH, None)
        os.remove(PATH)
