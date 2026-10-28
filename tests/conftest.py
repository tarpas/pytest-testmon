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
