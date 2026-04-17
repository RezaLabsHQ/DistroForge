"""
Tests for config loading — deep merge, fallback, and validation.
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import patch, mock_open

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestDeepMerge:
    """Tests for the _deep_merge utility function."""

    def setup_method(self):
        """Import the function fresh for each test."""
        from distroforge import _deep_merge
        self.merge = _deep_merge

    def test_simple_override(self):
        base = {"a": 1, "b": 2}
        override = {"b": 3}
        result = self.merge(base, override)
        assert result == {"a": 1, "b": 3}

    def test_nested_merge(self):
        base = {"user": {"name": "Default", "email": "default@example.com"}}
        override = {"user": {"email": "hamid@rezalabs.com"}}
        result = self.merge(base, override)
        assert result["user"]["name"] == "Default"
        assert result["user"]["email"] == "hamid@rezalabs.com"

    def test_deeply_nested_merge(self):
        base = {
            "dev": {
                "node": {"manager": "fnm", "version": "lts"},
                "python": {"manager": "pyenv", "version": "3.12"},
            }
        }
        override = {
            "dev": {
                "node": {"version": "22"},
            }
        }
        result = self.merge(base, override)
        assert result["dev"]["node"]["manager"] == "fnm"  # kept from base
        assert result["dev"]["node"]["version"] == "22"    # overridden
        assert result["dev"]["python"]["version"] == "3.12"  # untouched

    def test_list_replaced_not_appended(self):
        base = {"plugins": ["git", "docker"]}
        override = {"plugins": ["git", "node", "python"]}
        result = self.merge(base, override)
        assert result["plugins"] == ["git", "node", "python"]

    def test_new_keys_added(self):
        base = {"a": 1}
        override = {"b": 2}
        result = self.merge(base, override)
        assert result == {"a": 1, "b": 2}

    def test_empty_override(self):
        base = {"a": 1, "b": 2}
        result = self.merge(base, {})
        assert result == {"a": 1, "b": 2}

    def test_empty_base(self):
        override = {"a": 1}
        result = self.merge({}, override)
        assert result == {"a": 1}

    def test_both_empty(self):
        result = self.merge({}, {})
        assert result == {}

    def test_base_not_mutated(self):
        base = {"a": 1, "nested": {"b": 2}}
        override = {"a": 99, "nested": {"c": 3}}
        self.merge(base, override)
        assert base["a"] == 1  # original unchanged
        assert "c" not in base["nested"]  # original unchanged

    def test_override_dict_replaces_scalar(self):
        base = {"a": "string"}
        override = {"a": {"key": "value"}}
        result = self.merge(base, override)
        assert result["a"] == {"key": "value"}

    def test_override_scalar_replaces_dict(self):
        base = {"a": {"key": "value"}}
        override = {"a": "string"}
        result = self.merge(base, override)
        assert result["a"] == "string"


class TestConfigPhaseAccess:
    """Tests for the Phase.cfg() config accessor."""

    def test_cfg_nested_access(self):
        from phases import Phase
        from unittest.mock import MagicMock

        # Create a concrete subclass to test the base class method
        class TestPhase(Phase):
            name = "test"
            description = "test"
            def execute(self):
                pass

        phase = TestPhase.__new__(TestPhase)
        phase.config = {
            "dev": {
                "node": {"manager": "fnm", "version": "lts"},
                "docker": True,
            },
            "gaming": {"enabled": False},
        }

        assert phase.cfg("dev", "docker") is True
        assert phase.cfg("dev", "node", "manager") == "fnm"
        assert phase.cfg("gaming", "enabled") is False
        assert phase.cfg("nonexistent", default="fallback") == "fallback"
        assert phase.cfg("dev", "nonexistent", "deep", default=None) is None