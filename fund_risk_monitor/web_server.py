# -*- coding: utf-8 -*-
"""
Risk Monitoring Web Service
Provides REST API + frontend dashboard
"""

import json
import os
import time
import threading
from datetime import datetime
from collections import deque

import pandas as pd
from flask import Flask, jsonify, render_template, request

import random

from config import (
    INCOMING_DIR, ALERT_DIR, DATA_DIR,
    MODEL_FILE, FEATURE_COLUMNS_FILE, RISK_THRESHOLD, RISK_RULES_FILE,
    MODEL_HISTORY_DIR, MODEL_DIR
)
from train_model import prepare_features
from data_generator import generate_transaction
from database import init_db, save_transaction, save_alert, get_stats, get_recent_transactions, get_recent_alerts, review_alert, get_realtime_context, mark_transaction, get_manual_label_stats
from rule_engine import match_rules, load_rules

import joblib
import xgboost as xgb
import numpy as np
import re

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config['TEMPLATES_AUTO_RELOAD'] = True

# In-memory cache for fast response
recent_transactions = deque(maxlen=500)
recent_alerts = deque(maxlen=200)
start_time = None

# === Transaction Control State ===
tx_control = {
    "paused": False,
    "mode": "normal",          # normal / stress
    "stress_tps": 50,
    "training": False,
    "train_progress": "",
    "perf_stats": {
        "avg_inference_ms": 0,
        "avg_rule_ms": 0,
        "avg_total_ms": 0,
        "peak_tps": 0,
        "recent_tps": 0,
    },
}
_tps_counter = {"count": 0, "last_reset": time.time()}

model = None
feature_columns = None
active_model_version = "current"  # tracks which version is active


def load_model():
    global model, feature_columns, active_model_version
    model = joblib.load(MODEL_FILE)
    feature_columns = joblib.load(FEATURE_COLUMNS_FILE)
    active_model_version = "current"
    print(f"Model loaded, feature count: {len(feature_columns)}")


def archive_current_model():
    """Save current model as a timestamped snapshot before overwriting."""
    os.makedirs(MODEL_HISTORY_DIR, exist_ok=True)
    if not os.path.exists(MODEL_FILE):
        return None
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    tag = f"model_{ts}"
    dst_model = os.path.join(MODEL_HISTORY_DIR, f"{tag}.joblib")
    dst_feat = os.path.join(MODEL_HISTORY_DIR, f"{tag}_features.joblib")
    import shutil
    shutil.copy2(MODEL_FILE, dst_model)
    if os.path.exists(FEATURE_COLUMNS_FILE):
        shutil.copy2(FEATURE_COLUMNS_FILE, dst_feat)
    print(f"Archived current model as {tag}")
    return tag


def list_model_versions():
    """Return list of available model versions."""
    versions = [{"name": "current", "label": "Current (Active)", "path": MODEL_FILE,
                 "time": datetime.fromtimestamp(os.path.getmtime(MODEL_FILE)).strftime("%Y-%m-%d %H:%M:%S") if os.path.exists(MODEL_FILE) else ""}]
    if os.path.exists(MODEL_HISTORY_DIR):
        files = sorted([f for f in os.listdir(MODEL_HISTORY_DIR) if f.endswith(".joblib") and not f.endswith("_features.joblib")], reverse=True)
        for f in files:
            name = f.replace(".joblib", "")
            fpath = os.path.join(MODEL_HISTORY_DIR, f)
            mtime = datetime.fromtimestamp(os.path.getmtime(fpath)).strftime("%Y-%m-%d %H:%M:%S")
            versions.append({"name": name, "label": name, "path": fpath, "time": mtime})
    return versions


def predict_risk(tx: dict) -> dict:
    df = pd.DataFrame([tx])
    X = prepare_features(df)
    for col in feature_columns:
        if col not in X.columns:
            X[col] = 0
    X = X[feature_columns]
    raw_prob = float(model.predict_proba(X)[0][1])

    import math
    temperature = 0.3
    if raw_prob > 0 and raw_prob < 1:
        logit = math.log(raw_prob / (1 - raw_prob))
        prob = 1 / (1 + math.exp(-logit * temperature))
    else:
        prob = raw_prob

    label = 1 if prob >= RISK_THRESHOLD else 0
    if prob >= 0.8:
        level = "Critical"
    elif prob >= 0.6:
        level = "High"
    elif prob >= 0.4:
        level = "Medium"
    elif prob >= 0.2:
        level = "Low"
    else:
        level = "Normal"
    return {"risk_probability": round(prob, 4), "risk_label": label, "risk_level": level}


