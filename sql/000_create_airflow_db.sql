-- Runs once, the first time the database container starts with an empty volume.
-- Airflow keeps its own records in a separate database.
CREATE DATABASE airflow;