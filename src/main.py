import os
import re
from datetime import datetime
from io import StringIO

import pandas as pd
import requests
import psycopg2
import urllib3
from dateutil.relativedelta import relativedelta
from dotenv import load_dotenv


load_dotenv()
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

RAW_DIR = "data/raw"
os.makedirs(RAW_DIR, exist_ok=True)

FIRST_RUN = os.getenv("FIRST_RUN", "true").strip().lower() == "true"
LAST_LOAD_DATE = os.getenv("LAST_LOAD_DATE", "").strip()

if FIRST_RUN:
    DATA_TO = datetime.strptime(
        os.getenv("DATA_TO"),
        "%Y-%m-%d"
    )

    KEY_RATE_FROM = DATA_TO - relativedelta(
        years=int(os.getenv("INITIAL_KEY_RATE_YEARS"))
    )

    MACRO_FROM = DATA_TO - relativedelta(
        years=int(os.getenv("INITIAL_MACRO_YEARS"))
    )
else:
    if not LAST_LOAD_DATE:
        raise RuntimeError(
            "FIRST_RUN=false, но LAST_LOAD_DATE не заполнен"
        )

    DATA_TO = datetime.now()
    KEY_RATE_FROM = datetime.strptime(
        LAST_LOAD_DATE,
        "%Y-%m-%d"
    ) + relativedelta(days=1)
    MACRO_FROM = KEY_RATE_FROM


def get_connection():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        dbname=os.getenv("POSTGRES_DB", "pas"),
        user=os.getenv("POSTGRES_USER", "pas"),
        password=os.getenv("POSTGRES_PASSWORD", "pas_password")
    )


def write_log(
    connection,
    source,
    status,
    records_loaded,
    date_from,
    date_to,
    message
):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO pas.load_log
            (source, status, records_loaded, date_from, date_to, message)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                source,
                status,
                records_loaded,
                date_from.date() if isinstance(date_from, datetime) else date_from,
                date_to.date() if isinstance(date_to, datetime) else date_to,
                message
            )
        )
    connection.commit()


def save_dataframe(connection, table, dataframe, columns):
    """Сохраняет данные в PostgreSQL и возвращает количество новых строк."""
    if dataframe.empty:
        return 0

    dataframe = dataframe.copy()
    dataframe["date"] = pd.to_datetime(dataframe["date"]).dt.date

    inserted = 0

    with connection.cursor() as cursor:
        for row in dataframe.itertuples(index=False):
            values = [getattr(row, column) for column in columns]

            cursor.execute(
                f"SELECT 1 FROM pas.{table} WHERE date = %s",
                (row.date,)
            )

            exists = cursor.fetchone() is not None

            if table == "key_rate":
                cursor.execute(
                    """
                    INSERT INTO pas.key_rate (date, key_rate)
                    VALUES (%s, %s)
                    ON CONFLICT (date) DO UPDATE
                    SET key_rate = EXCLUDED.key_rate
                    """,
                    values
                )

            elif table in ("aud", "aed"):
                cursor.execute(
                    f"""
                    INSERT INTO pas.{table} (date, nominal, rate)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (date) DO UPDATE
                    SET nominal = EXCLUDED.nominal,
                        rate = EXCLUDED.rate
                    """,
                    values
                )

            elif table == "gdp":
                cursor.execute(
                    """
                    INSERT INTO pas.gdp (date, gdp)
                    VALUES (%s, %s)
                    ON CONFLICT (date) DO UPDATE
                    SET gdp = EXCLUDED.gdp
                    """,
                    values
                )

            elif table == "trade_balance":
                cursor.execute(
                    """
                    INSERT INTO pas.trade_balance (date, trade_balance)
                    VALUES (%s, %s)
                    ON CONFLICT (date) DO UPDATE
                    SET trade_balance = EXCLUDED.trade_balance
                    """,
                    values
                )

            if not exists:
                inserted += 1

    connection.commit()
    return inserted


def remove_raw_file(path):
    if os.path.exists(path):
        os.remove(path)


