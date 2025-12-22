"""
Pytest configuration and shared fixtures.
"""
import pytest
import sqlite3
from pathlib import Path


@pytest.fixture
def project_root():
    """Return project root directory."""
    return Path(__file__).parent.parent


@pytest.fixture
def temp_db(tmp_path):
    """Create a temporary SQLite database."""
    db_path = tmp_path / "test.sqlite"
    conn = sqlite3.connect(str(db_path))
    yield db_path, conn
    conn.close()


@pytest.fixture
def taxi_db(tmp_path, monkeypatch):
    """
    Create a temporary taxi_trips database with sample data.
    Sets SYMBIOTE_DB_PATH environment variable.
    """
    db_path = tmp_path / "taxi_trips.sqlite"
    conn = sqlite3.connect(str(db_path))
    
    # Create schema
    conn.execute("""
        CREATE TABLE taxi_trips (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pickup_datetime TEXT NOT NULL,
            dropoff_datetime TEXT NOT NULL,
            vendor_id TEXT NOT NULL,
            fare_amount REAL NOT NULL,
            tip_amount REAL NOT NULL,
            total_amount REAL NOT NULL
        )
    """)
    
    # Insert sample data
    sample_data = [
        ('2022-01-15 10:00:00', '2022-01-15 10:30:00', 'VTS', 25.50, 5.00, 32.00),
        ('2022-01-15 11:00:00', '2022-01-15 11:45:00', 'CMT', 35.00, 7.00, 45.00),
        ('2022-01-16 09:00:00', '2022-01-16 09:20:00', 'VTS', 15.00, 3.00, 19.50),
        ('2022-01-16 14:00:00', '2022-01-16 14:25:00', 'DDS', 20.00, 4.00, 25.50),
        ('2022-02-01 08:00:00', '2022-02-01 08:40:00', 'VTS', 30.00, 6.00, 38.00),
    ]
    
    conn.executemany("""
        INSERT INTO taxi_trips 
        (pickup_datetime, dropoff_datetime, vendor_id, fare_amount, tip_amount, total_amount)
        VALUES (?, ?, ?, ?, ?, ?)
    """, sample_data)
    
    conn.commit()
    conn.close()
    
    # Set environment variable
    monkeypatch.setenv("SYMBIOTE_DB_PATH", str(db_path))
    
    return db_path


@pytest.fixture
def sample_state():
    """Create a sample session state."""
    from datetime import datetime
    
    return {
        "intent": "trip_frequency",
        "start_date": datetime(2022, 1, 1),
        "end_date": datetime(2022, 2, 1),
        "granularity": "daily",
        "metric": None,
        "limit": None,
        "_saw_invalid_iso_date": False,
        "_invalid_dates": [],
        "_last_query_context": None,
        "_last_suggestions": [],
        "_query_count": 0,
        "_last_sql": None,
        "_last_df": None,
        "_last_df_rows": 0,
        "_last_user_question": None,
        "_postprocess": None,
        "_dates_were_swapped": False,
        "_swapped_from": None,
        "_swapped_to": None,
    }


# Markers
def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "slow: marks tests as slow")
    config.addinivalue_line("markers", "integration: marks tests as integration tests")
    config.addinivalue_line("markers", "mcp: marks tests related to MCP functionality")
