-- SENTINEL V2.0 — Schema SQL
-- Totalement idempotent : peut être exécuté N fois sans erreur.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS settings (
    key        VARCHAR(50) PRIMARY KEY,
    value      TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
INSERT INTO settings (key, value) VALUES ('kill_switch', 'false')
    ON CONFLICT (key) DO NOTHING;

CREATE TABLE IF NOT EXISTS decisions (
    decision_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    type                     VARCHAR(50),
    source_agent             VARCHAR(50),
    ticker                   VARCHAR(20),
    action                   VARCHAR(10),
    montant_eur              FLOAT,
    broker                   VARCHAR(20) DEFAULT 'IBKR',
    account_id               VARCHAR(20),
    paper_mode               BOOLEAN DEFAULT TRUE,
    requires_human_approval  BOOLEAN DEFAULT TRUE,
    auto_approved_reason     TEXT,
    score                    INT,
    raison                   TEXT,
    status                   VARCHAR(30) DEFAULT 'pending',
    samed_choice             VARCHAR(10),
    samed_approved_at        TIMESTAMPTZ,
    created_at               TIMESTAMPTZ DEFAULT NOW(),
    updated_at               TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS events (
    id           SERIAL PRIMARY KEY,
    event_type   VARCHAR(50),
    source_agent VARCHAR(50),
    decision_id  UUID REFERENCES decisions(decision_id) ON DELETE SET NULL,
    payload      JSONB,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS orders (
    id           SERIAL PRIMARY KEY,
    decision_id  UUID REFERENCES decisions(decision_id) ON DELETE SET NULL,
    ticker       VARCHAR(20),
    action       VARCHAR(10),
    quantity     FLOAT,
    avg_price    FLOAT,
    status_ib    VARCHAR(30),
    broker       VARCHAR(20),
    paper_mode   BOOLEAN,
    executed_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS heartbeats (
    agent_name  VARCHAR(50) PRIMARY KEY,
    last_seen   TIMESTAMPTZ,
    status      VARCHAR(20),
    latency_ms  INT,
    error_count INT DEFAULT 0,
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id             SERIAL PRIMARY KEY,
    total_eur      FLOAT,
    cash_eur       FLOAT,
    total_invested FLOAT,
    positions      JSONB,
    source         VARCHAR(20) DEFAULT 'vps',
    created_at     TIMESTAMPTZ DEFAULT NOW()
);
