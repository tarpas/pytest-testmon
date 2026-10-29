import gc
import warnings

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
def _no_leaked_connections():
    """Fail the test that leaked a sqlite connection.

    Under pytest a leaked connection is not finalized when the test returns but by a later garbage
    collection, so its ResourceWarning would surface at interpreter exit or in an unrelated test.
    Collecting here, with the warning recorded only for the duration of the collection, pins it on
    the right test without a process-wide warning filter (which in-process pytester runs inherit).
    """
    yield
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", ResourceWarning)
        gc.collect()
    leaks = [str(w.message) for w in caught if "unclosed database" in str(w.message)]
    assert not leaks, f"leaked sqlite connections: {leaks}"
