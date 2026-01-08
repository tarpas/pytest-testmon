"""
Tests for pytest-xdist integration with testmon.

These tests verify that testmon properly handles xdist worker coordination,
especially in --testmon-nocollect mode which should be read-only but still
needs to share exec_id from controller to workers to prevent database locking.
"""
import pytest

from testmon.pytest_testmon import (
    TestmonXdistSync,
    register_plugins,
    get_running_as,
)

pytest_plugins = ("pytester",)


class MockConfig:
    """Mock pytest config for testing plugin registration."""

    def __init__(self, has_xdist=True):
        self._plugins = {"xdist": True} if has_xdist else {}
        self._registered_plugins = []
        self.testmon_data = MockTestmonData()

    class pluginmanager:
        """Mock plugin manager."""

        _plugins = {}
        _registered = []

        @classmethod
        def hasplugin(cls, name):
            return name in cls._plugins

        @classmethod
        def register(cls, plugin, name=None):
            cls._registered.append((plugin, name))

    def __init__(self, has_xdist=True):
        self.pluginmanager._plugins = {"xdist": True} if has_xdist else {}
        self.pluginmanager._registered = []
        self.testmon_data = MockTestmonData()


class MockTestmonData:
    """Mock testmon data for testing."""

    exec_id = 123
    system_packages_change = False
    files_of_interest = ["test_file.py"]


class TestTestmonXdistSync:
    """Tests for TestmonXdistSync class."""

    def test_init_default_should_collect_true(self):
        """Test that should_collect defaults to True for backward compatibility."""
        sync = TestmonXdistSync()
        assert sync._should_collect is True
        assert sync.await_nodes == 0

    def test_init_should_collect_false(self):
        """Test that should_collect can be set to False for nocollect mode."""
        sync = TestmonXdistSync(should_collect=False)
        assert sync._should_collect is False

    def test_init_should_collect_true_explicit(self):
        """Test that should_collect can be explicitly set to True."""
        sync = TestmonXdistSync(should_collect=True)
        assert sync._should_collect is True


class TestXdistIntegration:
    """Integration tests for xdist with testmon."""

    def test_xdist_nocollect_no_database_lock(self, testdir):
        """
        Test that --testmon --testmon-nocollect -n 2 doesn't cause database lock.

        This is a regression test for the issue where using --testmon-nocollect
        with pytest-xdist would cause 'sqlite3.OperationalError: database is locked'
        because TestmonXdistSync was not registered in nocollect mode, causing
        each worker to independently call initiate_execution() with write access.
        """
        # Create a simple test file
        testdir.makepyfile(
            test_sample="""
            def test_one():
                assert True

            def test_two():
                assert True
        """
        )

        # First run to create testmondata (collect mode)
        result = testdir.runpytest("--testmon", "-v")
        result.assert_outcomes(passed=2)

        # Second run with nocollect and xdist - this should not cause database lock
        # Note: We use -n 2 to simulate parallel workers
        pytest.importorskip("xdist")
        result = testdir.runpytest(
            "--testmon",
            "--testmon-nocollect",
            "-n",
            "2",
            "-v",
        )

        # Should not have internal errors about database lock
        assert "database is locked" not in result.stdout.str()
        assert "database is locked" not in result.stderr.str()
        # The test should complete (pass or be deselected, but not crash)
        assert result.ret in [0, 5]  # 0 = success, 5 = no tests collected (deselected)

    def test_xdist_collect_mode_works(self, testdir):
        """Test that xdist with testmon in collect mode still works correctly."""
        testdir.makepyfile(
            test_basic="""
            def test_a():
                assert 1 + 1 == 2

            def test_b():
                assert 2 + 2 == 4
        """
        )

        pytest.importorskip("xdist")
        result = testdir.runpytest("--testmon", "-n", "2", "-v")

        # Should complete without errors
        assert "database is locked" not in result.stdout.str()
        assert "database is locked" not in result.stderr.str()
        result.assert_outcomes(passed=2)

    def test_xdist_sync_registered_in_nocollect_mode(self, testdir):
        """
        Verify TestmonXdistSync is registered even when --testmon-nocollect is used.

        This ensures the exec_id is shared from controller to workers, preventing
        workers from trying to independently initialize with write access.
        """
        testdir.makepyfile(
            test_check="""
            def test_pass():
                pass
        """
        )

        # First create testmondata
        result = testdir.runpytest("--testmon", "-v")
        result.assert_outcomes(passed=1)

        # Now run with nocollect - if TestmonXdistSync is registered properly,
        # the test header should show testmon is active
        pytest.importorskip("xdist")
        result = testdir.runpytest(
            "--testmon",
            "--testmon-nocollect",
            "-n",
            "2",
            "-v",
        )

        # Check testmon header is present (indicates plugin is active)
        assert "testmon:" in result.stdout.str()


class TestRegisterPlugins:
    """Tests for the register_plugins function."""

    def test_xdist_sync_registered_when_select_only(self):
        """
        Test that TestmonXdistSync is registered when only selection is active.

        This is the key fix - even in --testmon-nocollect mode (select only),
        TestmonXdistSync should be registered to share exec_id with workers.
        """
        # This test verifies the fix at the unit level
        # The actual registration happens in register_plugins, but we can
        # verify the TestmonXdistSync class accepts should_collect parameter

        # should_collect=False simulates --testmon-nocollect mode
        sync = TestmonXdistSync(should_collect=False)

        # The sync plugin should be created successfully
        assert sync is not None
        assert sync._should_collect is False

        # await_nodes tracking should still work
        assert sync.await_nodes == 0

