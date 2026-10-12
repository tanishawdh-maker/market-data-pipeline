# Start from the official Airflow image, then add the packages our pipeline needs.
FROM apache/airflow:3.3.2

COPY requirements.txt /requirements.txt

# Pinning apache-airflow stops pip from accidentally changing Airflow's own version.
RUN pip install --no-cache-dir "apache-airflow==${AIRFLOW_VERSION}" -r /requirements.txt