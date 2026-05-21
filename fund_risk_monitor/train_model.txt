# -*- coding: utf-8 -*-
"""
XGBoost Risk Model Training
Read training data, train model, output evaluation report
"""

import os
import warnings

import joblib
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import classification_report, roc_auc_score, confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder

from config import TRAINING_DATA_FILE, MODEL_DIR, MODEL_FILE, FEATURE_COLUMNS_FILE, DATA_DIR

warnings.filterwarnings("ignore")

FEATURE_CONFIG_FILE = os.path.join(DATA_DIR, "feature_config.json")

# Default feature list (used when config file doesn't exist)
NUMERIC_FEATURES = [
    "amount", "nav", "shares", "fee_rate", "fee_amount", "net_amount",
    "fund_risk_level", "customer_age", "customer_risk_tolerance",
    "kyc_score", "aml_flag", "account_age_days",
    "recent_tx_count_7d", "recent_tx_count_30d",
    "recent_tx_amount_7d", "recent_tx_amount_30d",
    "same_day_tx_count", "same_fund_tx_count",
    "holding_fund_count", "total_holding_amount", "holding_ratio",
    "ip_change_count_7d", "device_change_count_7d",
    "login_fail_count_24h", "trade_hour",
    "rule_hit_count", "rule_hit_category_count",
]

BOOLEAN_FEATURES = [
    "is_high_risk_region", "is_qualified_investor", "is_new_device",
    "is_large_transaction", "is_cross_border", "is_related_party",
    "blacklist_hit", "watchlist_hit", "is_trading_hours",
    "is_month_end", "is_quarter_end", "rule_has_veto",
]

CATEGORICAL_FEATURES = [
    "transaction_type", "fund_type", "fund_company_rating",
    "investor_type", "channel", "payment_method", "currency", "id_type",
]


def load_feature_config():
    """Load enabled feature list from config file"""
    import json
    if not os.path.exists(FEATURE_CONFIG_FILE):
        return NUMERIC_FEATURES, BOOLEAN_FEATURES, CATEGORICAL_FEATURES, True
    with open(FEATURE_CONFIG_FILE, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    num = [f["name"] for f in cfg.get("numeric_features", []) if f.get("enabled", True)]
    boo = [f["name"] for f in cfg.get("boolean_features", []) if f.get("enabled", True)]
    cat = [f["name"] for f in cfg.get("categorical_features", []) if f.get("enabled", True)]
    derived_enabled = {f["name"]: f.get("enabled", True) for f in cfg.get("derived_features", [])}
    return num, boo, cat, derived_enabled


def prepare_features(df):
    """Feature engineering: convert raw data to model-ready feature matrix"""
    num_feats, bool_feats, cat_feats, derived = load_feature_config()
    feature_df = pd.DataFrame()

    # Numeric features
    for col in num_feats:
        if col in df.columns:
            feature_df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    # Boolean features to 0/1
    for col in bool_feats:
        if col in df.columns:
            feature_df[col] = df[col].astype(int)

    # Categorical features one-hot encoding
    for col in cat_feats:
        if col in df.columns:
            dummies = pd.get_dummies(df[col], prefix=col, dummy_na=False)
            feature_df = pd.concat([feature_df, dummies], axis=1)

    # Derived features (based on config)
    d = derived if isinstance(derived, dict) else {}
    if d.get("amount_per_tx_7d", True) and "amount" in feature_df.columns:
        feature_df["amount_per_tx_7d"] = feature_df["amount"] / (feature_df.get("recent_tx_count_7d", 1) + 1)
    if d.get("tx_frequency_ratio", True) and "recent_tx_count_7d" in feature_df.columns:
        feature_df["tx_frequency_ratio"] = feature_df["recent_tx_count_7d"] / (feature_df.get("recent_tx_count_30d", 1) + 1)
    if d.get("risk_mismatch", True) and "customer_risk_tolerance" in feature_df.columns and "fund_risk_level" in feature_df.columns:
        feature_df["risk_mismatch"] = (feature_df["customer_risk_tolerance"] < feature_df["fund_risk_level"]).astype(int)
    if d.get("new_account_large_tx", True) and "account_age_days" in feature_df.columns and "amount" in feature_df.columns:
        feature_df["new_account_large_tx"] = ((feature_df["account_age_days"] < 30) & (feature_df["amount"] >= 500000)).astype(int)

    return feature_df


def train():
    """Train XGBoost model"""
    print("=" * 60)
    print("Starting risk model training")
    print("=" * 60)

    if not os.path.exists(TRAINING_DATA_FILE):
        print(f"Training data file not found: {TRAINING_DATA_FILE}")
        print("Please run data_generator.py to generate data")
        return

    df = pd.read_csv(TRAINING_DATA_FILE)
    print(f"\nDataset size: {len(df)} records")
    print(f"Label distribution:\n{df['risk_label'].value_counts()}")

    X = prepare_features(df)
    y = df["risk_label"]

    print(f"\nFeature count: {X.shape[1]}")
    print(f"Feature list: {list(X.columns)}")

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    print(f"\nTraining set: {len(X_train)} records")
    print(f"Test set: {len(X_test)} records")

    model = xgb.XGBClassifier(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.1,
        subsample=0.8,
        colsample_bytree=0.8,
        scale_pos_weight=len(y_train[y_train == 0]) / max(len(y_train[y_train == 1]), 1),
        random_state=42,
        eval_metric="logloss",
    )

    model.fit(
        X_train, y_train,
        eval_set=[(X_test, y_test)],
        verbose=False,
    )

    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)[:, 1]

    print("\n" + "=" * 60)
    print("Model Evaluation Report")
    print("=" * 60)
    print(classification_report(y_test, y_pred, target_names=["Normal", "High Risk"]))
    print(f"AUC-ROC: {roc_auc_score(y_test, y_prob):.4f}")
    print(f"\nConfusion Matrix:\n{confusion_matrix(y_test, y_pred)}")

    importance = model.feature_importances_
    feature_importance = sorted(zip(X.columns, importance), key=lambda x: x[1], reverse=True)
    print("\nFeature Importance (Top 15):")
    for feat, imp in feature_importance[:15]:
        print(f"  {feat}: {imp:.4f}")

    os.makedirs(MODEL_DIR, exist_ok=True)
    joblib.dump(model, MODEL_FILE)
    joblib.dump(list(X.columns), FEATURE_COLUMNS_FILE)
    print(f"\nModel saved to {MODEL_FILE}")
    print(f"Feature columns saved to {FEATURE_COLUMNS_FILE}")

    return model


if __name__ == "__main__":
    train()