def get_inference_detail(tx: dict) -> dict:
    """
    Extract XGBoost model inference details for a transaction:
    - Feature contributions (SHAP values)
    - Sampled tree decision paths
    - Per-tree leaf node scores
    """
    df = pd.DataFrame([tx])
    X = prepare_features(df)
    for col in feature_columns:
        if col not in X.columns:
            X[col] = 0
    X = X[feature_columns]

    booster = model.get_booster()
    dmat = xgb.DMatrix(X.values, feature_names=list(feature_columns))

    contribs = booster.predict(dmat, pred_contribs=True)[0]
    bias = float(contribs[-1])
    feat_contribs = contribs[:-1]
    top_idx = np.argsort(np.abs(feat_contribs))[::-1][:10]
    top_features = []
    for i in top_idx:
        top_features.append({
            "name": feature_columns[i],
            "contribution": round(float(feat_contribs[i]), 4),
            "value": round(float(X.iloc[0, i]), 4),
            "direction": "risk" if feat_contribs[i] > 0 else "safe",
        })

    leaves = booster.predict(dmat, pred_leaf=True)[0]

    tree_dumps = booster.get_dump()
    sample_trees = []
    sample_indices = list(range(0, min(len(tree_dumps), 200), 25))[:8]

    for ti in sample_indices:
        tree_text = tree_dumps[ti]
        leaf_id = int(leaves[ti])
        path = _trace_tree_path(tree_text, leaf_id, X.iloc[0])
        sample_trees.append({
            "tree_index": ti,
            "leaf_id": leaf_id,
            "path": path,
        })

    margin = float(booster.predict(dmat, output_margin=True)[0])

    return {
        "top_features": top_features,
        "bias": bias,
        "margin": round(margin, 4),
        "n_trees": len(tree_dumps),
        "sample_trees": sample_trees,
    }


def _trace_tree_path(tree_text: str, target_leaf: int, sample):
    """Parse a tree's text and trace sample's path to leaf node"""
    nodes = {}
    for line in tree_text.strip().split('\n'):
        line = line.strip()
        m = re.match(r'(\d+):\[(\w+)<([\d.e+-]+)\]\s*yes=(\d+),no=(\d+)', line)
        if m:
            nid, feat, thresh, yes, no = m.groups()
            nodes[int(nid)] = {"type": "split", "feature": feat, "threshold": float(thresh), "yes": int(yes), "no": int(no)}
            continue
        m = re.match(r'(\d+):leaf=([\d.e+-]+)', line)
        if m:
            nid, val = m.groups()
            nodes[int(nid)] = {"type": "leaf", "value": float(val)}

    path = []
    current = 0
    max_depth = 10
    for _ in range(max_depth):
        if current not in nodes:
            break
        node = nodes[current]
        if node["type"] == "leaf":
            path.append({"node_id": current, "type": "leaf", "score": round(node["value"], 4)})
            break
        feat = node["feature"]
        thresh = node["threshold"]
        feat_val = float(sample[feat]) if feat in sample.index else 0.0
        go_left = feat_val < thresh
        path.append({
            "node_id": current,
            "type": "split",
            "feature": feat,
            "threshold": round(thresh, 2),
            "sample_value": round(feat_val, 2),
            "direction": "yes" if go_left else "no",
            "condition": f"{feat} < {round(thresh, 2)}",
            "result": "Yes" if go_left else "No",
        })
        current = node["yes"] if go_left else node["no"]

    return path