def update_env_after_success(data_to):
    env_path = ".env"

    with open(env_path, "r", encoding="utf-8") as file:
        lines = file.readlines()

    result = []
    first_run_written = False
    last_load_written = False

    for line in lines:
        if line.startswith("FIRST_RUN="):
            result.append("FIRST_RUN=false\n")
            first_run_written = True
        elif line.startswith("LAST_LOAD_DATE="):
            result.append(
                f"LAST_LOAD_DATE={data_to.strftime('%Y-%m-%d')}\n"
            )
            last_load_written = True
        elif line.startswith("DATA_TO="):
            result.append(
                f"DATA_TO={data_to.strftime('%Y-%m-%d')}\n"
            )
        else:
            result.append(line)

    if not first_run_written:
        result.append("FIRST_RUN=false\n")

    if not last_load_written:
        result.append(
            f"LAST_LOAD_DATE={data_to.strftime('%Y-%m-%d')}\n"
        )

    with open(env_path, "w", encoding="utf-8") as file:
        file.writelines(result)


def load_key_rate(connection):
    source = "key_rate"

    url = (
        "https://cbr.ru/hd_base/KeyRate/"
        "?UniDbQuery.Posted=True"
        f"&UniDbQuery.From={KEY_RATE_FROM.strftime('%d.%m.%Y')}"
        f"&UniDbQuery.To={DATA_TO.strftime('%d.%m.%Y')}"
    )

    response = requests.get(
        url,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30
    )
    response.raise_for_status()

    tables = pd.read_html(StringIO(response.text))
    df = tables[0]
    df.columns = ["date", "key_rate"]

    df["date"] = pd.to_datetime(
        df["date"],
        dayfirst=True,
        errors="coerce"
    )
    df["key_rate"] = pd.to_numeric(
        df["key_rate"],
        errors="coerce"
    ) / 100

    df = df.dropna(subset=["date", "key_rate"])
    df = df.drop_duplicates(subset=["date"])
    df = df.sort_values("date")

    inserted = save_dataframe(
        connection,
        "key_rate",
        df,
        ["date", "key_rate"]
    )

    write_log(
        connection,
        source,
        "success",
        inserted,
        KEY_RATE_FROM,
        DATA_TO,
        f"Получено записей: {len(df)}, новых записей: {inserted}"
    )

    print(
        f"Ключевая ставка: получено {len(df)}, новых {inserted}"
    )


def load_currency(connection, currency, code, file_name, table):
    source = table
    file_path = os.path.join(RAW_DIR, file_name)

    url = (
        "https://cbr.ru/Queries/UniDbQuery/DownloadExcel/98956"
        "?Posted=True"
        "&so=1"
        "&mode=1"
        f"&VAL_NM_RQ={code}"
        f"&From={KEY_RATE_FROM.strftime('%d.%m.%Y')}"
        f"&To={DATA_TO.strftime('%d.%m.%Y')}"
        f"&FromDate={KEY_RATE_FROM.strftime('%m/%d/%Y')}"
        f"&ToDate={DATA_TO.strftime('%m/%d/%Y')}"
        "&backUrl=%2Fcurrency_base%2Fdynamics%2F"
    )

    response = requests.get(
        url,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30
    )
    response.raise_for_status()

    with open(file_path, "wb") as file:
        file.write(response.content)

    df = pd.read_excel(file_path)
    df.columns = ["nominal", "date", "rate", "currency"]

    df["date"] = pd.to_datetime(
        df["date"],
        dayfirst=True,
        errors="coerce"
    )
    df["nominal"] = pd.to_numeric(
        df["nominal"],
        errors="coerce"
    )
    df["rate"] = pd.to_numeric(
        df["rate"].astype(str).str.replace(",", ".", regex=False),
        errors="coerce"
    )

    df = df.dropna(subset=["date", "nominal", "rate"])
    df = df.drop_duplicates(subset=["date"], keep="last")
    df = df[(df["nominal"] > 0) & (df["rate"] > 0)]
    df = df.sort_values("date")

    inserted = save_dataframe(
        connection,
        table,
        df[["date", "nominal", "rate"]],
        ["date", "nominal", "rate"]
    )

    write_log(
        connection,
        source,
        "success",
        inserted,
        KEY_RATE_FROM,
        DATA_TO,
        f"Получено записей: {len(df)}, новых записей: {inserted}"
    )

    remove_raw_file(file_path)

    print(
        f"{currency}: получено {len(df)}, новых {inserted}"
    )


