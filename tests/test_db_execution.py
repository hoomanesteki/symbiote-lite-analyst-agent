from scripts.analysis import execute_sql_query

def test_execute_simple_query():
    sql = """
    SELECT COUNT(*) as n
    FROM taxi_trips
    WHERE pickup_datetime >= '2022-01-01'
      AND pickup_datetime < '2022-02-01'
    """
    df = execute_sql_query(sql)
    assert df is not None
    assert not df.empty
    assert "n" in df.columns