def simulate_realtime_transactions():
    """Background thread: continuously generate simulated transactions with real-time inference"""
    seq = 0
    perf_window = deque(maxlen=100)
    _ctx_cache = {}
    _ctx_cache_time = 0

    while True:
        try:
            if tx_control["paused"]:
                time.sleep(0.5)
                continue

            if tx_control["mode"] == "stress":
                tps = tx_control["stress_tps"]
                time.sleep(1.0 / max(tps, 1))
            else:
                time.sleep(random.uniform(0.5, 2.5))

            t0 = time.time()

            force_risky = random.random() < 0.05
            tx = generate_transaction(force_risky=force_risky)

            now = time.time()
            if now - _ctx_cache_time > 10:
                today_str = datetime.now().strftime("%Y-%m-%d")
                try:
                    _ctx_cache = get_realtime_context(
                        tx.get("customer_id", ""),
                        tx.get("fund_code", ""),
                        tx.get("region_name", ""),
                        today_str
                    )
                    _ctx_cache_time = now
                except Exception:
                    pass
            tx.update(_ctx_cache)

            t1 = time.time()
            rule_result = match_rules(tx)
            tx["rule_hit_count"] = rule_result["hit_count"]
            tx["rule_hit_category_count"] = rule_result["hit_category_count"]
            tx["rule_has_veto"] = int(any(
                r.get("veto") for cat in rule_result["hit_categories"] for r in cat["hit_rules"]
            ))
            t2 = time.time()
            time.sleep(0.01)
            result = predict_risk(tx)
            t3 = time.time()

            # === Rule veto override ===
            veto_hit = bool(tx["rule_has_veto"])
            if veto_hit and result["risk_label"] == 0:
                result["risk_label"] = 1
                result["risk_level"] = max(result["risk_level"], "High") if result["risk_probability"] >= 0.4 else "High"
                result["rule_override"] = True
            else:
                result["rule_override"] = False

            if tx_control["mode"] == "stress":
                inference_detail = {}
            else:
                try:
                    inference_detail = get_inference_detail(tx)
                except Exception:
                    inference_detail = {}
                time.sleep(0.01)

            seq += 1

            record = {
                "transaction_id": tx.get("transaction_id", "")[:12],
                "customer_id": tx.get("customer_id", ""),
                "amount": tx.get("amount", 0),
                "fund_name": tx.get("fund_name", ""),
                "fund_code": tx.get("fund_code", ""),
                "region_name": tx.get("region_name", ""),
                "transaction_type": tx.get("transaction_type", ""),
                "payment_method": tx.get("payment_method", ""),
                "channel": tx.get("channel", ""),
                "trade_time": tx.get("trade_time", ""),
                "is_high_risk_region": tx.get("is_high_risk_region", False),
                "recent_tx_count_7d": tx.get("recent_tx_count_7d", 0),
                "recent_tx_amount_7d": tx.get("recent_tx_amount_7d", 0),
                "account_age_days": tx.get("account_age_days", 0),
                "ip_change_count_7d": tx.get("ip_change_count_7d", 0),
                "login_fail_count_24h": tx.get("login_fail_count_24h", 0),
                "aml_flag": tx.get("aml_flag", 0),
                "kyc_score": tx.get("kyc_score", 0),
                "device_change_count_7d": tx.get("device_change_count_7d", 0),
                "same_day_tx_count": tx.get("same_day_tx_count", 0),
                "blacklist_hit": tx.get("blacklist_hit", False),
                "watchlist_hit": tx.get("watchlist_hit", False),
                **result,
                "hit_count": rule_result["hit_count"],
                "hit_category_count": rule_result["hit_category_count"],
                "hit_summary": rule_result["hit_summary"],
                "hit_categories": rule_result["hit_categories"],
                "rule_override": result.get("rule_override", False),
                "inference_detail": inference_detail,
                "processed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            recent_transactions.appendleft(record)
            save_transaction(record, raw_tx=tx)
            try:
                from database import get_conn as _gc2
                record["id"] = _gc2().execute("SELECT last_insert_rowid()").fetchone()[0]
            except Exception:
                pass
            time.sleep(0.01)

            t4 = time.time()

            rule_ms = (t2 - t1) * 1000
            inference_ms = (t3 - t2) * 1000
            total_ms = (t4 - t0) * 1000
            perf_window.append({"inference": inference_ms, "rule": rule_ms, "total": total_ms})

            _tps_counter["count"] += 1
            elapsed = time.time() - _tps_counter["last_reset"]
            if elapsed >= 2.0:
                current_tps = _tps_counter["count"] / elapsed
                tx_control["perf_stats"]["recent_tps"] = round(current_tps, 1)
                if current_tps > tx_control["perf_stats"]["peak_tps"]:
                    tx_control["perf_stats"]["peak_tps"] = round(current_tps, 1)
                _tps_counter["count"] = 0
                _tps_counter["last_reset"] = time.time()

            if perf_window:
                tx_control["perf_stats"]["avg_inference_ms"] = round(sum(p["inference"] for p in perf_window) / len(perf_window), 2)
                tx_control["perf_stats"]["avg_rule_ms"] = round(sum(p["rule"] for p in perf_window) / len(perf_window), 2)
                tx_control["perf_stats"]["avg_total_ms"] = round(sum(p["total"] for p in perf_window) / len(perf_window), 2)

            if tx_control["mode"] != "stress" or seq % 50 == 0:
                level_icon = "[RISK]" if result["risk_label"] == 1 else "[OK]"
                print(f"  {level_icon} #{seq} {record['customer_id']} | {record['fund_name']} | "
                      f"${record['amount']:,.2f} | {result['risk_level']} ({result['risk_probability']:.1%})"
                      f" [{total_ms:.0f}ms]")

            if result["risk_label"] == 1:
                save_alert(record)
                from database import get_conn
                last_id = get_conn().execute("SELECT last_insert_rowid()").fetchone()[0]
                record["id"] = last_id
                record["_review_status"] = "pending"
                recent_alerts.appendleft(record)

        except Exception as e:
            print(f"Simulation thread error: {e}")
            import traceback
            traceback.print_exc()


# ============ API Routes ============

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/pipeline")
def pipeline():
    return render_template("pipeline.html")


@app.route("/api/stats")
def api_stats():
    uptime = ""
    if start_time:
        delta = datetime.now() - start_time
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    db_stats = get_stats()
    total = db_stats["total_processed"]
    total_alerts = db_stats["total_alerts"]
    alert_rate = round(total_alerts / total * 100, 1) if total > 0 else 0

    # Normalize both Chinese (legacy) and English risk level keys
    _cn_to_en = {"正常": "Normal", "低风险": "Low", "中风险": "Medium", "高风险": "High", "极高风险": "Critical"}
    dist = {"Normal": 0, "Low": 0, "Medium": 0, "High": 0, "Critical": 0}
    for k, v in db_stats["risk_distribution"].items():
        en_key = _cn_to_en.get(k, k)  # map Chinese to English, keep English as-is
        if en_key in dist:
            dist[en_key] += v

    return jsonify({
        "total_processed": total,
        "total_alerts": total_alerts,
        "pending_alerts": db_stats["pending_alerts"],
        "alert_rate": alert_rate,
        "uptime": uptime,
        "risk_distribution": dist,
    })


@app.route("/api/timeline")
def api_timeline():
    """Recent transaction timeline data (aggregated by second)"""
    from database import get_conn as _gc
    conn = _gc()
    rows = conn.execute(
        "SELECT processed_at, risk_label, amount FROM transactions ORDER BY id DESC LIMIT 200"
    ).fetchall()
    buckets = {}
    for row in rows:
        ts = row["processed_at"]
        if not ts:
            continue
        sec = ts[:19]
        if sec not in buckets:
            buckets[sec] = {"time": sec[11:], "total": 0, "risk": 0, "amount": 0}
        buckets[sec]["total"] += 1
        buckets[sec]["risk"] += row["risk_label"]
        buckets[sec]["amount"] += round(row["amount"], 0)
    timeline = sorted(buckets.values(), key=lambda x: x["time"])[-30:]
    return jsonify(timeline)


@app.route("/api/review_stats")
def api_review_stats():
    """Review statistics"""
    from database import get_conn as _gc
    conn = _gc()
    total_alerts = conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]
    pending = conn.execute("SELECT COUNT(*) FROM alerts WHERE review_status='pending'").fetchone()[0]
    approved = conn.execute("SELECT COUNT(*) FROM alerts WHERE review_status='approved'").fetchone()[0]
    rejected = conn.execute("SELECT COUNT(*) FROM alerts WHERE review_status='rejected'").fetchone()[0]
    return jsonify({
        "total": total_alerts, "pending": pending,
        "approved": approved, "rejected": rejected,
        "reviewed": approved + rejected,
        "approve_rate": round(approved / max(approved + rejected, 1) * 100, 1),
    })


