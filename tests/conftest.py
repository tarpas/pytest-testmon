import gc

import pytest

from tests.lib4tests import FLAVORS


class TestmonTestHooks:
    def pytest_testmon_flavors(self, flavors):
        """Extend how the tests using the `local_remote` fixture run.

        `flavors` maps a name to `factory(testdir) -> LocalRemote`; add to it. Implement with
        `@pytest.hookimpl(optionalhook=True)` so the plugin loads before this spec is declared.
        """


def pytest_addhooks(pluginmanager):
    pluginmanager.add_hookspecs(TestmonTestHooks)


def pytest_generate_tests(metafunc):
    if "local_remote" in metafunc.fixturenames:
        flavors = dict(FLAVORS)
        metafunc.config.hook.pytest_testmon_flavors(flavors=flavors)
        metafunc.parametrize(
            "local_remote", list(flavors.values()), ids=list(flavors), indirect=True
        )


@pytest.fixture(autouse=True)
def _collect_garbage():
    """Finalize what the test left behind while its warnings are still being captured.

    Under pytest a leaked sqlite connection is not finalized when the test returns but by a later
    garbage collection; collecting here makes its ResourceWarning fail this test (see filterwarnings
    in tox.ini) instead of surfacing at interpreter exit or in an unrelated later test.
    """
    yield
    gc.collect()
