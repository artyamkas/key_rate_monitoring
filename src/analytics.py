import os
import pandas as pd
from sqlalchemy import create_engine


def get_engine():
    connection_string = (
        f"postgresql+psycopg2://{os.getenv('POSTGRES_USER')}:"
        f"{os.getenv('POSTGRES_PASSWORD')}@"
        f"{os.getenv('POSTGRES_HOST', 'localhost')}:"
        f"{os.getenv('POSTGRES_PORT', '5432')}/"
        f"{os.getenv('POSTGRES_DB')}"
    )

    return create_engine(connection_string)


def load_data():
    engine = get_engine()

    tables = [
        "key_rate",
        "aud",
        "aed",
        "gdp",
        "trade_balance"
    ]

    data = {}

    for table in tables:
        data[table] = pd.read_sql(
            f"SELECT * FROM pas.{table} ORDER BY date",
            engine
        )

    return data