@app.route("/api/features")
def api_features():
    """Return all model features and their importance"""
    importance = model.feature_importances_
    features = []
    for i, col in enumerate(feature_columns):
        imp = float(importance[i])
        if "_" in col and any(col.startswith(p + "_") for p in [
            "transaction_type", "fund_type", "fund_company_rating",
            "investor_type", "channel", "payment_method", "currency", "id_type"
        ]):
            source = "One-Hot Encoded"
        elif col in ["amount_per_tx_7d", "tx_frequency_ratio", "risk_mismatch", "new_account_large_tx"]:
            source = "Derived Feature"
        elif col in ["is_high_risk_region", "is_qualified_investor", "is_new_device",
                      "is_large_transaction", "is_cross_border", "is_related_party",
                      "blacklist_hit", "watchlist_hit", "is_trading_hours",
                      "is_month_end", "is_quarter_end"]:
            source = "Boolean Feature"
        else:
            source = "Numeric Feature"
        features.append({"name": col, "importance": round(imp, 6), "source": source})
    features.sort(key=lambda x: x["importance"], reverse=True)
    return jsonify({"total": len(features), "features": features})


@app.route("/api/feature_config")
def api_feature_config():
    """Get feature configuration"""
    cfg_path = os.path.join(DATA_DIR, "feature_config.json")
    if os.path.exists(cfg_path):
        with open(cfg_path, "r", encoding="utf-8") as f:
            return jsonify(json.load(f))
    return jsonify({})


