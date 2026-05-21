# Fund Risk Monitor

A real-time fund transaction risk monitoring platform powered by **XGBoost + Rule Engine**, featuring data simulation, model training, real-time inference, rule matching, and a live Web dashboard.

---

## Table of Contents

- [System Architecture](#system-architecture)
- [Module Overview](#module-overview)
- [Prerequisites & Dependencies](#prerequisites--dependencies)
- [Quick Start](#quick-start)
- [Directory Structure](#directory-structure)
- [API Reference](#api-reference)
- [Configuration](#configuration)

---

## System Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                     Web Dashboard (Flask)                     │
│             index.html (Dashboard) / pipeline.html (Pipeline) │
├──────────────────────────────────────────────────────────────┤
│                       REST API Layer                          │
│   /api/stats  /api/transactions  /api/alerts  /api/rules ... │
├──────────┬───────────────┬───────────────┬───────────────────┤
│   Data   │  Rule Engine  │  XGBoost ML   │  SQLite Database  │
│ Simulator│  (40+ rules)  │  Inference    │  Persistence      │
└──────────┴───────────────┴───────────────┴───────────────────┘
```

**Data Flow:**

```
Simulated TX Generation → Real-time Context Injection → Rule Engine Matching
    → XGBoost Risk Inference → SQLite Persistence (transactions / alerts)
    → Web Dashboard Live Display
```

---

## Module Overview

### 1. `config.py` — Global Configuration

| Setting | Description |
|---------|-------------|
| `BASE_DIR` | Project root directory |
| `DATA_DIR` | Data directory (training data, rules, alerts) |
| `INCOMING_DIR` | Directory for simulated real-time transaction JSONs |
| `MODEL_DIR` | Model storage directory |
| `MODEL_HISTORY_DIR` | Historical model versions directory |
| `DB_PATH` | SQLite database path (project-local) |
| `RISK_THRESHOLD` | Risk probability threshold, default 0.6 |
| `NUM_TRAINING_SAMPLES` | Training data size, default 10,000 |
| `NUM_REALTIME_SAMPLES` | Number of simulated real-time transactions, default 50 |

### 2. `data_generator.py` — Data Simulator

- **Purpose:** Generate simulated fund transaction data with 50+ fields
- **Transaction Styles:** normal / suspicious (gray area) / high_risk
- **Key Functions:**
  - `generate_transaction()` — Generate a single transaction (supports `force_risky` flag)
  - `label_transaction()` — Multi-dimensional feature-based labeling (0=Normal, 1=High Risk)
  - `generate_training_data()` — Batch generate training CSV (90% normal + 10% high-risk)
  - `generate_realtime_transactions()` — Generate real-time transaction JSON files
  - `generate_risk_rules_file()` — Generate layered risk control rules JSON
- **Data Dictionary:** 11 regions, 8 fund companies, 12 fund products, 6 transaction types, 6 payment methods, 6 channels

### 3. `train_model.py` — Model Training

- **Algorithm:** XGBoost Binary Classifier (XGBClassifier)
- **Feature Engineering (`prepare_features()`):**
  - **Numeric Features (27):** Amount, NAV, shares, fee rate, risk level, age, KYC score, TX frequency, etc.
  - **Boolean Features (12):** High-risk region, qualified investor, new device, large TX, cross-border, related party, blacklist, etc.
  - **Categorical Features (8):** Transaction type, fund type, rating, investor type, channel, payment method, etc. (One-Hot Encoded)
  - **Derived Features (4):** Amount per TX (7d), TX frequency ratio, risk mismatch, new account large TX
- **Hyperparameters:** 200 trees, max_depth=6, learning_rate=0.1, subsample=0.8
- **Output:** `xgb_risk_model.joblib` + `feature_columns.joblib`
- **Dynamic Feature Config:** Reads `data/feature_config.json` to enable/disable features

### 4. `rule_engine.py` — Rule Engine

- **Purpose:** Layered rule matching — 9 categories, 40+ sub-rules
- **Rule Categories:**

| Category ID | Category Name | Risk Weight | Sub-rules |
|-------------|---------------|-------------|-----------|
| C01 | AML Rules | 5 | 5 |
| C02 | Customer Identity Rules | 4 | 6 |
| C03 | Transaction Amount Rules | 3 | 5 |
| C04 | Transaction Behavior Rules | 3 | 5 |
| C05 | Region & Cross-border Rules | 4 | 3 |
| C06 | Payment Method Rules | 3 | 4 |
| C07 | Device & Network Security Rules | 3 | 5 |
| C08 | Related Party Rules | 3 | 3 |
| C09 | Global Statistical Anomaly Rules | 4 | 6 |

- **Veto Mechanism:** Certain sub-rules can be marked as "veto" — when triggered, they force an alert even if the ML model predicts low risk
- **Rules File:** `data/risk_rules.json`

### 5. `database.py` — Data Persistence

- **Database:** SQLite (WAL mode, thread-safe)
- **Tables:**
  - `transactions` — All transaction records (risk probability, risk level, hit rules, manual labels, etc.)
  - `alerts` — Alert records (review status: pending / approved / rejected)
- **Key Functions:**
  - `init_db()` — Initialize schema and indexes
  - `save_transaction()` / `save_alert()` — Insert records
  - `get_stats()` — Aggregate statistics (totals, alert counts, risk distribution)
  - `get_realtime_context()` — Real-time global context features (customer daily TX volume, fund daily volume, market share, etc.)
  - `mark_transaction()` — Manually label transaction risk
  - `review_alert()` — Review alerts

### 6. `realtime_monitor.py` — File-based Real-time Monitor

- **Purpose:** Uses watchdog to monitor `data/incoming/` directory; triggers inference when new JSON files arrive
- **Use Case:** Standalone monitoring service, independent of the Web server
- **Scans existing files first, then enters real-time watch mode**

### 7. `web_server.py` — Web Server (Main Entry Point)

- **Framework:** Flask (port 5000)
- **Features:**
  - Background thread continuously generates simulated transactions with real-time inference
  - Full REST API (stats, transactions, alerts, rules, review, labeling, model retraining, model versioning, etc.)
  - Frontend dashboard rendering
  - **Stress Test Mode:** Supports pause / resume / stress test (up to 200 TPS)
  - **Online Retraining:** Retrains model using existing transaction data (including manual labels) with hot-swap
  - **Model Versioning:** Keeps historical model snapshots; users can switch between model versions
  - **XGBoost Inference Detail:** SHAP feature contributions, decision tree path tracing
- **Pages:**
  - `/` — Risk monitoring dashboard (live stats, transaction list, alert review)
  - `/pipeline` — Data processing pipeline visualization

### 8. `run_all.py` — One-click Run (Data Generation + Training + Monitoring)

Runs sequentially: Generate rules → Generate training data → Train model → Generate real-time TXs → Start file-based monitor

### 9. `templates/` — Frontend Templates

- `index.html` — Main dashboard page
- `pipeline.html` — Data pipeline visualization page

### 10. `models/` — Model Files

- `xgb_risk_model.joblib` — Trained XGBoost model (active)
- `feature_columns.joblib` — Feature column names (ensures feature alignment during inference)
- `history/` — Historical model versions (timestamped snapshots)

### 11. `data/` — Data Directory

- `training_data.csv` — Training dataset
- `risk_rules.json` — Risk control rules configuration
- `feature_config.json` — Feature toggle configuration
- `incoming/` — Simulated real-time transaction JSON directory
- `alerts/` — Alert JSON directory

---

## Prerequisites & Dependencies

### Python Version

- **Python >= 3.9** (recommended 3.10+; tested with 3.13)

### Python Packages

| Package | Minimum Version | Purpose |
|---------|----------------|---------|
| `xgboost` | 2.0.3 | Gradient boosted tree model |
| `scikit-learn` | 1.4.0 | Data splitting, evaluation metrics |
| `pandas` | 2.1.4 | Data processing, feature engineering |
| `numpy` | 1.26.3 | Numerical computation |
| `watchdog` | 3.0.0 | File system monitoring (realtime_monitor) |
| `joblib` | 1.3.2 | Model serialization |
| `flask` | 3.0.0 | Web framework |

### System Dependencies

- **No additional system dependencies** — Uses SQLite (Python built-in), pure Python packages
- No database servers, Redis, or message queues required

### Install Dependencies

```bash
pip install -r requirements.txt
```

---

## Quick Start

### Option 1: Start Web Server Directly (Recommended)

```bash
cd fund_risk_monitor
python web_server.py
```

Visit http://localhost:5000 to see the live risk monitoring dashboard.

> The web server automatically generates simulated transactions and runs real-time inference in a background thread — no additional setup needed.

### Option 2: Full Pipeline (From Scratch)

If you don't have pre-existing model and data files:

```bash
cd fund_risk_monitor

# 1. Generate risk rules + training data
python data_generator.py

# 2. Train XGBoost model
python train_model.py

# 3. Start web server
python web_server.py
```

### Option 3: One-click Run All

```bash
cd fund_risk_monitor
python run_all.py
```

> Note: `run_all.py` ends with the file-based monitor (realtime_monitor), not the Web dashboard. Use Option 1 for the dashboard.

---

## Directory Structure

```
fund_risk_monitor/
├── config.py                  # Global configuration
├── data_generator.py          # Data simulator
├── train_model.py             # Model training
├── rule_engine.py             # Rule engine
├── database.py                # SQLite persistence
├── realtime_monitor.py        # File-based real-time monitor
├── web_server.py              # Web server (main entry point)
├── run_all.py                 # One-click run script
├── requirements.txt           # Python dependencies
├── fund_risk_monitor.db       # SQLite database file
├── templates/
│   ├── index.html             # Dashboard page
│   ├── pipeline.html          # Pipeline visualization page
│   └── pipeline.html.bak      # Backup
├── models/
│   ├── xgb_risk_model.joblib  # Active XGBoost model
│   ├── feature_columns.joblib # Feature column config
│   └── history/               # Historical model versions
└── data/
    ├── training_data.csv      # Training data
    ├── risk_rules.json        # Risk control rules
    ├── feature_config.json    # Feature toggles
    ├── incoming/              # Real-time transaction JSONs
    └── alerts/                # Alert JSONs
```

---

## API Reference

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Dashboard page |
| GET | `/pipeline` | Pipeline visualization page |
| GET | `/api/stats` | System statistics (totals, alerts, risk distribution) |
| GET | `/api/timeline` | Recent transaction timeline (aggregated per second) |
| GET | `/api/transactions` | Transaction records (supports pagination) |
| GET | `/api/alerts` | Pending alert list |
| GET | `/api/rules` | Risk control rules |
| GET | `/api/features` | Model features and importance scores |
| GET | `/api/feature_config` | Feature toggle configuration |
| GET | `/api/review_stats` | Review statistics |
| GET | `/api/label_stats` | Manual labeling statistics |
| GET | `/api/control/status` | Control status (pause/stress/performance metrics) |
| GET | `/api/model_versions` | List available model versions |
| POST | `/api/review` | Review alert (approved / rejected) |
| POST | `/api/mark_transaction` | Manually label transaction risk |
| POST | `/api/control` | Control TX flow (pause/resume/stress/stop_stress) |
| POST | `/api/retrain` | Online model retraining |
| POST | `/api/switch_model` | Switch to a specific model version |
| POST | `/api/rules/veto` | Toggle rule veto status |
| POST | `/api/feature_config` | Save feature toggle configuration |

---

## Configuration

### Risk Threshold

Edit `RISK_THRESHOLD` in `config.py` (default 0.6):
- Probability >= threshold → Flagged as high risk (risk_label=1), alert generated
- Probability < threshold → Classified as normal

### Risk Level Mapping

| Probability Range | Level |
|-------------------|-------|
| >= 0.8 | Critical |
| >= 0.6 | High |
| >= 0.4 | Medium |
| >= 0.2 | Low |
| < 0.2 | Normal |

### Online Retraining

1. Trigger via dashboard UI or `POST /api/retrain`
2. System exports existing transaction data from SQLite (prioritizes manual labels)
3. Retrains XGBoost model and hot-swaps it (no restart needed)
4. Previous model is automatically saved to `models/history/` for rollback

### Model Versioning

- Every retrain saves the previous model as a timestamped snapshot in `models/history/`
- Use the dashboard model selector or `GET /api/model_versions` to list versions
- Switch models via `POST /api/switch_model` with the desired version name
