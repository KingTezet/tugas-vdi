# Multi-DBMS Data Pipeline & Web Visualization — Store Analytics

Tugas Mandiri Terstruktur — Mata Kuliah **Visualisasi Data dan Informasi**, Program Studi Informatika.

| | |
|---|---|
| **Nama** | _(isi nama lengkap)_ |
| **NIM** | _(isi NIM)_ |

## 🔗 Daftar Tautan

| Tautan | URL |
|---|---|
| Live Web Application | |
| Repositori GitHub | https://github.com/KingTezet/tugas-vdi |
| Sumber Data Asli | https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce |
| Referensi Kode / Proyek | |

## 📖 Skenario Bisnis

Sebuah toko online memisahkan penyimpanan data berdasarkan karakteristik beban kerjanya:

- **Data master & transaksi** (pelanggan, produk, order) membutuhkan integritas relasional, foreign key, dan konsistensi ACID → disimpan di **PostgreSQL**.
- **Log aktivitas pengguna** (page view, search, add-to-cart, wishlist, checkout) bervolume tinggi, bersifat *append-only*, dan butuh penulisan cepat → disimpan di **Redis Stream**.

Dashboard menggabungkan kedua sumber untuk menjawab: *kategori mana yang paling banyak dilihat tapi jarang dibeli?*, *apakah aktivitas harian sejalan dengan pendapatan?*, dan *apakah pelanggan yang aktif juga paling banyak belanja?*

## 🏗️ Arsitektur

```
┌──────────────────────────┐      ┌──────────────────────────┐
│ DBMS 1: PostgreSQL 16    │      │ DBMS 2: Redis 7          │
│ (Relational)             │      │ (In-memory / Stream)     │
│ - customers              │      │ - activity_log (XSTREAM) │
│ - products               │      │   customer_id, product_id│
│ - orders                 │      │   event_type, device,    │
│                          │      │   session_seconds, ts    │
└────────────┬─────────────┘      └────────────┬─────────────┘
   SQLAlchemy + psycopg2                   redis-py (XRANGE)
             │                                 │
             ▼                                 ▼
        ┌───────────────────────────────────────────┐
        │  Pandas: pd.read_sql + DataFrame(XRANGE)  │
        │  merge() on customer_id & product_id      │
        │  groupby / pivot_table / resample         │
        └────────────────────┬──────────────────────┘
                             ▼
              Streamlit + Plotly (3 chart interaktif)
```

| DBMS | Engine | Fungsi |
|---|---|---|
| DBMS 1 | PostgreSQL 16 | Data master (customers, products) & transaksi (orders) |
| DBMS 2 | Redis 7 (Stream) | Log aktivitas/clickstream pengguna |

### Alur Data Pipeline (Pandas)

1. **Extract** — `pd.read_sql()` mengambil tabel `customers`, `products`, `orders` dari PostgreSQL; `XRANGE activity_log` mengambil seluruh event dari Redis lalu diubah menjadi DataFrame dan dikonversi tipenya.
2. **Transform / Federation** — `orders.merge(customers).merge(products)` dan `events.merge(customers).merge(products)` memperkaya log Redis dengan atribut master (kota, segmen, kategori) dari PostgreSQL. Setelah itu dilakukan agregasi (`groupby`, `pivot_table`, `resample`) dan merge kedua hasil agregasi (mis. view per kategori ⨝ order per kategori → conversion rate).
3. **Present** — hasil divisualisasikan dengan Plotly di Streamlit, di-cache selama 5 menit (`st.cache_data`).

### Fitur Interaktivitas

- Filter sidebar: rentang tanggal, kota, kategori produk, segmen pelanggan, opsi sertakan order *cancelled*.
- KPI: total pendapatan, jumlah order, jumlah event, konversi view → order.
- **Chart 1** — Grouped bar: page view & add-to-cart (Redis) vs order (PostgreSQL) per kategori.
- **Chart 2** — Dual-axis: pendapatan (bar) vs jumlah event (line), granularitas harian/mingguan.
- **Chart 3** — Scatter per pelanggan: jumlah event vs total belanja, warna = segmen, ukuran = jumlah order, beserta korelasi Pearson.
- Hover tooltip, zoom/pan Plotly, tabel data hasil merge, tombol muat ulang data.

## 📂 Struktur Proyek

```
.
├── app.py               # Aplikasi Streamlit (pipeline + visualisasi)
├── db_config.py         # Koneksi PostgreSQL & Redis dari environment variables
├── seed_data.py         # Generator data sintetis (Faker) ke PostgreSQL & Redis
├── database/
│   └── schema.sql       # DDL PostgreSQL
├── docker-compose.yml   # PostgreSQL + Redis lokal
├── requirements.txt
├── .env.example         # Template environment variables
└── README.md
```

## 🗄️ Data

- **Basis skema:** [Brazilian E-Commerce Public Dataset by Olist (Kaggle)](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) — entitas customers, products, orders diadaptasi dan disederhanakan.
- **Isi data:** sintetis, dibuat dengan [Faker](https://faker.readthedocs.io/) (locale `id_ID`, seed 42 sehingga reproducible):
  - PostgreSQL: 200 customers, 60 products, 600 orders
  - Redis: 2.000 event di stream `activity_log`
- Skema PostgreSQL: [`database/schema.sql`](database/schema.sql). Struktur Redis Stream terdokumentasi di [`seed_data.py`](seed_data.py).

## 🚀 Menjalankan Secara Lokal

Prasyarat: Python 3.10+, Docker Desktop.

```bash
# 1. Siapkan environment variables
cp .env.example .env          # sesuaikan bila perlu

# 2. Jalankan PostgreSQL & Redis
docker compose up -d

# 3. Install dependensi
python -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 4. Isi data
python seed_data.py

# 5. Jalankan dashboard
streamlit run app.py
```

Buka http://localhost:8501.

## ☁️ Deployment (Streamlit Community Cloud)

Database lokal tidak bisa diakses dari internet, jadi untuk versi live gunakan layanan cloud gratis:

1. Buat PostgreSQL di **Neon** / **Supabase** dan Redis di **Upstash** / **Redis Cloud**.
2. Isi `DATABASE_URL` dan `REDIS_URL` di `.env` lokal, lalu jalankan `python seed_data.py` sekali untuk mengisi database cloud.
3. Push repo ke GitHub (file `.env` sudah di-ignore), lalu deploy `app.py` di https://share.streamlit.io.
4. Di **App settings → Secrets**, isi:
   ```toml
   DATABASE_URL = "postgresql://user:pass@host/db?sslmode=require"
   REDIS_URL = "rediss://default:pass@host:6379"
   ```
   Streamlit mengekspos secrets tingkat atas sebagai environment variables, sehingga dibaca oleh `db_config.py` tanpa perubahan kode.

## 🔐 Keamanan

Tidak ada password yang di-hardcode. Semua credential dibaca dari `.env` (lokal, tidak di-commit) atau Secrets platform deploy melalui `python-dotenv` + `os.getenv`.

## 📚 Referensi

- Streamlit Docs — https://docs.streamlit.io
- Plotly Python — https://plotly.com/python/
- pandas `merge` — https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.merge.html
- SQLAlchemy — https://docs.sqlalchemy.org
- redis-py & Redis Streams — https://redis.readthedocs.io , https://redis.io/docs/latest/develop/data-types/streams/
- Faker — https://faker.readthedocs.io
