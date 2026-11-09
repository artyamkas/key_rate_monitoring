import streamlit as st
import pandas as pd
import plotly.express as px

from analytics import load_data
from quality import check_quality
from forecast import build_forecast, get_engine


st.set_page_config(
    page_title="Мониторинг ключевой ставки ЦБ",
    page_icon="📊",
    layout="wide"
)

st.title("Мониторинг ключевой ставки ЦБ России")

page = st.sidebar.radio(
    "Раздел",
    ["Предметный дашборд", "Операционный дашборд"]
)

try:
    data = load_data()
except Exception as error:
    st.error(f"Не удалось загрузить данные: {error}")
    st.stop()


if page == "Предметный дашборд":

    st.header("Предметный дашборд")

    key_rate = data["key_rate"]

    if key_rate.empty:
        st.warning("Данные о ключевой ставке отсутствуют")
        st.stop()

    latest_rate = key_rate.sort_values("date").iloc[-1]

    col1, col2, col3 = st.columns(3)

    col1.metric(
        "Последняя ключевая ставка",
        f"{latest_rate['key_rate']}%"
    )

    col2.metric(
        "Дата последнего значения",
        str(latest_rate["date"])
    )

    col3.metric(
        "Количество записей",
        len(key_rate)
    )

    st.subheader("Динамика ключевой ставки")

    fig = px.line(
        key_rate,
        x="date",
        y="key_rate",
        title="Ключевая ставка ЦБ России"
    )

    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Динамика валютных курсов")

    currency = pd.concat([
        data["aud"].assign(currency="AUD"),
        data["aed"].assign(currency="AED")
    ])

    if not currency.empty:
        fig = px.line(
            currency,
            x="date",
            y="rate",
            color="currency",
            title="Курсы валют"
        )

        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Макроэкономические показатели")

    col1, col2 = st.columns(2)

    with col1:
        fig = px.line(
            data["gdp"],
            x="date",
            y="gdp",
            title="ВВП"
        )
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        fig = px.line(
            data["trade_balance"],
            x="date",
            y="trade_balance",
            title="Торговый баланс"
        )
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Корреляция показателей")

    combined = key_rate[["date", "key_rate"]].copy()

    for table, column in [
        ("aud", "rate"),
        ("aed", "rate"),
        ("gdp", "gdp"),
        ("trade_balance", "trade_balance")
    ]:
        source = data[table][["date", column]].copy()
        combined = combined.merge(source, on="date", how="left")

    correlation = combined.drop(columns=["date"]).corr()

    fig = px.imshow(
        correlation,
        text_auto=".2f",
        title="Корреляционная матрица"
    )

    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Прогноз ключевой ставки")

    if st.button("Построить прогноз"):
        try:
            result = build_forecast(data)
            st.success("Прогнозы рассчитаны и сохранены")
            st.dataframe(result, use_container_width=True)
        except Exception as error:
            st.error(f"Ошибка прогнозирования: {error}")

    history = pd.read_sql(
        """
        SELECT forecast_date, target_date, model_name, predicted_rate
        FROM pas.forecast_history
        ORDER BY forecast_date
        """,
        get_engine()
    )

    if not history.empty:
        st.subheader("История прогнозов")

        fig = px.line(
            history,
            x="forecast_date",
            y="predicted_rate",
            color="model_name",
            markers=True,
            hover_data=["target_date"],
            title="Изменение прогнозов"
        )

        st.plotly_chart(fig, use_container_width=True)

        st.dataframe(history, use_container_width=True)


else:

    st.header("Операционный дашборд")

    st.subheader("Контроль качества данных")

    quality = check_quality()

    st.dataframe(
        quality,
        use_container_width=True,
        hide_index=True
    )

    st.subheader("Последние загрузки")

    engine = get_engine()

    logs = pd.read_sql(
        """
        SELECT
            load_time,
            source,
            status,
            records_loaded,
            date_from,
            date_to,
            message
        FROM pas.load_log
        ORDER BY load_time DESC
        LIMIT 100
        """,
        engine
    )

    if logs.empty:
        st.info("История загрузок пока отсутствует")
    else:
        st.dataframe(logs, use_container_width=True)

    st.subheader("Состояние источников")

    for table, frame in data.items():
        if frame.empty:
            st.error(f"{table}: данные отсутствуют")
        else:
            last_date = frame["date"].max()
            st.write(
                f"{table}: {len(frame)} записей, "
                f"последняя дата — {last_date}"
            )