from google.cloud import bigquery
import pandas as pd
from datetime import datetime

def run_bigquery (sql: str) -> pd.DataFrame:
    """
    Run a BigQuery SQL query and validates input.

    Args:
        sql (str): SQL query to execute.

    Returns:
        pd.DataFrame: Query results.
    """

    if not isinstance(sql, str) or not sql.strip(): # Validate input SQL
        raise ValueError("SQL query must be a non-empty string.") # Raise error for invalid input

    client = bigquery.Client() # connect to Google BigQuery using default credentials
    
    print("Running SQL at:", datetime.utcnow().isoformat()) # Log the time the query is run
    print(sql)  # Log the SQL query being executed

    query_job = client.query(sql) # send the query to BigQuery
    df = query_job.to_dataframe() # convert the results to a pandas DataFrame

    return df

# Manual sanity test
if __name__ == "__main__":
    TEST_SQL = """
    SELECT 
        passenger_count,
        AVG(fare_amount) AS avg_fare
    FROM `bigquery-public-data.new_york_taxi_trips.tlc_yellow_trips_2022`
    WHERE passenger_count IS NOT NULL
    GROUP BY passenger_count
    ORDER BY passenger_count
    LIMIT 5
    """
    df = run_bigquery(TEST_SQL)
    print(df.head())