def load_gdp(connection):
    source = "gdp"
    file_path = os.path.join(RAW_DIR, "gdp.xlsx")

    # response = requests.get(
    #     "https://rosstat.gov.ru/statistics/accounts",
    #     headers={"User-Agent": "Mozilla/5.0"},
    #     timeout=30,
    #     verify=False
    # )
    # response.raise_for_status()

    # match = re.search(
    #     r'href="([^"]*/VVP_kvartal[^\"]*\.xlsx)"',
    #     response.text
    # )

    # if not match:
    #     raise RuntimeError(
    #         "Не найдена ссылка на XLSX с квартальными данными ВВП"
    #     )

    # gdp_url = "https://rosstat.gov.ru" + match.group(1)

    # response = requests.get(
    #     gdp_url,
    #     headers={"User-Agent": "Mozilla/5.0"},
    #     timeout=30,
    #     verify=False
    # )
    # response.raise_for_status()

    # with open(file_path, "wb") as file:
    #     file.write(response.content)

    gdp_raw = pd.read_excel(
        "src/VVP_kvartal_s-1995-2026.xlsx", # file_path, временно файл с компа тк сайт не работает
        sheet_name="2",
        header=None
    )

    years = gdp_raw.iloc[2].ffill()
    quarters = gdp_raw.iloc[3]
    values = gdp_raw.iloc[4]

    gdp_rows = []

    for i in range(gdp_raw.shape[1]):
        year = years.iloc[i]
        quarter = quarters.iloc[i]
        value = values.iloc[i]

        if pd.notna(year) and pd.notna(quarter) and pd.notna(value):
            year = int(str(year).replace("2)", ""))
            gdp_rows.append({
                "year": year,
                "quarter": quarter,
                "gdp": pd.to_numeric(value, errors="coerce")
            })

    gdp = pd.DataFrame(gdp_rows)

    gdp["date"] = pd.to_datetime(
        gdp["year"].astype(str) + "-" +
        gdp["quarter"].map({
            "I квартал": "01-01",
            "II квартал": "04-01",
            "III квартал": "07-01",
            "IV квартал": "10-01"
        }),
        errors="coerce"
    )

    gdp = gdp.dropna(subset=["date", "gdp"])
    gdp = gdp.drop_duplicates(subset=["date"])
    gdp = gdp[gdp["date"] <= DATA_TO].sort_values("date")

    daily_dates = pd.DataFrame({
        "date": pd.date_range(
            start=MACRO_FROM,
            end=DATA_TO,
            freq="D"
        )
    })

    gdp = pd.merge_asof(
        daily_dates,
        gdp[["date", "gdp"]],
        on="date",
        direction="backward"
    )

    gdp = gdp.dropna(subset=["date", "gdp"])
    gdp = gdp.drop_duplicates(subset=["date"])

    inserted = save_dataframe(
        connection,
        "gdp",
        gdp,
        ["date", "gdp"]
    )

    write_log(
        connection,
        source,
        "success",
        inserted,
        MACRO_FROM,
        DATA_TO,
        f"Сформировано ежедневных записей: {len(gdp)}, новых записей: {inserted}"
    )

    # remove_raw_file(file_path)

    print(
        f"ВВП: сформировано {len(gdp)}, новых {inserted}"
    )


