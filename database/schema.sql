-- =====================================================================
-- DBMS 1: PostgreSQL  -  Data master & transaksi toko online
-- Skema terinspirasi dari "Brazilian E-Commerce Public Dataset by Olist"
-- (https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)
-- =====================================================================

DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS customers;

CREATE TABLE customers (
    customer_id   INTEGER PRIMARY KEY,
    full_name     VARCHAR(120) NOT NULL,
    email         VARCHAR(120) NOT NULL UNIQUE,
    gender        CHAR(1)      NOT NULL CHECK (gender IN ('L', 'P')),
    city          VARCHAR(80)  NOT NULL,
    segment       VARCHAR(20)  NOT NULL CHECK (segment IN ('Regular', 'Silver', 'Gold')),
    registered_at DATE         NOT NULL
);

CREATE TABLE products (
    product_id   INTEGER PRIMARY KEY,
    product_name VARCHAR(120)  NOT NULL,
    category     VARCHAR(50)   NOT NULL,
    price        NUMERIC(12,2) NOT NULL CHECK (price > 0)
);

CREATE TABLE orders (
    order_id     INTEGER PRIMARY KEY,
    customer_id  INTEGER       NOT NULL REFERENCES customers(customer_id),
    product_id   INTEGER       NOT NULL REFERENCES products(product_id),
    quantity     INTEGER       NOT NULL CHECK (quantity > 0),
    total_amount NUMERIC(14,2) NOT NULL,
    status       VARCHAR(20)   NOT NULL CHECK (status IN ('completed', 'shipped', 'cancelled')),
    order_date   TIMESTAMP     NOT NULL
);

CREATE INDEX idx_orders_customer ON orders(customer_id);
CREATE INDEX idx_orders_product  ON orders(product_id);
CREATE INDEX idx_orders_date     ON orders(order_date);
