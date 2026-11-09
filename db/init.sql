CREATE SCHEMA IF NOT EXISTS pas;

CREATE TABLE IF NOT EXISTS pas.key_rate (
    date DATE PRIMARY KEY,
    key_rate NUMERIC(10, 4) NOT NULL
);

CREATE TABLE IF NOT EXISTS pas.aud (
    date DATE PRIMARY KEY,
    nominal INTEGER NOT NULL,
    rate NUMERIC(15, 6) NOT NULL
);

CREATE TABLE IF NOT EXISTS pas.aed (
    date DATE PRIMARY KEY,
    nominal INTEGER NOT NULL,
    rate NUMERIC(15, 6) NOT NULL
);

CREATE TABLE IF NOT EXISTS pas.gdp (
    date DATE PRIMARY KEY,
    gdp NUMERIC(20, 6) NOT NULL
);

CREATE TABLE IF NOT EXISTS pas.trade_balance (
    date DATE PRIMARY KEY,
    trade_balance NUMERIC(20, 6) NOT NULL
);

CREATE TABLE IF NOT EXISTS pas.load_log (
    id BIGSERIAL PRIMARY KEY,
    load_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL,
    records_loaded INTEGER NOT NULL DEFAULT 0,
    date_from DATE,
    date_to DATE,
    message TEXT
);

CREATE TABLE IF NOT EXISTS pas.forecast_history (
    id BIGSERIAL PRIMARY KEY,
    forecast_date DATE NOT NULL,
    target_date DATE NOT NULL,
    model_name VARCHAR(100) NOT NULL,
    predicted_rate NUMERIC(10,4) NOT NULL
);