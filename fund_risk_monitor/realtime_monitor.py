# -*- coding: utf-8 -*-
"""
Real-time Risk Monitoring Service
Monitors the incoming directory; auto-infers risk when new JSON files arrive.
"""

import json
import os
import sys
import time
from datetime import datetime

import joblib
import pandas as pd
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from config import (
    INCOMING_DIR, MODEL_FILE, FEATURE_COLUMNS_FILE,
    ALERT_DIR, RISK_THRESHOLD, DATA_DIR
)
from train_model import prepare_features


class RiskModel:
    """Risk model wrapper"""

    def __init__(self):
        print("Loading risk model...")
        if not os.path.exists(MODEL_FILE):
            raise FileNotFoundError(f"Model file not found: {MODEL_FILE}\nPlease run train_model.py first")
        self.model = joblib.load(MODEL_FILE)
        self.feature_columns = joblib.load(FEATURE_COLUMNS_FILE)
        print(f"Model loaded, feature count: {len(self.feature_columns)}")

    def predict(self, transaction: dict) -> dict:
        """Single transaction risk inference"""
        df = pd.DataFrame([transaction])
        X = prepare_features(df)

        for col in self.feature_columns:
            if col not in X.columns:
                X[col] = 0
        X = X[self.feature_columns]

        prob = self.model.predict_proba(X)[0][1]
        label = 1 if prob >= RISK_THRESHOLD else 0

        return {
            "risk_probability": round(float(prob), 4),
            "risk_label": label,
            "risk_level": self._get_risk_level(prob),
        }

    @staticmethod
    def _get_risk_level(prob):
        if prob >= 0.8:
            return "Critical"
        elif prob >= 0.6:
            return "High"
        elif prob >= 0.4:
            return "Medium"
        elif prob >= 0.2:
            return "Low"
        else:
            return "Normal"


class TransactionHandler(FileSystemEventHandler):
    """Monitors folder; infers risk when new JSON arrives"""

    def __init__(self, model: RiskModel):
        self.model = model
        self.processed_count = 0
        self.alert_count = 0
        os.makedirs(ALERT_DIR, exist_ok=True)

    def on_created(self, event):
        if event.is_directory or not event.src_path.endswith(".json"):
            return
        time.sleep(0.1)
        self._process_file(event.src_path)

    def _process_file(self, filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                tx = json.load(f)

            result = self.model.predict(tx)
            self.processed_count += 1

            tx_id = tx.get("transaction_id", "unknown")[:8]
            customer = tx.get("customer_id", "unknown")
            amount = tx.get("amount", 0)
            fund = tx.get("fund_name", "unknown")
            region = tx.get("region_name", "unknown")

            if result["risk_label"] == 1:
                self.alert_count += 1
                print(f"\n{'!'*60}")
                print(f"[!] HIGH RISK ALERT #{self.alert_count}")
                print(f"  TX ID: {tx_id}...")
                print(f"  Customer: {customer} | Region: {region}")
                print(f"  Fund: {fund}")
                print(f"  Amount: {amount:,.2f}")
                print(f"  Risk Probability: {result['risk_probability']:.2%}")
                print(f"  Risk Level: {result['risk_level']}")
                print(f"{'!'*60}")

                alert = {**tx, **result, "alert_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
                alert_file = os.path.join(ALERT_DIR, f"alert_{tx_id}.json")
                with open(alert_file, "w", encoding="utf-8") as f:
                    json.dump(alert, f, ensure_ascii=False, indent=2)
            else:
                print(f"  [OK] {tx_id}... | {customer} | {amount:,.2f} | {fund} | Risk: {result['risk_probability']:.2%}")

        except Exception as e:
            print(f"  [ERROR] Failed to process {filepath}: {e}")


def scan_existing_files(handler):
    """Scan existing JSON files"""
    if not os.path.exists(INCOMING_DIR):
        return
    files = sorted([f for f in os.listdir(INCOMING_DIR) if f.endswith(".json")])
    if files:
        print(f"\nFound {len(files)} pending transaction files, starting batch inference...\n")
        for filename in files:
            filepath = os.path.join(INCOMING_DIR, filename)
            handler._process_file(filepath)
        print(f"\nBatch complete: {handler.processed_count} processed, {handler.alert_count} alerts")


def main():
    """Start real-time monitoring"""
    print("=" * 60)
    print("Fund Transaction Real-time Risk Monitoring System")
    print(f"Risk Threshold: {RISK_THRESHOLD}")
    print(f"Incoming Directory: {INCOMING_DIR}")
    print("=" * 60)

    model = RiskModel()
    handler = TransactionHandler(model)

    scan_existing_files(handler)

    os.makedirs(INCOMING_DIR, exist_ok=True)
    observer = Observer()
    observer.schedule(handler, INCOMING_DIR, recursive=False)
    observer.start()

    print(f"\nReal-time monitoring active, waiting for new transaction files...")
    print("(Drop new JSON files into the incoming directory to trigger inference)")
    print("Press Ctrl+C to stop\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        print(f"\nMonitoring stopped. Processed {handler.processed_count} transactions, {handler.alert_count} alerts")

    observer.join()


if __name__ == "__main__":
    main()