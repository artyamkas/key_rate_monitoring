import schedule
import subprocess
import time
import logging
import os

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

is_running = False


def run_loader():
    global is_running

    if is_running:
        logging.warning("Загрузка уже выполняется")
        return

    is_running = True

    try:
        logging.info("Запуск загрузки данных")

        result = subprocess.run(
            ["python", "src/main.py"],
            check=False
        )

        if result.returncode == 0:
            logging.info("Загрузка завершена")
        else:
            logging.error("Загрузка завершилась с ошибкой")

    except Exception:
        logging.exception("Ошибка запуска загрузчика")

    finally:
        is_running = False


schedule.every().day.at("16:00").do(run_loader)

logging.info("Планировщик запущен. Ежедневная загрузка: 16:00 MSK")

while True:
    schedule.run_pending()
    time.sleep(60)