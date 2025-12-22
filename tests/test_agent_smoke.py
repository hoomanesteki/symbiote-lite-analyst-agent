"""
Smoke tests for the agent module.
These tests verify basic imports and module structure.
"""
import pytest


class TestAgentImports:
    """Test that all agent modules can be imported."""

    def test_agent_imports(self):
        """Test main agent module imports."""
        import symbiote_lite.agent
        assert hasattr(symbiote_lite.agent, "run_agent")

    def test_agent_core_imports(self):
        """Test agent_core module imports."""
        import symbiote_lite.agent_core
        assert hasattr(symbiote_lite.agent_core, "analyze_query")

    def test_tools_imports(self):
        """Test tools module imports."""
        from symbiote_lite.tools import DirectToolExecutor, MCPAgentAdapter
        assert DirectToolExecutor is not None
        assert MCPAgentAdapter is not None

    def test_sql_imports(self):
        """Test SQL module imports."""
        from symbiote_lite.sql import (
            execute_sql_query,
            build_sql,
            safe_select_only,
            detect_sql_injection,
        )
        assert execute_sql_query is not None
        assert build_sql is not None
        assert safe_select_only is not None
        assert detect_sql_injection is not None


class TestModuleStructure:
    """Test module structure and attributes."""

    def test_symbiote_lite_version(self):
        """Test that version is defined."""
        import symbiote_lite
        assert hasattr(symbiote_lite, "__version__")

    def test_symbiote_lite_exports(self):
        """Test main package exports."""
        from symbiote_lite import (
            run_agent,
            analyze_query,
            DirectToolExecutor,
            MCPAgentAdapter,
        )
        assert callable(run_agent)
        assert callable(analyze_query)


class TestAgentHelpers:
    """Test agent helper functions."""

    def test_detect_unsupported_query(self):
        """Test unsupported query detection."""
        from symbiote_lite.agent import detect_unsupported_query

        # Should detect unsupported patterns
        assert detect_unsupported_query("show hourly trips") is not None
        assert detect_unsupported_query("trips by location") is not None
        assert detect_unsupported_query("weekend vs weekday busier") is not None

        # Should allow supported patterns
        assert detect_unsupported_query("show trips in january") is None
        assert detect_unsupported_query("fare trends by week") is None

    def test_detect_multi_topic(self):
        """Test multi-topic detection."""
        from symbiote_lite.agent import detect_multi_topic

        # Should detect multiple topics
        result = detect_multi_topic("show trips and fares in january")
        assert result is not None
        assert "trips" in result
        assert "fares" in result

        # Should not flag single topic
        assert detect_multi_topic("show trips in january") is None

    def test_detect_sql_injection_in_agent(self):
        """Test SQL injection detection is available."""
        from symbiote_lite.sql.safety import detect_sql_injection

        assert detect_sql_injection("'; DROP TABLE users; --") is True
        assert detect_sql_injection("show trips in january") is False
