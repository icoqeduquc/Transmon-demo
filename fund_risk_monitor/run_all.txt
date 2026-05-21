# -*- coding: utf-8 -*-
"""
One-click run: Generate data -> Train model -> Start monitoring
"""

from data_generator import generate_risk_rules_file, generate_training_data, generate_realtime_transactions
from train_model import train
from realtime_monitor import main as start_monitor


if __name__ == "__main__":
    print("=" * 60)
    print("Step 1: Generate simulated data")
    print("=" * 60)
    generate_risk_rules_file()
    generate_training_data()

    print("\n" + "=" * 60)
    print("Step 2: Train XGBoost risk model")
    print("=" * 60)
    train()

    print("\n" + "=" * 60)
    print("Step 3: Generate simulated real-time transactions")
    print("=" * 60)
    generate_realtime_transactions()

    print("\n" + "=" * 60)
    print("Step 4: Start real-time monitoring")
    print("=" * 60)
    start_monitor()
