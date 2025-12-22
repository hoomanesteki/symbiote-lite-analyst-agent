#!/usr/bin/env python
"""
Create a sample taxi_trips.sqlite database for testing.

Run with: python -m scripts.create_sample_db
"""

import sqlite3
import random
from datetime import datetime, timedelta
from pathlib import Path

def create_sample_database():
    db_path = Path(__file__).resolve().parents[1] / "data" / "taxi_trips.sqlite"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    print(f"Creating sample database at: {db_path}")
    
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    # Create table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS taxi_trips (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pickup_datetime TEXT NOT NULL,
            dropoff_datetime TEXT NOT NULL,
            vendor_id TEXT NOT NULL,
            fare_amount REAL NOT NULL,
            tip_amount REAL NOT NULL,
            total_amount REAL NOT NULL
        )
    """)
    
    # Clear existing data
    cursor.execute("DELETE FROM taxi_trips")
    
    # Generate sample data for 2022
    vendors = ["VTS", "CMT", "DDS"]
    start_date = datetime(2022, 1, 1)
    end_date = datetime(2022, 12, 31)
    
    rows = []
    current_date = start_date
    
    print("Generating sample trips...")
    
    while current_date <= end_date:
        # Generate 50-200 trips per day
        trips_today = random.randint(50, 200)
        
        for _ in range(trips_today):
            pickup_hour = random.randint(0, 23)
            pickup_minute = random.randint(0, 59)
            pickup_time = current_date.replace(hour=pickup_hour, minute=pickup_minute)
            
            # Trip duration: 5-60 minutes
            duration = timedelta(minutes=random.randint(5, 60))
            dropoff_time = pickup_time + duration
            
            vendor = random.choice(vendors)
            fare = round(random.uniform(5, 80), 2)
            tip = round(random.uniform(0, fare * 0.3), 2)
            total = round(fare + tip + random.uniform(1, 5), 2)  # fare + tip + fees
            
            rows.append((
                pickup_time.strftime("%Y-%m-%d %H:%M:%S"),
                dropoff_time.strftime("%Y-%m-%d %H:%M:%S"),
                vendor,
                fare,
                tip,
                total
            ))
        
        current_date += timedelta(days=1)
    
    # Insert all rows
    cursor.executemany("""
        INSERT INTO taxi_trips (pickup_datetime, dropoff_datetime, vendor_id, fare_amount, tip_amount, total_amount)
        VALUES (?, ?, ?, ?, ?, ?)
    """, rows)
    
    conn.commit()
    
    # Verify
    cursor.execute("SELECT COUNT(*) FROM taxi_trips")
    count = cursor.fetchone()[0]
    
    cursor.execute("SELECT MIN(pickup_datetime), MAX(pickup_datetime) FROM taxi_trips")
    min_date, max_date = cursor.fetchone()
    
    conn.close()
    
    print(f"✅ Created {count:,} sample trips")
    print(f"   Date range: {min_date} to {max_date}")
    print(f"   Database: {db_path}")


if __name__ == "__main__":
    create_sample_database()