@app.route("/api/feature_config", methods=["POST"])
def api_save_feature_config():
    """Save feature configuration and retrain model"""
    data = request.get_json()
    cfg_path = os.path.join(DATA_DIR, "feature_config.json")
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    enabled = 0
    for group in ["numeric_features", "boolean_features", "categorical_features", "derived_features"]:
        for feat in data.get(group, []):
            if feat.get("enabled", True):
                enabled += 1

    return jsonify({"success": True, "message": f"Feature config saved ({enabled} enabled). Please click Retrain Model."})


@app.route("/api/transactions")
def api_transactions():
    limit = request.args.get("limit", 100, type=int)
    offset = request.args.get("offset", 0, type=int)
    if offset == 0:
        mem = list(recent_transactions)[:limit]
        if mem:
            return jsonify(mem)
    return jsonify(get_recent_transactions(limit, offset))


@app.route("/api/alerts")
def api_alerts():
    limit = request.args.get("limit", 50, type=int)
    offset = request.args.get("offset", 0, type=int)
    if offset == 0:
        mem_alerts = [a for a in list(recent_alerts)[:200] if a.get("_review_status", "pending") == "pending"]
        if len(mem_alerts) >= 3:
            return jsonify(mem_alerts[:limit])
    return jsonify(get_recent_alerts(limit, offset))


@app.route("/api/rules")
def api_rules():
    if os.path.exists(RISK_RULES_FILE):
        with open(RISK_RULES_FILE, "r", encoding="utf-8") as f:
            return jsonify(json.load(f))
    return jsonify([])


@app.route("/api/rules/veto", methods=["POST"])
def api_toggle_veto():
    """Toggle sub-rule veto status"""
    data = request.get_json()
    rule_id = data.get("rule_id")
    veto = data.get("veto", False)
    if not rule_id:
        return jsonify({"error": "Missing rule_id"}), 400

    if not os.path.exists(RISK_RULES_FILE):
        return jsonify({"error": "Rules file not found"}), 404

    with open(RISK_RULES_FILE, "r", encoding="utf-8") as f:
        rules = json.load(f)

    found = False
    for cat in rules:
        for sub in cat.get("sub_rules", []):
            if sub["rule_id"] == rule_id:
                sub["veto"] = veto
                found = True
                break
        if found:
            break

    if not found:
        return jsonify({"error": f"Rule {rule_id} not found"}), 404

    with open(RISK_RULES_FILE, "w", encoding="utf-8") as f:
        json.dump(rules, f, ensure_ascii=False, indent=2)

    from rule_engine import _rules_cache
    import rule_engine
    rule_engine._rules_cache = None

    status = "Enabled" if veto else "Disabled"
    return jsonify({"success": True, "message": f"Rule {rule_id} veto {status}"})


