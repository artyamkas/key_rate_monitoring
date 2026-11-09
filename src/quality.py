import pandas as pd
from sqlalchemy import create_engine, text
import os


def get_engine():
    connection_string = (
        f"postgresql+psycopg2://{os.getenv('POSTGRES_USER')}:"
        f"{os.getenv('POSTGRES_PASSWORD')}@"
        f"{os.getenv('POSTGRES_HOST', 'localhost')}:"
        f"{os.getenv('POSTGRES_PORT', '5432')}/"
        f"{os.getenv('POSTGRES_DB')}"
    )
    return create_engine(connection_string)


def check_quality():
    engine = get_engine()

    tables = [
        "key_rate",
        "aud",
        "aed",
        "gdp",
        "trade_balance"
    ]

    results = []

    with engine.connect() as connection:
        for table in tables:
            query = text(f"""
                SELECT
                    COUNT(*) AS total,
                    COUNT(DISTINCT date) AS unique_dates,
                    COUNT(*) FILTER (WHERE date IS NULL) AS null_dates
                FROM pas.{table}
            """)

            row = connection.execute(query).fetchone()

            results.append({
                "Таблица": table,
                "Количество записей": row.total,
                "Уникальность дат": row.total == row.unique_dates,
                "Пустые даты": row.null_dates,
                "Результат": "OK" if row.total == row.unique_dates
                and row.null_dates == 0 else "Ошибка"
            })

    return pd.DataFrame(results)