def load_trade_balance(connection):
    source = "trade_balance"

    response = requests.get(
        "https://cbr.ru/statistics/dopbalance_table/",
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30
    )
    response.raise_for_status()

    tables = pd.read_html(StringIO(response.text))

    trade_raw = None

    for table in tables:
        columns = [str(column) for column in table.columns]
        if any("Торговый баланс" in column for column in columns):
            trade_raw = table
            break

    if trade_raw is None:
        raise RuntimeError("Не найдена таблица с торговым балансом")

    trade_raw.columns = [
        "period",
        "current_account",
        "trade_balance",
        "services_balance",
        "primary_income",
        "secondary_income"
    ]

    trade_raw["trade_balance"] = pd.to_numeric(
        trade_raw["trade_balance"]
        .astype(str)
        .str.replace(" ", "", regex=False),
        errors="coerce"
    )

    quarter_map = {
        "I квартал": "01-01",
        "II квартал": "04-01",
        "III квартал": "07-01",
        "IV квартал": "10-01"
    }

    def quarter_to_date(value):
        value = str(value).replace("\xa0", " ").strip()

        year = re.search(r"\d{4}", value)

        if not year:
            return pd.NaT

        quarter = re.search(
            r"\b(I|II|III|IV) квартал\b",
            value
        )

        if not quarter:
            return pd.NaT

        date = quarter_map[
            f"{quarter.group(1)} квартал"
        ]

        return pd.to_datetime(
            f"{year.group()}-{date}"
        )

    trade_raw["date"] = trade_raw["period"].apply(
        quarter_to_date
    )

    trade = trade_raw[["date", "period", "trade_balance"]].copy()
    trade = trade.dropna(subset=["date", "trade_balance"])
    trade = trade.sort_values("date")
    trade = trade[trade["date"] <= DATA_TO]

    daily_dates = pd.DataFrame({
        "date": pd.date_range(
            start=MACRO_FROM,
            end=DATA_TO,
            freq="D"
        )
    })

    trade = pd.merge_asof(
        daily_dates,
        trade[["date", "trade_balance"]],
        on="date",
        direction="backward"
    )

    trade = trade.dropna(subset=["date", "trade_balance"])
    trade = trade.drop_duplicates(subset=["date"])

    inserted = save_dataframe(
        connection,
        "trade_balance",
        trade,
        ["date", "trade_balance"]
    )

    write_log(
        connection,
        source,
        "success",
        inserted,
        MACRO_FROM,
        DATA_TO,
        f"Сформировано ежедневных записей: {len(trade)}, новых записей: {inserted}"
    )

    print(
        f"Торговый баланс: сформировано {len(trade)}, новых {inserted}"
    )


def main():
    today = datetime.now().date()

    if not FIRST_RUN and LAST_LOAD_DATE == today.strftime("%Y-%m-%d"):
        print(
            f"Обновление за {today:%d.%m.%Y} уже выполнялось. "
            "Следующее обновление возможно завтра."
        )
        return

    connection = None
    errors = []

    try:
        connection = get_connection()
        print(
            f"Период загрузки: {KEY_RATE_FROM:%d.%m.%Y} — "
            f"{DATA_TO:%d.%m.%Y}"
        )

        loaders = [
            ("key_rate", lambda: load_key_rate(connection)),
            ("aud", lambda: load_currency(
                connection,
                "Австралийский доллар",
                "R01010",
                "aud.xlsx",
                "aud"
            )),
            ("aed", lambda: load_currency(
                connection,
                "Дирхам ОАЭ",
                "R01230",
                "aed.xlsx",
                "aed"
            )),
            ("gdp", lambda: load_gdp(connection)),
            ("trade_balance", lambda: load_trade_balance(connection))
        ]

        for source, loader in loaders:
            try:
                loader()
            except Exception as error:
                errors.append(source)
                connection.rollback()

                write_log(
                    connection,
                    source,
                    "error",
                    0,
                    KEY_RATE_FROM if source in ("key_rate", "aud", "aed") else MACRO_FROM,
                    DATA_TO,
                    str(error)
                )

                print(f"{source}: ошибка — {error}")

        if errors:
            print(
                "Загрузка завершена с ошибками. "
                "LAST_LOAD_DATE и FIRST_RUN не изменены."
            )
            return

        update_env_after_success(DATA_TO)

        print("Все источники успешно обработаны.")
        print(
            f"LAST_LOAD_DATE обновлена: {DATA_TO:%d.%m.%Y}"
        )

    finally:
        if connection is not None:
            connection.close()


if __name__ == "__main__":
    main()
