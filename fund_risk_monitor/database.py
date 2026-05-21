# -*- coding: utf-8 -*-
"""
SQLite Data Persistence
Database file stored in project directory
"""

import sqlite3
import json
import threading
from datetime import datetime
from config import DB_PATH

# Thread-safe: each thread uses its own connection
_local = threading.local()


def get_conn():
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA busy_timeout=5000")
        _local.conn.execute("PRAGMA synchronous=NORMAL")
    return _local.conn


def init_db():
    """Initialize database schema"""
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_id TEXT,
            customer_id TEXT,
            amount REAL,
            fund_name TEXT,
            fund_code TEXT,
            region_name TEXT,
            transaction_type TEXT,
            payment_method TEXT,
            channel TEXT,
            trade_time TEXT,
            is_high_risk_region INTEGER,
            risk_probability REAL,
            risk_label INTEGER,
            risk_level TEXT,
            processed_at TEXT,
            raw_data TEXT,
            hit_count INTEGER DEFAULT 0,
            hit_summary TEXT,
            manual_label INTEGER DEFAULT NULL
        );

        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_id TEXT,
            customer_id TEXT,
            amount REAL,
            fund_name TEXT,
            fund_code TEXT,
            region_name TEXT,
            transaction_type TEXT,
            payment_method TEXT,
            channel TEXT,
            trade_time TEXT,
            is_high_risk_region INTEGER,
            risk_probability REAL,
            risk_label INTEGER,
            risk_level TEXT,
            processed_at TEXT,
            hit_count INTEGER DEFAULT 0,
            hit_summary TEXT,
            review_status TEXT DEFAULT 'pending',
            review_comment TEXT,
            reviewed_at TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_tx_time ON transactions(processed_at);
        CREATE INDEX IF NOT EXISTS idx_tx_risk ON transactions(risk_label);
        CREATE INDEX IF NOT EXISTS idx_alert_time ON alerts(processed_at);
        CREATE INDEX IF NOT EXISTS idx_tx_customer ON transactions(customer_id);
        CREATE INDEX IF NOT EXISTS idx_tx_customer_date ON transactions(customer_id, trade_time);
        CREATE INDEX IF NOT EXISTS idx_tx_fund ON transactions(fund_code, trade_time);
    """)
    conn.commit()
    try:
        conn.execute("ALTER TABLE transactions ADD COLUMN manual_label INTEGER DEFAULT NULL")
        conn.commit()
    except Exception:
        pass
    print(f"Database initialized at {DB_PATH}")


def save_transaction(record: dict, raw_tx: dict = None):
    """Save transaction record"""
    conn = get_conn()
    conn.execute("""
        INSERT INTO transactions 
        (transaction_id, customer_id, amount, fund_name, fund_code, region_name,
         transaction_type, payment_method, channel, trade_time, is_high_risk_region,
         risk_probability, risk_label, risk_level, processed_at, raw_data, hit_count, hit_summary)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        record.get("transaction_id"),
        record.get("customer_id"),
        record.get("amount"),
        record.get("fund_name"),
        record.get("fund_code"),
        record.get("region_name"),
        record.get("transaction_type"),
        record.get("payment_method"),
        record.get("channel"),
        record.get("trade_time"),
        int(record.get("is_high_risk_region", 0)),
        record.get("risk_probability"),
        record.get("risk_label"),
        record.get("risk_level"),
        record.get("processed_at"),
        json.dumps(raw_tx, ensure_ascii=False) if raw_tx else None,
        record.get("hit_count", 0),
        record.get("hit_summary", ""),
    ))
    conn.commit()


def save_alert(record: dict):
    """Save alert record"""
    conn = get_conn()
    conn.execute("""
        INSERT INTO alerts
        (transaction_id, customer_id, amount, fund_name, fund_code, region_name,
         transaction_type, payment_method, channel, trade_time, is_high_risk_region,
         risk_probability, risk_label, risk_level, processed_at, hit_count, hit_summary)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        record.get("transaction_id"),
        record.get("customer_id"),
        record.get("amount"),
        record.get("fund_name"),
        record.get("fund_code"),
        record.get("region_name"),
        record.get("transaction_type"),
        record.get("payment_method"),
        record.get("channel"),
        record.get("trade_time"),
        int(record.get("is_high_risk_region", 0)),
        record.get("risk_probability"),
        record.get("risk_label"),
        record.get("risk_level"),
        record.get("processed_at"),
        record.get("hit_count", 0),
        record.get("hit_summary", ""),
    ))
    conn.commit()


def get_stats():
    """Get statistics from database"""
    try:
        conn = get_conn()
        total = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
        total_alerts = conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]
        pending_alerts = conn.execute("SELECT COUNT(*) FROM alerts WHERE review_status = 'pending'").fetchone()[0]

        dist = {}
        rows = conn.execute("SELECT risk_level, COUNT(*) as cnt FROM transactions GROUP BY risk_level").fetchall()
        for row in rows:
            dist[row["risk_level"]] = row["cnt"]

        return {
            "total_processed": total,
            "total_alerts": total_alerts,
            "pending_alerts": pending_alerts,
            "risk_distribution": dist,
        }
    except Exception as e:
        print(f"get_stats error: {e}")
        return {"total_processed": 0, "total_alerts": 0, "pending_alerts": 0, "risk_distribution": {}}


def get_recent_transactions(limit=100, offset=0):
    """Get recent transaction records"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM transactions ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset)
    ).fetchall()
    return [dict(r) for r in rows]


