"""
Tests for MCP (Model Context Protocol) integration.
Covers tool executor and agent adapter.
"""
import pytest
import sqlite3
from pathlib import Path

from symbiote_lite.tools.executor import DirectToolExecutor
from symbiote_lite.tools.agent_adapter import MCPAgentAdapter


class TestDirectToolExecutor:
    """Test the DirectToolExecutor class."""

    @pytest.fixture
    def executor(self):
        """Create executor instance."""
        return DirectToolExecutor()

    @pytest.fixture
    def sample_db(self, tmp_path, monkeypatch):
        """Create sample database and set env var."""
        db_path = tmp_path / "taxi_trips.sqlite"
        conn = sqlite3.connect(str(db_path))
        
        conn.execute("""
            CREATE TABLE taxi_trips (
                id INTEGER PRIMARY KEY,
                pickup_datetime TEXT,
                dropoff_datetime TEXT,
                vendor_id TEXT,
                fare_amount REAL,
                tip_amount REAL,
                total_amount REAL
            )
        """)
        
        conn.execute("""
            INSERT INTO taxi_trips 
            (pickup_datetime, dropoff_datetime, vendor_id, fare_amount, tip_amount, total_amount)
            VALUES 
            ('2022-01-15 10:00:00', '2022-01-15 10:30:00', 'VTS', 25.50, 5.00, 32.00),
            ('2022-01-15 11:00:00', '2022-01-15 11:45:00', 'CMT', 35.00, 7.00, 45.00)
        """)
        conn.commit()
        conn.close()
        
        monkeypatch.setenv("SYMBIOTE_DB_PATH", str(db_path))
        return db_path

    def test_execute_sql_returns_dict(self, executor, sample_db):
        """Test execute_sql returns dictionary."""
        result = executor.execute_sql("SELECT 1 AS test")
        
        assert isinstance(result, dict)
        assert "success" in result
        assert "rows" in result
        assert "row_count" in result
        assert "columns" in result

    def test_execute_sql_success_flag(self, executor, sample_db):
        """Test success flag is True for valid queries."""
        result = executor.execute_sql("SELECT 1 AS test")
        assert result["success"] is True

    def test_execute_sql_rows_format(self, executor, sample_db):
        """Test rows are in dict format."""
        result = executor.execute_sql("SELECT * FROM taxi_trips")
        
        assert isinstance(result["rows"], list)
        assert len(result["rows"]) == 2
        assert isinstance(result["rows"][0], dict)

    def test_execute_sql_row_count(self, executor, sample_db):
        """Test row count is correct."""
        result = executor.execute_sql("SELECT * FROM taxi_trips")
        assert result["row_count"] == 2

    def test_execute_sql_columns(self, executor, sample_db):
        """Test columns are returned."""
        result = executor.execute_sql("SELECT vendor_id, fare_amount FROM taxi_trips")
        
        assert "vendor_id" in result["columns"]
        assert "fare_amount" in result["columns"]

    def test_execute_sql_dataframe_included(self, executor, sample_db):
        """Test DataFrame is included in result."""
        import pandas as pd
        
        result = executor.execute_sql("SELECT * FROM taxi_trips")
        
        assert "dataframe" in result
        assert isinstance(result["dataframe"], pd.DataFrame)

    def test_execute_sql_blocks_drop(self, executor, sample_db):
        """Test DROP queries are blocked."""
        with pytest.raises(ValueError):
            executor.execute_sql("DROP TABLE taxi_trips")

    def test_execute_sql_blocks_delete(self, executor, sample_db):
        """Test DELETE queries are blocked."""
        with pytest.raises(ValueError):
            executor.execute_sql("DELETE FROM taxi_trips")

    def test_execute_sql_blocks_insert(self, executor, sample_db):
        """Test INSERT queries are blocked."""
        with pytest.raises(ValueError):
            executor.execute_sql("INSERT INTO taxi_trips VALUES (1,2,3,4,5,6,7)")

    def test_execute_sql_blocks_update(self, executor, sample_db):
        """Test UPDATE queries are blocked."""
        with pytest.raises(ValueError):
            executor.execute_sql("UPDATE taxi_trips SET fare_amount = 0")

    def test_execute_sql_to_dataframe(self, executor, sample_db):
        """Test execute_sql_to_dataframe method."""
        import pandas as pd
        
        df = executor.execute_sql_to_dataframe("SELECT * FROM taxi_trips")
        
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2

    def test_execute_sql_empty_result(self, executor, sample_db):
        """Test empty result handling."""
        result = executor.execute_sql(
            "SELECT * FROM taxi_trips WHERE vendor_id = 'NONEXISTENT'"
        )
        
        assert result["success"] is True
        assert result["rows"] == []
        assert result["row_count"] == 0


