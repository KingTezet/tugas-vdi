"""Dashboard Multi-DBMS: PostgreSQL (master/transaksi) + Redis (log aktivitas).

Jalankan:  streamlit run app.py
Koneksi database dibaca dari .env (lihat db_config.py) - tanpa hardcode password.
Tema visual diatur di .streamlit/config.toml (gaya "Emerald" monokrom).
"""
from datetime import timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from db_config import REDIS_STREAM_KEY, get_pg_engine, get_redis_client

st.set_page_config(page_title="Store Analytics", page_icon="◼", layout="wide")

# ---------------------------------------------------------------------------
# 0. DESIGN TOKENS - monokrom + aksen emerald (tanpa gradien)
# ---------------------------------------------------------------------------
INK = "#EDEDED"        # teks utama
MUTED = "#8A8A8A"      # label sumbu, keterangan
LINE = "#262626"       # garis sumbu / border
GRID = "#1C1C1C"       # grid horizontal (sangat redup)
SURFACE = "#0A0A0A"    # latar halaman
FONT = '-apple-system, BlinkMacSystemFont, "SF Pro Text", "Inter", "Helvetica Neue", Arial, sans-serif'

# Ramp emerald satu hue (gelap -> terang). Dipakai untuk data berurutan:
# funnel (view -> cart -> order) dan segmen (Regular -> Silver -> Gold).
# Sudah divalidasi: lightness monoton, selisih tiap step cukup, kontras >= 3:1 di latar gelap.
EMERALD = ["#047857", "#10B981", "#6EE7B7"]

PLOTLY_CONFIG = {"displayModeBar": False, "responsive": True}

st.markdown(
    f"""
    <style>
      html, body, [class*="css"], .stApp {{ font-family: {FONT}; }}
      [data-testid="stDecoration"] {{ display: none; }}
      .block-container {{ padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1280px; }}
      h1, h2, h3, h4 {{ letter-spacing: -0.02em; font-weight: 600 !important; }}
      [data-testid="stMetricLabel"] p {{
          color: {MUTED}; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.06em;
      }}
      [data-testid="stMetricValue"] {{ font-size: 1.7rem; font-weight: 600; letter-spacing: -0.02em; }}
      /* Tag multiselect: netral, bukan blok warna penuh */
      [data-baseweb="tag"] {{
          background-color: #1F1F1F !important; border: 1px solid {LINE} !important;
          color: {INK} !important; border-radius: 6px !important;
      }}
      [data-baseweb="tag"] span {{ color: {INK} !important; }}
      section[data-testid="stSidebar"] .block-container {{ padding-top: 1.5rem; }}
      section[data-testid="stSidebar"] label p {{
          color: {MUTED}; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.06em;
      }}
      .eyebrow {{ color: {MUTED}; font-size: 0.78rem; text-transform: uppercase;
                  letter-spacing: 0.08em; margin-bottom: 0.2rem; }}
      .subtle {{ color: {MUTED}; font-size: 0.9rem; margin-top: -0.4rem; }}
    </style>
    """,
    unsafe_allow_html=True,
)


def style_fig(fig: go.Figure, height: int = 380, legend: bool = True) -> go.Figure:
    """Layout Plotly transparan, minimal grid, tipografi netral."""
    fig.update_layout(
        height=height,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONT, size=12, color=MUTED),
        colorway=EMERALD,
        margin=dict(l=56, r=12, t=40 if legend else 16, b=40),
        showlegend=legend,
        legend=dict(orientation="h", x=0, y=1.02, yanchor="bottom", title_text="",
                    font=dict(color=INK), bgcolor="rgba(0,0,0,0)"),
        hoverlabel=dict(bgcolor="#161616", bordercolor=LINE, font=dict(family=FONT, color=INK)),
        bargap=0.32,
        bargroupgap=0.08,
        barcornerradius=4,
    )
    fig.update_xaxes(automargin=True, showgrid=False, zeroline=False, showline=True, linecolor=LINE,
                     ticks="", title_font=dict(color=MUTED), tickfont=dict(color=MUTED))
    fig.update_yaxes(automargin=True, showgrid=True, gridcolor=GRID, gridwidth=1, zeroline=False, showline=False,
                     ticks="", title_font=dict(color=MUTED), tickfont=dict(color=MUTED))
    return fig


def show_chart(fig: go.Figure) -> None:
    # theme=None agar tema Streamlit tidak menimpa styling di atas
    st.plotly_chart(fig, theme=None, width="stretch", config=PLOTLY_CONFIG)


