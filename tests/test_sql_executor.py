"""
Tests for the SQL executor module.
Covers database connection and query execution.
"""
import pytest
import sqlite3
from pathlib import Path

from symbiote_lite.sql.executor import execute_sql_query, _default_db_path


class TestExecuteSQLQuery:
    """Test SQL query execution."""

    def test_executor_missing_db(self, tmp_path):
        """Test error when database doesn't exist."""
        fake_db = tmp_path / "missing.sqlite"
        with pytest.raises(FileNotFoundError):
            execute_sql_query("SELECT 1;", db_path=fake_db)

    def test_executor_with_valid_db(self, tmp_path):
        """Test execution with valid database."""
        # Create a test database
        db_path = tmp_path / "test.sqlite"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE test (id INTEGER, value TEXT)")
        conn.execute("INSERT INTO test VALUES (1, 'hello')")
        conn.commit()
        conn.close()

        # Execute query
        df = execute_sql_query("SELECT * FROM test", db_path=db_path)
        
        assert len(df) == 1
        assert df.iloc[0]["id"] == 1
        assert df.iloc[0]["value"] == "hello"

    def test_executor_returns_dataframe(self, tmp_path):
        """Test that executor returns pandas DataFrame."""
        import pandas as pd
        
        # Create a test database
        db_path = tmp_path / "test.sqlite"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE test (x INTEGER)")
        conn.execute("INSERT INTO test VALUES (1), (2), (3)")
        conn.commit()
        conn.close()

        df = execute_sql_query("SELECT * FROM test", db_path=db_path)
        
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 3

    def test_executor_empty_result(self, tmp_path):
        """Test execution with empty result."""
        db_path = tmp_path / "test.sqlite"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE test (id INTEGER)")
        conn.commit()
        conn.close()

        df = execute_sql_query("SELECT * FROM test", db_path=db_path)
        
        assert len(df) == 0

    def test_executor_aggregation(self, tmp_path):
        """Test aggregation queries."""
        db_path = tmp_path / "test.sqlite"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE sales (amount REAL)")
        conn.execute("INSERT INTO sales VALUES (10), (20), (30)")
        conn.commit()
        conn.close()

        df = execute_sql_query("SELECT SUM(amount) as total FROM sales", db_path=db_path)
        
        assert df.iloc[0]["total"] == 60

    def test_executor_invalid_sql(self, tmp_path):
        """Test error on invalid SQL."""
        db_path = tmp_path / "test.sqlite"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE test (id INTEGER)")
        conn.commit()
        conn.close()

        with pytest.raises(Exception):
            execute_sql_query("INVALID SQL SYNTAX", db_path=db_path)

    def test_executor_missing_table(self, tmp_path):
        """Test error on missing table."""
        db_path = tmp_path / "test.sqlite"
        conn = sqlite3.connect(str(db_path))
        conn.commit()
        conn.close()

        with pytest.raises(Exception):
            execute_sql_query("SELECT * FROM nonexistent", db_path=db_path)


class TestDefaultDbPath:
    """Test default database path resolution."""

    def test_default_path_returns_path(self):
        """Test default path returns a Path object."""
        path = _default_db_path()
        assert isinstance(path, Path)

    def test_default_path_ends_with_sqlite(self):
        """Test default path ends with .sqlite."""
        path = _default_db_path()
        assert path.suffix == ".sqlite"

    def test_env_override(self, monkeypatch, tmp_path):
        """Test environment variable override."""
        custom_path = tmp_path / "custom.sqlite"
        monkeypatch.setenv("SYMBIOTE_DB_PATH", str(custom_path))
        
        path = _default_db_path()
        assert path == custom_path


class TestDatabaseSchema:
    """Test expected database schema (integration-like tests)."""

    @pytest.fixture
    def sample_db(self, tmp_path):
        """Create a sample database with expected schema."""
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
        
        # Insert sample data
        conn.execute("""
            INSERT INTO taxi_trips 
            (pickup_datetime, dropoff_datetime, vendor_id, fare_amount, tip_amount, total_amount)
            VALUES 
            ('2022-01-15 10:00:00', '2022-01-15 10:30:00', 'VTS', 25.50, 5.00, 32.00),
            ('2022-01-15 11:00:00', '2022-01-15 11:45:00', 'CMT', 35.00, 7.00, 45.00),
            ('2022-01-16 09:00:00', '2022-01-16 09:20:00', 'VTS', 15.00, 3.00, 19.50)
        """)
        conn.commit()
        conn.close()
        
        return db_path

    def test_trip_count_query(self, sample_db):
        """Test trip counting query."""
        df = execute_sql_query(
            "SELECT COUNT(*) as trips FROM taxi_trips",
            db_path=sample_db
        )
        assert df.iloc[0]["trips"] == 3

    def test_date_filter_query(self, sample_db):
        """Test date filtering query."""
        df = execute_sql_query(
            """
            SELECT COUNT(*) as trips FROM taxi_trips
            WHERE pickup_datetime >= '2022-01-15'
              AND pickup_datetime < '2022-01-16'
            """,
            db_path=sample_db
        )
        assert df.iloc[0]["trips"] == 2

    def test_vendor_grouping_query(self, sample_db):
        """Test vendor grouping query."""
        df = execute_sql_query(
            """
            SELECT vendor_id, COUNT(*) as trips 
            FROM taxi_trips 
            GROUP BY vendor_id
            ORDER BY trips DESC
            """,
            db_path=sample_db
        )
        assert len(df) == 2
        assert df.iloc[0]["vendor_id"] == "VTS"
        assert df.iloc[0]["trips"] == 2

    def test_aggregation_query(self, sample_db):
        """Test aggregation queries."""
        df = execute_sql_query(
            """
            SELECT 
                AVG(fare_amount) as avg_fare,
                SUM(fare_amount) as total_fare,
                AVG(tip_amount) as avg_tip
            FROM taxi_trips
            """,
            db_path=sample_db
        )
        assert df.iloc[0]["avg_fare"] == pytest.approx(25.17, rel=0.01)
        assert df.iloc[0]["total_fare"] == pytest.approx(75.50, rel=0.01)