def get_recent_alerts(limit=50, offset=0):
    """Get recent pending alerts"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM alerts WHERE review_status = 'pending' ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset)
    ).fetchall()
    return [dict(r) for r in rows]


def review_alert(alert_id, status, comment=""):
    """Review alert: status = 'approved' or 'rejected'"""
    conn = get_conn()
    conn.execute(
        "UPDATE alerts SET review_status = ?, review_comment = ?, reviewed_at = ? WHERE id = ?",
        (status, comment, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), alert_id)
    )
    conn.commit()


def get_realtime_context(customer_id, fund_code, region_name, today_str):
    """
    Real-time global context features for ML model.
    Provides comparison data against market averages.
    """
    try:
        conn = get_conn()

        row = conn.execute(
            "SELECT COUNT(*) as cnt, COALESCE(SUM(amount),0) as total FROM transactions WHERE customer_id=? AND trade_time LIKE ?",
            (customer_id, today_str + "%")
        ).fetchone()
        customer_today_count = row["cnt"]
        customer_today_amount = row["total"]

        row = conn.execute(
            "SELECT COUNT(*) as cnt, COALESCE(SUM(amount),0) as total FROM transactions WHERE fund_code=? AND trade_time LIKE ?",
            (fund_code, today_str + "%")
        ).fetchone()
        fund_today_count = row["cnt"]
        fund_today_amount = row["total"]

        row = conn.execute(
            "SELECT COUNT(*) as cnt, COALESCE(SUM(amount),0) as total FROM transactions WHERE region_name=? AND trade_time LIKE ?",
            (region_name, today_str + "%")
        ).fetchone()
        region_today_count = row["cnt"]
        region_today_amount = row["total"]

        row = conn.execute(
            "SELECT COUNT(*) as cnt, COALESCE(SUM(amount),0) as total FROM transactions WHERE trade_time LIKE ?",
            (today_str + "%",)
        ).fetchone()
        market_today_count = row["cnt"]
        market_today_amount = row["total"]

        row = conn.execute(
            "SELECT COUNT(DISTINCT fund_code) as cnt FROM transactions WHERE customer_id=? AND trade_time LIKE ?",
            (customer_id, today_str + "%")
        ).fetchone()
        customer_today_fund_variety = row["cnt"]

        return {
            "ctx_customer_today_count": customer_today_count,
            "ctx_customer_today_amount": round(customer_today_amount, 2),
            "ctx_customer_today_fund_variety": customer_today_fund_variety,
            "ctx_fund_today_count": fund_today_count,
            "ctx_fund_today_amount": round(fund_today_amount, 2),
            "ctx_region_today_count": region_today_count,
            "ctx_region_today_amount": round(region_today_amount, 2),
            "ctx_market_today_count": market_today_count,
            "ctx_market_today_amount": round(market_today_amount, 2),
            "ctx_customer_share_of_fund": round(customer_today_amount / max(fund_today_amount, 1), 4),
            "ctx_customer_share_of_market": round(customer_today_amount / max(market_today_amount, 1), 4),
            "ctx_region_share_of_market": round(region_today_amount / max(market_today_amount, 1), 4),
        }
    except Exception as e:
        print(f"get_realtime_context error: {e}")
        return {
            "ctx_customer_today_count": 0, "ctx_customer_today_amount": 0,
            "ctx_customer_today_fund_variety": 0,
            "ctx_fund_today_count": 0, "ctx_fund_today_amount": 0,
            "ctx_region_today_count": 0, "ctx_region_today_amount": 0,
            "ctx_market_today_count": 0, "ctx_market_today_amount": 0,
            "ctx_customer_share_of_fund": 0, "ctx_customer_share_of_market": 0,
            "ctx_region_share_of_market": 0,
        }


def mark_transaction(tx_id, manual_label):
    """Label transaction actual risk (0=Normal, 1=High Risk)"""
    conn = get_conn()
    conn.execute(
        "UPDATE transactions SET manual_label = ? WHERE id = ?",
        (manual_label, tx_id)
    )
    conn.commit()


def get_manual_label_stats():
    """Get manual labeling statistics"""
    conn = get_conn()
    total = conn.execute("SELECT COUNT(*) FROM transactions WHERE manual_label IS NOT NULL").fetchone()[0]
    risky = conn.execute("SELECT COUNT(*) FROM transactions WHERE manual_label = 1").fetchone()[0]
    normal = conn.execute("SELECT COUNT(*) FROM transactions WHERE manual_label = 0").fetchone()[0]
    return {"total_labeled": total, "labeled_risky": risky, "labeled_normal": normal}