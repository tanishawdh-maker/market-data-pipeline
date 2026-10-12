# A small official Python image as the starting point.
FROM python:3.12-slim

WORKDIR /app

# Install packages first: Docker caches this step and skips it on rebuilds
# unless requirements.txt changes.
COPY api/requirements.txt api/requirements.txt
RUN pip install --no-cache-dir -r api/requirements.txt

# Then copy our code: the API, plus the one shared file it needs from etl/.
COPY etl/db.py etl/db.py
COPY api/ api/

ENV PYTHONPATH=/app/etl
EXPOSE 8000

# 0.0.0.0 = accept connections from outside the container, not just from inside it.
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]