def section(title: str, subtitle: str) -> None:
    st.markdown(f"#### {title}")
    st.markdown(f"<p class='subtle'>{subtitle}</p>", unsafe_allow_html=True)


def rupiah(x: float) -> str:
    if x >= 1e9:
        return f"Rp {x / 1e9:.2f} M".replace(".", ",")
    if x >= 1e6:
        return f"Rp {x / 1e6:.1f} jt".replace(".", ",")
    return f"Rp {x:,.0f}".replace(",", ".")


# ---------------------------------------------------------------------------
# 1. EXTRACT - ambil data dari masing-masing DBMS
# ---------------------------------------------------------------------------
@st.cache_resource
def pg_engine():
    return get_pg_engine()


@st.cache_resource
def redis_client():
    return get_redis_client()


@st.cache_data(ttl=300, show_spinner="Mengambil data dari PostgreSQL...")
def load_postgres() -> dict[str, pd.DataFrame]:
    engine = pg_engine()
    customers = pd.read_sql("SELECT * FROM customers", engine)
    products = pd.read_sql("SELECT * FROM products", engine)
    orders = pd.read_sql("SELECT * FROM orders", engine, parse_dates=["order_date"])
    products["price"] = products["price"].astype(float)
    orders["total_amount"] = orders["total_amount"].astype(float)
    return {"customers": customers, "products": products, "orders": orders}


@st.cache_data(ttl=300, show_spinner="Mengambil log aktivitas dari Redis...")
def load_redis() -> pd.DataFrame:
    r = redis_client()
    entries = r.xrange(REDIS_STREAM_KEY)  # [(id, {field: value}), ...]
    events = pd.DataFrame([{"event_id": eid, **fields} for eid, fields in entries])
    if events.empty:
        return pd.DataFrame(columns=["event_id", "customer_id", "product_id",
                                     "event_type", "device", "session_seconds", "timestamp"])
    events["customer_id"] = events["customer_id"].astype(int)
    events["product_id"] = events["product_id"].astype(int)
    events["session_seconds"] = events["session_seconds"].astype(int)
    events["timestamp"] = pd.to_datetime(events["timestamp"])
    return events


# ---------------------------------------------------------------------------
# 2. TRANSFORM - federasi data lintas DBMS dengan pandas.merge()
# ---------------------------------------------------------------------------
def build_datasets(pg: dict[str, pd.DataFrame], events: pd.DataFrame):
    customers, products, orders = pg["customers"], pg["products"], pg["orders"]
    cust_cols = customers[["customer_id", "full_name", "city", "segment"]]
    prod_cols = products[["product_id", "product_name", "category"]]

    orders_full = (orders.merge(cust_cols, on="customer_id", how="left")
                         .merge(prod_cols, on="product_id", how="left"))
    # Log Redis diperkaya dengan atribut master dari PostgreSQL
    events_full = (events.merge(cust_cols, on="customer_id", how="left")
                         .merge(prod_cols, on="product_id", how="left"))
    return orders_full, events_full


try:
    pg_data = load_postgres()
    events_raw = load_redis()
except Exception as exc:  # koneksi gagal -> tampilkan pesan yang jelas
    st.error(f"Gagal terhubung ke database: {exc}")
    st.info("Pastikan `docker compose up -d` sudah jalan, file `.env` terisi, "
            "dan `python seed_data.py` sudah dieksekusi.")
    st.stop()

orders_df, events_df = build_datasets(pg_data, events_raw)

if orders_df.empty or events_df.empty:
    st.warning("Data kosong. Jalankan `python seed_data.py` terlebih dahulu.")
    st.stop()

# ---------------------------------------------------------------------------
# 3. SIDEBAR - filter (kosong = semua, agar tidak menumpuk tag)
# ---------------------------------------------------------------------------
all_cities = sorted(pg_data["customers"]["city"].unique())
all_cats = sorted(pg_data["products"]["category"].unique())
all_segments = ["Regular", "Silver", "Gold"]
min_date = min(orders_df["order_date"].min(), events_df["timestamp"].min()).date()
max_date = max(orders_df["order_date"].max(), events_df["timestamp"].max()).date()

