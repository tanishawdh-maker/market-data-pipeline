"""Database connection. Settings come from the .env file, never from the code."""
import os

import psycopg
from dotenv import load_dotenv

load_dotenv()  # read the .env file and put its values into environment variables


def get_connection():
    """Open a connection to the PostgreSQL database."""
    return psycopg.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "postgres"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD"),
    )