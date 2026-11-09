from datetime import date, timedelta

import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor
from sqlalchemy import create_engine
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


def build_forecast(data):
    key_rate = data["key_rate"].copy()
    key_rate["date"] = pd.to_datetime(key_rate["date"])

    df = key_rate.sort_values("date").set_index("date")

    for table, column in [
        ("aud", "rate"),
        ("aed", "rate"),
        ("gdp", "gdp"),
        ("trade_balance", "trade_balance")
    ]:
        source = data[table].copy()
        source["date"] = pd.to_datetime(source["date"])
        source = source.set_index("date")[[column]]

        if table in ["aud", "aed"]:
            source = source.rename(columns={"rate": f"{table}_rate"})

        df = df.join(source, how="left")
        df[source.columns[0]] = df[source.columns[0]].ffill()

    df["key_rate_lag_1"] = df["key_rate"].shift(1)
    df["key_rate_lag_7"] = df["key_rate"].shift(7)
    df["key_rate_lag_30"] = df["key_rate"].shift(30)

    features = [
        "key_rate_lag_1",
        "key_rate_lag_7",
        "key_rate_lag_30",
        "aud_rate",
        "aed_rate",
        "gdp",
        "trade_balance"
    ]

    df["target"] = df["key_rate"].shift(-30)

    training = df.dropna(subset=features + ["target"])

    if len(training) < 30:
        raise ValueError("Недостаточно данных для построения прогноза")

    X = training[features]
    y = training["target"]

    latest = df[features].dropna().iloc[[-1]]

    models = {
        "Linear Regression": LinearRegression(),
        "Random Forest": RandomForestRegressor(
            n_estimators=100,
            random_state=42
        )
    }

    forecast_date = date.today()
    target_date = forecast_date + timedelta(days=30)

    results = []

    for name, model in models.items():
        model.fit(X, y)
        prediction = model.predict(latest)[0]

        results.append({
            "forecast_date": forecast_date,
            "target_date": target_date,
            "model_name": name,
            "predicted_rate": round(float(prediction), 4)
        })

    result_df = pd.DataFrame(results)

    result_df.to_sql(
        "forecast_history",
        get_engine(),
        schema="pas",
        if_exists="append",
        index=False
    )

    return result_df