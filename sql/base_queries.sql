-- Base query for sampling trips
SELECT
    pickup_datetime,
    passenger_count,
    trip_distance,
    fare_amount
FROM `bigquery-public-data.new_york_taxi_trips.tlc_yellow_trips_2022`
WHERE IS NOT NULL
LIMIT 1000;

-- Aggregation: average fare by passenger count
SELECT
    passenger_count,
    AVG(fare_amount) AS avg_fare
FROM `bigquery-public-data.new_york_taxi_trips.tlc_yellow_trips_2022`
GROUP BY passenger_count
ORDER BY passenger_count;