@app.route("/api/review", methods=["POST"])
def api_review():
    data = request.get_json()
    alert_id = data.get("alert_id")
    status = data.get("status", "approved")
    comment = data.get("comment", "")
    if not alert_id:
        return jsonify({"error": "Missing alert_id"}), 400
    review_alert(alert_id, status, comment)
    for a in recent_alerts:
        if a.get("id") == alert_id:
            a["_review_status"] = status
            break
    return jsonify({"success": True, "message": f"Alert {alert_id} reviewed: {status}"})


@app.route("/api/mark_transaction", methods=["POST"])
def api_mark_transaction():
    """Post-hoc label transaction actual risk"""
    data = request.get_json()
    tx_id = data.get("tx_id")
    label = data.get("label")
    if tx_id is None or label is None:
        return jsonify({"error": "Missing tx_id or label"}), 400
    mark_transaction(tx_id, int(label))
    label_text = "✅ High Risk" if label == 1 else "✅ Normal"
    return jsonify({"success": True, "message": f"Transaction {tx_id} labeled as: {label_text}"})


@app.route("/api/label_stats")
def api_label_stats():
    """Get manual labeling statistics"""
    return jsonify(get_manual_label_stats())

@app.route("/api/control", methods=["POST"])
def api_control():
    """Transaction control: pause/resume/stress test"""
    data = request.get_json()
    action = data.get("action")

    if action == "pause":
        tx_control["paused"] = True
        tx_control["mode"] = "normal"
        return jsonify({"success": True, "message": "Transactions paused"})

    elif action == "resume":
        tx_control["paused"] = False
        tx_control["mode"] = "normal"
        return jsonify({"success": True, "message": "Transactions resumed (normal mode)"})

    elif action == "stress":
        tps = data.get("tps", 50)
        tx_control["paused"] = False
        tx_control["mode"] = "stress"
        tx_control["stress_tps"] = max(1, min(tps, 200))
        tx_control["perf_stats"]["peak_tps"] = 0
        return jsonify({"success": True, "message": f"Stress test started (target {tx_control['stress_tps']} TPS)"})

    elif action == "stop_stress":
        tx_control["mode"] = "normal"
        return jsonify({"success": True, "message": "Stress test stopped, back to normal mode"})

    return jsonify({"error": "Unknown action"}), 400


@app.route("/api/control/status")
def api_control_status():
    """Get current control state and performance metrics"""
    return jsonify({
        "paused": tx_control["paused"],
        "mode": tx_control["mode"],
        "stress_tps": tx_control["stress_tps"],
        "training": tx_control["training"],
        "train_progress": tx_control["train_progress"],
        "perf_stats": tx_control["perf_stats"],
        "active_model": active_model_version,
    })