class TestMCPAgentAdapter:
    """Test the MCPAgentAdapter class."""

    @pytest.fixture
    def adapter(self):
        """Create adapter instance."""
        return MCPAgentAdapter()

    @pytest.fixture
    def sample_db(self, tmp_path, monkeypatch):
        """Create sample database."""
        db_path = tmp_path / "taxi_trips.sqlite"
        conn = sqlite3.connect(str(db_path))
        
        conn.execute("""
            CREATE TABLE taxi_trips (
                id INTEGER PRIMARY KEY,
                pickup_datetime TEXT,
                dropoff_datetime TEXT,
                vendor_id TEXT,
                fare_amount REAL,
                tip_amount REAL,
                total_amount REAL
            )
        """)
        
        conn.execute("""
            INSERT INTO taxi_trips 
            (pickup_datetime, dropoff_datetime, vendor_id, fare_amount, tip_amount, total_amount)
            VALUES 
            ('2022-01-15 10:00:00', '2022-01-15 10:30:00', 'VTS', 25.50, 5.00, 32.00)
        """)
        conn.commit()
        conn.close()
        
        monkeypatch.setenv("SYMBIOTE_DB_PATH", str(db_path))
        return db_path

    def test_adapter_has_executor(self, adapter):
        """Test adapter has executor instance."""
        assert hasattr(adapter, "executor")
        assert isinstance(adapter.executor, DirectToolExecutor)

    def test_adapter_execute_sql(self, adapter, sample_db):
        """Test adapter execute_sql method."""
        result = adapter.execute_sql("SELECT * FROM taxi_trips")
        
        assert result["success"] is True
        assert len(result["rows"]) == 1

    def test_adapter_execute_sql_safety(self, adapter, sample_db):
        """Test adapter enforces SQL safety."""
        with pytest.raises(ValueError):
            adapter.execute_sql("DROP TABLE taxi_trips")


class TestMCPBoundary:
    """Test MCP boundary enforcement."""

    def test_all_execution_through_tool(self):
        """Verify agent.py uses tool executor."""
        from pathlib import Path
        
        # Read agent.py
        agent_path = Path(__file__).parent.parent / "symbiote_lite" / "agent.py"
        if agent_path.exists():
            content = agent_path.read_text()
            
            # Check for MCP integration markers
            assert "DirectToolExecutor" in content
            assert "_execute_via_mcp" in content or "_tool_executor" in content

    def test_agent_core_uses_tool(self):
        """Verify agent_core.py uses tool executor."""
        from pathlib import Path
        
        agent_core_path = Path(__file__).parent.parent / "symbiote_lite" / "agent_core.py"
        if agent_core_path.exists():
            content = agent_core_path.read_text()
            
            # Check for MCP integration
            assert "DirectToolExecutor" in content or "_tool_executor" in content


class TestMCPOutputFormat:
    """Test MCP output format compliance."""

    @pytest.fixture
    def executor(self):
        return DirectToolExecutor()

    @pytest.fixture
    def sample_db(self, tmp_path, monkeypatch):
        db_path = tmp_path / "test.sqlite"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE test (id INTEGER, name TEXT)")
        conn.execute("INSERT INTO test VALUES (1, 'Alice'), (2, 'Bob')")
        conn.commit()
        conn.close()
        monkeypatch.setenv("SYMBIOTE_DB_PATH", str(db_path))
        return db_path

    def test_output_is_json_serializable(self, executor, sample_db):
        """Test output can be JSON serialized."""
        import json
        
        result = executor.execute_sql("SELECT * FROM test")
        
        # Remove DataFrame (not JSON serializable)
        json_safe = {k: v for k, v in result.items() if k != "dataframe"}
        
        # Should not raise
        json_str = json.dumps(json_safe)
        assert len(json_str) > 0

    def test_rows_are_records_format(self, executor, sample_db):
        """Test rows are in records format (list of dicts)."""
        result = executor.execute_sql("SELECT id, name FROM test")
        
        rows = result["rows"]
        assert isinstance(rows, list)
        assert all(isinstance(r, dict) for r in rows)
        assert rows[0] == {"id": 1, "name": "Alice"}
        assert rows[1] == {"id": 2, "name": "Bob"}