with st.sidebar:
    st.markdown("### Filter")
    st.caption("Biarkan kosong untuk menampilkan semua.")

    date_range = st.date_input("Periode", (min_date, max_date),
                               min_value=min_date, max_value=max_date, format="DD/MM/YYYY")
    st.divider()

    cities = st.multiselect("Kota", all_cities, placeholder="Semua kota")
    categories = st.multiselect("Kategori", all_cats, placeholder="Semua kategori")
    segments = st.pills("Segmen", all_segments, selection_mode="multi", default=all_segments)
    st.divider()

    include_cancelled = st.toggle("Sertakan order cancelled", value=False)
    if st.button("Muat ulang data", width="stretch"):
        st.cache_data.clear()
        st.rerun()

    st.caption(f"PostgreSQL · {len(orders_df):,} order  \nRedis · {len(events_df):,} event")

if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
    start_date, end_date = date_range
else:
    start_date, end_date = min_date, max_date
cities = cities or all_cities
categories = categories or all_cats
segments = segments or all_segments

start_ts = pd.Timestamp(start_date)
end_ts = pd.Timestamp(end_date) + timedelta(days=1)

o = orders_df[
    orders_df["order_date"].between(start_ts, end_ts, inclusive="left")
    & orders_df["city"].isin(cities)
    & orders_df["category"].isin(categories)
    & orders_df["segment"].isin(segments)
]
if not include_cancelled:
    o = o[o["status"] != "cancelled"]
e = events_df[
    events_df["timestamp"].between(start_ts, end_ts, inclusive="left")
    & events_df["city"].isin(cities)
    & events_df["category"].isin(categories)
    & events_df["segment"].isin(segments)
]

# ---------------------------------------------------------------------------
# 4. PRESENT - header, KPI & visualisasi
# ---------------------------------------------------------------------------
st.markdown("<div class='eyebrow'>PostgreSQL × Redis · Pandas · Plotly</div>", unsafe_allow_html=True)
st.title("Store Analytics")
st.markdown("<p class='subtle'>Data master & transaksi dari PostgreSQL digabung dengan log "
            "aktivitas dari Redis Stream.</p>", unsafe_allow_html=True)
st.write("")

revenue = o["total_amount"].sum()
n_orders = len(o)
n_events = len(e)
n_views = int((e["event_type"] == "page_view").sum())
k1, k2, k3, k4 = st.columns(4)
k1.metric("Pendapatan", rupiah(revenue), border=True)
k2.metric("Order", f"{n_orders:,}".replace(",", "."), border=True)
k3.metric("Event aktivitas", f"{n_events:,}".replace(",", "."), border=True)
k4.metric("Konversi view → order", f"{(n_orders / n_views * 100) if n_views else 0:.1f}%", border=True)

if o.empty and e.empty:
    st.warning("Tidak ada data untuk kombinasi filter ini.")
    st.stop()

st.write("")

# --- Chart 1: Funnel per kategori (Redis vs PostgreSQL) ---------------------
act_cat = (e.pivot_table(index="category", columns="event_type", values="event_id",
                         aggfunc="count", fill_value=0)
           .reindex(columns=["page_view", "add_to_cart"], fill_value=0)
           .reset_index())
ord_cat = o.groupby("category").agg(orders=("order_id", "count"),
                                    revenue=("total_amount", "sum")).reset_index()
cat_df = act_cat.merge(ord_cat, on="category", how="outer").fillna(0)
cat_df["conversion_%"] = (cat_df["orders"] / cat_df["page_view"].replace(0, pd.NA) * 100).astype(float).round(1)
cat_long = cat_df.melt(id_vars="category", value_vars=["page_view", "add_to_cart", "orders"],
                       var_name="metrik", value_name="jumlah")
funnel_labels = {"page_view": "Page view · Redis", "add_to_cart": "Add to cart · Redis",
                 "orders": "Order · PostgreSQL"}
cat_long["metrik"] = cat_long["metrik"].map(funnel_labels)

c1, c2 = st.columns([3, 2], gap="medium")
with c1, st.container(border=True):
    section("Aktivitas vs order per kategori", "Funnel: dilihat → masuk keranjang → dibeli")
    fig1 = px.bar(cat_long, x="category", y="jumlah", color="metrik", barmode="group",
                  category_orders={"metrik": list(funnel_labels.values())},
                  color_discrete_sequence=EMERALD,
                  labels={"category": "", "jumlah": "", "metrik": ""})
    fig1.update_traces(hovertemplate="%{x}<br>%{fullData.name}: <b>%{y:,}</b><extra></extra>",
                       marker_line_width=0)
    show_chart(style_fig(fig1, height=360))

# --- Chart 3: Engagement vs spending per pelanggan --------------------------
eng = e.groupby("customer_id").agg(events=("event_id", "count"),
                                   avg_session=("session_seconds", "mean")).reset_index()
