"""
Tests for Phase base class — progress tracking, step counting, error collection.
"""

from unittest.mock import MagicMock

import pytest

from core.detector import SystemInfo
from core.logger import ForgeLogger
from core.runner import Runner
from phases import Phase


class ConcretePhase(Phase):
    """Concrete implementation for testing the base class."""
    name = "Test Phase"
    description = "A test phase"
    icon = "🧪"

    def __init__(self, *args, execute_fn=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._execute_fn = execute_fn

    def execute(self):
        if self._execute_fn:
            self._execute_fn(self)


@pytest.fixture
def mock_logger():
    logger = MagicMock(spec=ForgeLogger)
    logger.verbose = False
    return logger


@pytest.fixture
def mock_runner(mock_logger):
    return Runner(mock_logger, dry_run=True, verbose=False)


@pytest.fixture
def system_info():
    return SystemInfo()


def make_phase(mock_runner, mock_logger, system_info, execute_fn=None, config=None):
    """Helper to create a ConcretePhase with given execute function."""
    return ConcretePhase(
        runner=mock_runner,
        logger=mock_logger,
        config=config or {},
        system=system_info,
        execute_fn=execute_fn,
    )


class TestStepCounting:
    """Tests for step number tracking."""

    def test_steps_increment(self, mock_runner, mock_logger, system_info):
        def do_execute(phase):
            phase.step("First")
            phase.step("Second")
            phase.step("Third")

        phase = make_phase(mock_runner, mock_logger, system_info, do_execute)
        phase.run()

        assert phase._step_number == 3
        # Verify step calls include numbering
        calls = mock_logger.step.call_args_list
        assert "[1]" in calls[0][0][0]
        assert "[2]" in calls[1][0][0]
        assert "[3]" in calls[2][0][0]

    def test_step_counter_starts_at_zero(self, mock_runner, mock_logger, system_info):
        phase = make_phase(mock_runner, mock_logger, system_info)
        assert phase._step_number == 0


class TestResultTracking:
    """Tests for command result aggregation."""

    def test_results_track_dry_run(self, mock_runner, mock_logger, system_info):
        def do_execute(phase):
            phase.cmd("echo one", description="One")
            phase.cmd("echo two", description="Two")

        phase = make_phase(mock_runner, mock_logger, system_info, do_execute)
        results = phase.run()

        # In dry-run mode, commands report as skipped (success=True, skipped=True)
        # but Phase.cmd() counts skipped results separately
        total = results["passed"] + results["skipped"]
        assert total == 2
        assert results["failed"] == 0

    def test_run_returns_results_dict(self, mock_runner, mock_logger, system_info):
        phase = make_phase(mock_runner, mock_logger, system_info)
        results = phase.run()

        assert isinstance(results, dict)
        assert "passed" in results
        assert "failed" in results
        assert "skipped" in results


class TestFailedStepCollection:
    """Tests for failed step tracking."""

    def test_failed_steps_empty_initially(self, mock_runner, mock_logger, system_info):
        phase = make_phase(mock_runner, mock_logger, system_info)
        assert phase._failed_steps == []

    def test_failed_steps_collected(self, mock_runner, mock_logger, system_info):
        """When running in non-dry-run mode with failing commands."""
        real_runner = Runner(mock_logger, dry_run=False, verbose=False)

        def do_execute(phase):
            phase.cmd("exit 1", description="Failing step")
            phase.cmd("exit 2", description="Another failure")

        phase = make_phase(real_runner, mock_logger, system_info, do_execute)
        results = phase.run()

        assert results["failed"] == 2
        assert len(phase._failed_steps) == 2
        assert phase._failed_steps[0][0] == "Failing step"
        assert phase._failed_steps[1][0] == "Another failure"


class TestSkipLogic:
    """Tests for phase skip behavior."""

    def test_should_skip_default_false(self, mock_runner, mock_logger, system_info):
        phase = make_phase(mock_runner, mock_logger, system_info)
        assert phase.should_skip() is False

    def test_skipped_phase_returns_results(self, mock_runner, mock_logger, system_info):
        class SkippablePhase(ConcretePhase):
            def should_skip(self):
                return True

        phase = SkippablePhase(
            runner=mock_runner,
            logger=mock_logger,
            config={},
            system=system_info,
        )
        results = phase.run()

        assert results["passed"] == 0
        assert results["failed"] == 0
        mock_logger.skip.assert_called_once()


class TestCfgAccessor:
    """Tests for config key traversal."""

    def test_deep_access(self, mock_runner, mock_logger, system_info):
        config = {"a": {"b": {"c": 42}}}
        phase = make_phase(mock_runner, mock_logger, system_info, config=config)

        assert phase.cfg("a", "b", "c") == 42

    def test_missing_key_returns_default(self, mock_runner, mock_logger, system_info):
        config = {"a": 1}
        phase = make_phase(mock_runner, mock_logger, system_info, config=config)

        assert phase.cfg("b", default="fallback") == "fallback"
        assert phase.cfg("a", "deep", default=None) is None

    def test_empty_config(self, mock_runner, mock_logger, system_info):
        phase = make_phase(mock_runner, mock_logger, system_info, config={})
        assert phase.cfg("anything", default="nope") == "nope"
