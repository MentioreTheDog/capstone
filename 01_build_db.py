"""Загружает 9 сырых CSV-файлов датасета Olist в единую SQLite-базу olist.db.

Использование:
    python 01_build_db.py

Ожидает, что сырые CSV лежат в ./data/ (скачиваются отдельно с Kaggle,
см. README — в репозиторий они не входят из-за размера).
"""

import sqlite3
from pathlib import Path

import pandas as pd

DATA_DIR = Path("data")
DB_PATH = "olist.db"

# Имя файла -> имя таблицы в базе
TABLES = {
    "olist_orders_dataset.csv": "orders",
    "olist_order_items_dataset.csv": "order_items",
    "olist_order_payments_dataset.csv": "order_payments",
    "olist_order_reviews_dataset.csv": "order_reviews",
    "olist_customers_dataset.csv": "customers",
    "olist_products_dataset.csv": "products",
    "olist_sellers_dataset.csv": "sellers",
    "olist_geolocation_dataset.csv": "geolocation",
    "product_category_name_translation.csv": "product_category_name_translation",
}


def main():
    missing = [f for f in TABLES if not (DATA_DIR / f).exists()]
    if missing:
        raise FileNotFoundError(
            f"Не найдены файлы в {DATA_DIR}/: {missing}\n"
            "Скачайте датасет с Kaggle (ссылка в README) и распакуйте в data/."
        )

    with sqlite3.connect(DB_PATH) as conn:
        for filename, table in TABLES.items():
            df = pd.read_csv(DATA_DIR / filename)
            df.to_sql(table, conn, if_exists="replace", index=False)
            print(f"{table:35s} <- {filename:45s} ({len(df):,} строк)")

        # Индексы на ключи, по которым дальше идут JOIN в feat_sql.py —
        # без них выборка признаков по 95k+ заказов заметно медленнее
        conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_id     ON orders(order_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_items_order   ON order_items(order_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pay_order     ON order_payments(order_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_rev_order     ON order_reviews(order_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_cust   ON orders(customer_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_products_id   ON products(product_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sellers_id    ON sellers(seller_id)")
        conn.commit()

        # Без ANALYZE планировщик SQLite не видит статистику по новым индексам
        # и может выбрать на порядки более медленный план для многотабличных
        # JOIN-запросов из feat_sql.py (проверено: без этого шага сборка
        # признаков зависает на минуты вместо секунды).
        conn.execute("ANALYZE")
        conn.commit()

    print(f"\nГотово: {DB_PATH}")


if __name__ == "__main__":
    main()