spend = o.groupby("customer_id").agg(total_spend=("total_amount", "sum"),
                                     orders=("order_id", "count")).reset_index()
cust = (pg_data["customers"][["customer_id", "full_name", "city", "segment"]]
        .merge(eng, on="customer_id", how="inner")
        .merge(spend, on="customer_id", how="left")
        .fillna({"total_spend": 0, "orders": 0}))
cust = cust[cust["city"].isin(cities) & cust["segment"].isin(segments)]

with c2, st.container(border=True):
    corr_txt = ""
    if len(cust) > 2:
        corr_txt = f" · korelasi r = {cust['events'].corr(cust['total_spend']):.2f}"
    section("Engagement vs belanja", f"Per pelanggan, ukuran = jumlah order{corr_txt}")
    fig3 = px.scatter(cust, x="events", y="total_spend", color="segment", size=cust["orders"] + 1,
                      size_max=16, hover_name="full_name",
                      custom_data=["city", "orders", "avg_session"],
                      category_orders={"segment": all_segments},
                      color_discrete_map=dict(zip(all_segments, EMERALD)),
                      labels={"events": "Event aktivitas", "total_spend": "", "segment": ""})
    fig3.update_traces(
        marker=dict(opacity=0.9, line=dict(width=1.5, color=SURFACE)),
        hovertemplate="<b>%{hovertext}</b><br>%{customdata[0]}<br>Event: %{x}"
                      "<br>Belanja: Rp %{y:,.0f}<br>Order: %{customdata[1]}"
                      "<br>Sesi rata-rata: %{customdata[2]:.0f} dtk<extra></extra>",
    )
    fig3 = style_fig(fig3, height=360)
    fig3.update_yaxes(tickprefix="Rp ", tickformat="~s")
    show_chart(fig3)

# --- Chart 2: Tren waktu (dua panel, satu sumbu-y masing-masing) -------------
with st.container(border=True):
    head_l, head_r = st.columns([4, 1], vertical_alignment="center")
    with head_l:
        section("Tren aktivitas & pendapatan", "Dua panel dengan sumbu waktu yang sama")
    with head_r:
        granularity = st.segmented_control("Granularitas", ["Harian", "Mingguan"],
                                           default="Harian", label_visibility="collapsed")
    freq = "W-MON" if granularity == "Mingguan" else "D"
    ev_trend = e.set_index("timestamp").resample(freq)["event_id"].count().rename("events")
    rev_trend = o.set_index("order_date").resample(freq)["total_amount"].sum().rename("revenue")
    trend = pd.concat([ev_trend, rev_trend], axis=1, sort=True).fillna(0).reset_index(names="tanggal")

    fig2 = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.12,
                         subplot_titles=("Pendapatan · PostgreSQL", "Event aktivitas · Redis"))
    fig2.add_trace(go.Bar(x=trend["tanggal"], y=trend["revenue"], name="Pendapatan",
                          marker=dict(color=EMERALD[1], line_width=0),
                          hovertemplate="Rp %{y:,.0f}<extra></extra>"), row=1, col=1)
    fig2.add_trace(go.Scatter(x=trend["tanggal"], y=trend["events"], name="Event",
                              mode="lines", line=dict(color=EMERALD[2], width=2),
                              hovertemplate="%{y} event<extra></extra>"), row=2, col=1)
    style_fig(fig2, height=440, legend=False)
    fig2.update_layout(hovermode="x unified", margin=dict(t=32))
    fig2.update_yaxes(tickprefix="Rp ", tickformat="~s", row=1, col=1)
    fig2.update_annotations(font=dict(color=INK, size=13, family=FONT), x=0, xanchor="left")
    show_chart(fig2)

# --- Tabel hasil merge ------------------------------------------------------
with st.expander("Data hasil merge"):
    tab1, tab2, tab3 = st.tabs(["Ringkasan kategori", "Order + master", "Log aktivitas + master"])
    tab1.dataframe(cat_df, width="stretch", hide_index=True)
    tab2.dataframe(o.sort_values("order_date", ascending=False), width="stretch", hide_index=True)
    tab3.dataframe(e.sort_values("timestamp", ascending=False), width="stretch", hide_index=True)

st.write("")
st.caption("Data sintetis (Faker) · skema mengacu pada Olist Brazilian E-Commerce Public Dataset (Kaggle) · "
           "Visualisasi Data dan Informasi — Informatika")
