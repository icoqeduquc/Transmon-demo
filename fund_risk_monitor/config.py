# -*- coding: utf-8 -*-
"""Project Configuration"""

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Data directory
DATA_DIR = os.path.join(BASE_DIR, "data")
INCOMING_DIR = os.path.join(DATA_DIR, "incoming")  # Simulated real-time incoming transaction JSONs
TRAINING_DATA_FILE = os.path.join(DATA_DIR, "training_data.csv")
RISK_RULES_FILE = os.path.join(DATA_DIR, "risk_rules.json")

# Model directory
MODEL_DIR = os.path.join(BASE_DIR, "models")
MODEL_FILE = os.path.join(MODEL_DIR, "xgb_risk_model.joblib")
FEATURE_COLUMNS_FILE = os.path.join(MODEL_DIR, "feature_columns.joblib")
MODEL_HISTORY_DIR = os.path.join(MODEL_DIR, "history")

# Alert directory
ALERT_DIR = os.path.join(DATA_DIR, "alerts")

# SQLite database (project-local)
DB_PATH = os.path.join(BASE_DIR, "fund_risk_monitor.db")

# Risk threshold
RISK_THRESHOLD = 0.6  # Probability above this triggers alert

# Simulated data config
NUM_TRAINING_SAMPLES = 10000  # Training data size
NUM_REALTIME_SAMPLES = 50     # Number of simulated real-time transactions