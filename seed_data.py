"""Seed data sintetis (Faker) ke PostgreSQL (master) dan Redis (log aktivitas).

Jalankan:  python seed_data.py
Hasil default:
  - PostgreSQL: 200 customers, 60 products, 600 orders
  - Redis     : 2000 event aktivitas di Redis Stream 'activity_log'
"""
import random
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from faker import Faker

from db_config import REDIS_STREAM_KEY, get_pg_engine, get_redis_client

SEED = 42
N_CUSTOMERS = 200
N_PRODUCTS = 60
N_ORDERS = 600
N_EVENTS = 2000
DAYS_BACK = 90

fake = Faker("id_ID")
Faker.seed(SEED)
random.seed(SEED)

NOW = datetime.now().replace(microsecond=0)
START = NOW - timedelta(days=DAYS_BACK)

CITIES = ["Jakarta", "Bandung", "Surabaya", "Yogyakarta", "Semarang",
          "Medan", "Makassar", "Denpasar", "Sumedang", "Malang"]
CATEGORIES = {
    "Elektronik": (500_000, 8_000_000),
    "Fashion": (75_000, 750_000),
    "Rumah Tangga": (50_000, 1_500_000),
    "Kecantikan": (40_000, 400_000),
    "Olahraga": (100_000, 2_000_000),
    "Buku": (35_000, 250_000),
}
EVENT_TYPES = ["page_view", "search", "add_to_cart", "wishlist", "checkout"]
EVENT_WEIGHTS = [0.50, 0.20, 0.15, 0.08, 0.07]
DEVICES = ["mobile", "desktop", "tablet"]
DEVICE_WEIGHTS = [0.65, 0.28, 0.07]


def random_ts(start: datetime = START, end: datetime = NOW) -> datetime:
    delta = int((end - start).total_seconds())
    return start + timedelta(seconds=random.randint(0, delta))


def build_customers() -> pd.DataFrame:
    rows = []
    for cid in range(1, N_CUSTOMERS + 1):
        gender = random.choice(["L", "P"])
        name = fake.name_male() if gender == "L" else fake.name_female()
        email = fake.unique.email()
        rows.append({
            "customer_id": cid,
            "full_name": name,
            "email": email,
            "gender": gender,
            "city": random.choice(CITIES),
            "segment": random.choices(["Regular", "Silver", "Gold"], [0.6, 0.3, 0.1])[0],
            "registered_at": fake.date_between(start_date="-2y", end_date="-91d"),
        })
    return pd.DataFrame(rows)


def build_products() -> pd.DataFrame:
    rows = []
    cats = list(CATEGORIES)
    for pid in range(1, N_PRODUCTS + 1):
        cat = cats[(pid - 1) % len(cats)]
        lo, hi = CATEGORIES[cat]
        price = round(random.uniform(lo, hi) / 1000) * 1000
        rows.append({
            "product_id": pid,
            "product_name": f"{cat} {fake.word().title()} {pid:03d}",
            "category": cat,
            "price": float(price),
        })
    return pd.DataFrame(rows)


def build_orders(products: pd.DataFrame) -> pd.DataFrame:
    price_map = products.set_index("product_id")["price"].to_dict()
    rows = []
    for oid in range(1, N_ORDERS + 1):
        pid = random.randint(1, N_PRODUCTS)
        qty = random.choices([1, 2, 3, 4, 5], [0.55, 0.25, 0.1, 0.06, 0.04])[0]
        rows.append({
            "order_id": oid,
            "customer_id": random.randint(1, N_CUSTOMERS),
            "product_id": pid,
            "quantity": qty,
            "total_amount": price_map[pid] * qty,
            "status": random.choices(["completed", "shipped", "cancelled"], [0.75, 0.15, 0.10])[0],
            "order_date": random_ts(),
        })
    return pd.DataFrame(rows)


def seed_postgres(customers, products, orders) -> None:
    engine = get_pg_engine()
    schema_sql = (Path(__file__).parent / "database" / "schema.sql").read_text()
    with engine.begin() as conn:
        conn.exec_driver_sql(schema_sql)  # DROP + CREATE ulang tabel
    customers.to_sql("customers", engine, if_exists="append", index=False)
    products.to_sql("products", engine, if_exists="append", index=False)
    orders.to_sql("orders", engine, if_exists="append", index=False)
    print(f"[PostgreSQL] customers={len(customers)} products={len(products)} orders={len(orders)}")


def seed_redis() -> None:
    r = get_redis_client()
    r.delete(REDIS_STREAM_KEY)
    events = []
    for _ in range(N_EVENTS):
        events.append({
            "customer_id": random.randint(1, N_CUSTOMERS),
            "product_id": random.randint(1, N_PRODUCTS),
            "event_type": random.choices(EVENT_TYPES, EVENT_WEIGHTS)[0],
            "device": random.choices(DEVICES, DEVICE_WEIGHTS)[0],
            "session_seconds": random.randint(5, 900),
            "timestamp": random_ts(),
        })
    events.sort(key=lambda e: e["timestamp"])  # ID stream harus naik

    pipe = r.pipeline()
    for i, ev in enumerate(events, start=1):
        ms = int(ev["timestamp"].timestamp() * 1000)
        fields = {k: str(v) for k, v in ev.items() if k != "timestamp"}
        fields["timestamp"] = ev["timestamp"].isoformat()
        # ID eksplisit <ms>-<seq> agar urut & unik walau timestamp sama
        pipe.xadd(REDIS_STREAM_KEY, fields, id=f"{ms}-{i}")
    pipe.execute()
    print(f"[Redis] stream '{REDIS_STREAM_KEY}' entries={r.xlen(REDIS_STREAM_KEY)}")


def main() -> None:
    customers = build_customers()
    products = build_products()
    orders = build_orders(products)
    seed_postgres(customers, products, orders)
    seed_redis()
    print("Seeding selesai.")


if __name__ == "__main__":
    main()
