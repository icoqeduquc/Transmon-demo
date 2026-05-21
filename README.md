# Fund Transaction Risk Monitoring System

Real-time fund transaction risk monitoring dashboard with an XGBoost ML model and a layered rule engine. Supports live inference, stress testing, manual review, and hot retraining.

## Features

- **Real-time inference**: ~100ms per transaction, end-to-end
- **XGBoost model**: 80+ features, SHAP-based explainability, sample tree path visualization
- **Rule engine**: 9 categories / 43 deterministic rules with veto override
- **Live dashboard**: risk distribution, scatter plot, alerts queue, manual review
- **AI inference pipeline view** at `/pipeline`: animated XGBoost decision flow
- **Stress test mode**: up to 200 TPS for performance demos
- **Hot retraining**: retrain the model from accumulated transaction data without restart

## Quick Start

```bash
cd fund_risk_monitor
pip install -r requirements.txt
python web_server.py
```

Open http://localhost:5000

To start fresh (regenerate data and retrain from scratch):

```bash
python run_all.py
```

## Configuration

Edit `fund_risk_monitor/config.py`:

- `DB_PATH`: SQLite database location (defaults to `D:\fund_risk_monitor.db`; change for non-Windows)
- `RISK_THRESHOLD`: alert threshold (default 0.6)
- `NUM_TRAINING_SAMPLES`: synthetic training data size

## Project Structure

```
fund_risk_monitor/
├── web_server.py          # Flask web service (main entry)
├── run_all.py             # End-to-end pipeline
├── data_generator.py      # Synthetic transaction generator
├── train_model.py         # XGBoost training
├── realtime_monitor.py    # File-watcher inference service
├── rule_engine.py         # Layered rule matching
├── database.py            # SQLite persistence
├── config.py              # Paths and thresholds
├── templates/             # HTML dashboards
├── models/                # Pre-trained XGBoost model
└── data/                  # Rules, feature config, runtime files
```

## Tech Stack

Python 3.11 · Flask · XGBoost · scikit-learn · pandas · SQLite · vanilla JS (no frontend framework)