@app.route("/api/retrain", methods=["POST"])
def api_retrain():
    """Retrain model with existing transaction data"""
    if tx_control["training"]:
        return jsonify({"error": "Model is currently training, please wait"}), 400

    def _do_retrain():
        global model, feature_columns
        try:
            tx_control["training"] = True
            tx_control["train_progress"] = "Exporting training data from database..."
            print("\n" + "=" * 60)
            print("Starting model retraining with existing transaction data")
            print("=" * 60)

            from database import get_conn
            conn = get_conn()
            rows = conn.execute(
                "SELECT raw_data, risk_label, manual_label FROM transactions WHERE raw_data IS NOT NULL"
            ).fetchall()

            if len(rows) < 50:
                tx_control["train_progress"] = f"Insufficient data: only {len(rows)} records (need at least 50)"
                tx_control["training"] = False
                return

            manual_count = sum(1 for r in rows if r["manual_label"] is not None)
            tx_control["train_progress"] = f"Exported {len(rows)} records ({manual_count} manually labeled), preparing features..."

            records = []
            for row in rows:
                try:
                    raw = json.loads(row["raw_data"])
                    if row["manual_label"] is not None:
                        raw["risk_label"] = row["manual_label"]
                    else:
                        raw["risk_label"] = row["risk_label"]
                    if "rule_hit_count" not in raw:
                        rr = match_rules(raw)
                        raw["rule_hit_count"] = rr["hit_count"]
                        raw["rule_hit_category_count"] = rr["hit_category_count"]
                        raw["rule_has_veto"] = int(any(r.get("veto") for cat in rr["hit_categories"] for r in cat["hit_rules"]))
                    records.append(raw)
                except Exception:
                    continue

            df = pd.DataFrame(records)
            tx_control["train_progress"] = f"Feature engineering... ({len(df)} records)"

            X = prepare_features(df)
            y = df["risk_label"]

            new_feature_columns = list(X.columns)

            tx_control["train_progress"] = f"Training XGBoost model... ({len(X)} samples, {len(new_feature_columns)} features)"

            from sklearn.model_selection import train_test_split
            from sklearn.metrics import roc_auc_score, classification_report
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.2, random_state=42,
                stratify=y if y.nunique() > 1 else None
            )

            new_model = xgb.XGBClassifier(
                n_estimators=200, max_depth=6, learning_rate=0.1,
                subsample=0.8, colsample_bytree=0.8,
                scale_pos_weight=len(y_train[y_train == 0]) / max(len(y_train[y_train == 1]), 1),
                random_state=42, eval_metric="logloss",
            )
            new_model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)

            y_prob = new_model.predict_proba(X_test)[:, 1]
            try:
                auc = roc_auc_score(y_test, y_prob)
            except Exception:
                auc = 0.0

            tx_control["train_progress"] = f"Training complete! AUC={auc:.4f}, archiving old model..."
            archive_current_model()

            joblib.dump(new_model, MODEL_FILE)
            joblib.dump(new_feature_columns, FEATURE_COLUMNS_FILE)
            model = new_model
            feature_columns = new_feature_columns
            active_model_version = "current"
            print(f"Model hot-swapped, AUC={auc:.4f}, samples={len(X)}, features={len(new_feature_columns)}")

            tx_control["train_progress"] = f"✅ Complete! Samples={len(X)}, AUC={auc:.4f}, model hot-swapped"
            time.sleep(3)
            tx_control["training"] = False

        except Exception as e:
            tx_control["train_progress"] = f"❌ Training failed: {str(e)}"
            tx_control["training"] = False
            import traceback
            traceback.print_exc()

    t = threading.Thread(target=_do_retrain, daemon=True)
    t.start()
    return jsonify({"success": True, "message": "Model retraining started (running in background)"})


@app.route("/api/model_versions")
def api_model_versions():
    """List all available model versions"""
    versions = list_model_versions()
    return jsonify({"active": active_model_version, "versions": versions})


@app.route("/api/switch_model", methods=["POST"])
def api_switch_model():
    """Switch to a specific model version"""
    global model, feature_columns, active_model_version
    data = request.get_json()
    version_name = data.get("version")
    if not version_name:
        return jsonify({"error": "Missing version name"}), 400

    try:
        if version_name == "current":
            model = joblib.load(MODEL_FILE)
            feature_columns = joblib.load(FEATURE_COLUMNS_FILE)
            active_model_version = "current"
        else:
            model_path = os.path.join(MODEL_HISTORY_DIR, f"{version_name}.joblib")
            feat_path = os.path.join(MODEL_HISTORY_DIR, f"{version_name}_features.joblib")
            if not os.path.exists(model_path):
                return jsonify({"error": f"Model version '{version_name}' not found"}), 404
            model = joblib.load(model_path)
            if os.path.exists(feat_path):
                feature_columns = joblib.load(feat_path)
            active_model_version = version_name

        print(f"Switched to model version: {version_name}, features: {len(feature_columns)}")
        return jsonify({"success": True, "message": f"Switched to model: {version_name}", "feature_count": len(feature_columns)})
    except Exception as e:
        return jsonify({"error": f"Failed to load model: {str(e)}"}), 500


def main():
    load_model()
    init_db()
    global start_time
    start_time = datetime.now()
    os.makedirs(INCOMING_DIR, exist_ok=True)

    t = threading.Thread(target=simulate_realtime_transactions, daemon=True)
    t.start()
    print("Real-time simulation thread started (generating one transaction every 0.5~2.5s)")

    print("=" * 60)
    print("Risk Monitoring Dashboard started")
    print("Visit http://localhost:5000")
    print("=" * 60)
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)


if __name__ == "__main__":
    main()
