# -*- coding: utf-8 -*-
"""
Simulated Fund Transaction Data Generator
Generates transaction JSON with dozens of fields, simulating transactions
across different regions, fund companies, and customers.
"""

import json
import os
import random
import uuid
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from config import (
    DATA_DIR, INCOMING_DIR, TRAINING_DATA_FILE,
    RISK_RULES_FILE, NUM_TRAINING_SAMPLES, NUM_REALTIME_SAMPLES
)

# ============ Base Data Dictionaries ============

# Regions (with high-risk region flags)
REGIONS = [
    {"code": "110000", "name": "Beijing", "high_risk": False},
    {"code": "310000", "name": "Shanghai", "high_risk": False},
    {"code": "440000", "name": "Guangdong", "high_risk": False},
    {"code": "330000", "name": "Zhejiang", "high_risk": False},
    {"code": "320000", "name": "Jiangsu", "high_risk": False},
    {"code": "510000", "name": "Sichuan", "high_risk": False},
    {"code": "500000", "name": "Chongqing", "high_risk": False},
    {"code": "350000", "name": "Fujian", "high_risk": False},
    {"code": "999001", "name": "Offshore-Cayman", "high_risk": True},
    {"code": "999002", "name": "Offshore-BVI", "high_risk": True},
    {"code": "999003", "name": "Offshore-Bermuda", "high_risk": True},
]

# Fund companies
FUND_COMPANIES = [
    {"id": "FC001", "name": "ChinaAMC", "rating": "AAA"},
    {"id": "FC002", "name": "E Fund", "rating": "AAA"},
    {"id": "FC003", "name": "Southern Fund", "rating": "AA"},
    {"id": "FC004", "name": "Harvest Fund", "rating": "AA"},
    {"id": "FC005", "name": "Bosera Fund", "rating": "A"},
    {"id": "FC006", "name": "GF Fund", "rating": "A"},
    {"id": "FC007", "name": "Tianhong Fund", "rating": "AA"},
    {"id": "FC008", "name": "BOC Fund", "rating": "AAA"},
]

# Fund products
FUND_PRODUCTS = [
    {"code": "000001", "name": "ChinaAMC Growth Mix", "type": "Mixed", "company": "FC001", "risk_level": 3},
    {"code": "000002", "name": "ChinaAMC Return Mix", "type": "Mixed", "company": "FC001", "risk_level": 3},
    {"code": "110011", "name": "E Fund Small Cap", "type": "Equity", "company": "FC002", "risk_level": 4},
    {"code": "110022", "name": "E Fund Consumer", "type": "Equity", "company": "FC002", "risk_level": 4},
    {"code": "202001", "name": "Southern Steady Growth", "type": "Mixed", "company": "FC003", "risk_level": 3},
    {"code": "070010", "name": "Harvest Theme Mix", "type": "Mixed", "company": "FC004", "risk_level": 3},
    {"code": "050002", "name": "Bosera CSI 300", "type": "Index", "company": "FC005", "risk_level": 3},
    {"code": "270002", "name": "GF Steady Growth", "type": "Mixed", "company": "FC006", "risk_level": 2},
    {"code": "000198", "name": "Tianhong Bond", "type": "Bond", "company": "FC007", "risk_level": 1},
    {"code": "163801", "name": "BOC Income Mix", "type": "Mixed", "company": "FC008", "risk_level": 2},
    {"code": "519732", "name": "BoCom New Growth Mix", "type": "Mixed", "company": "FC005", "risk_level": 3},
    {"code": "161725", "name": "CMB CSI Baijiu", "type": "Index", "company": "FC006", "risk_level": 4},
]

TRANSACTION_TYPES = ["Purchase", "Redemption", "Switch", "Auto-invest", "Dividend Reinvest", "Large Purchase"]
PAYMENT_METHODS = ["Bank Transfer", "Check", "Wire Transfer", "Third-party Payment", "Cash", "Bank Draft"]
CHANNELS = ["Counter", "Online", "Mobile App", "Third-party Platform", "Institutional Direct", "Phone Order"]
ID_TYPES = ["ID Card", "Passport", "Military ID", "HK/Macau Pass", "TW Pass", "Business License"]
INVESTOR_TYPES = ["Individual", "Institution", "Product Account", "QFII", "RQFII"]
CURRENCIES = ["CNY", "USD", "HKD", "EUR"]


def generate_customer_id():
    """Generate customer ID"""
    return f"CUST{random.randint(100000, 999999)}"


def generate_transaction(trade_date=None, force_risky=False):
    """
    Generate a simulated transaction with dozens of fields.
    force_risky: whether to force generate a high-risk transaction (for training data balance)
    """
    if trade_date is None:
        trade_date = datetime.now() - timedelta(days=random.randint(0, 365))

    fund = random.choice(FUND_PRODUCTS)
    company = next(c for c in FUND_COMPANIES if c["id"] == fund["company"])
    tx_type = random.choice(TRANSACTION_TYPES)

    # Determine transaction style: normal / suspicious (gray area) / high risk
    if force_risky:
        style = random.choices(["suspicious", "high_risk"], weights=[0.4, 0.6])[0]
    else:
        style = random.choices(["normal", "suspicious"], weights=[0.92, 0.08])[0]

    if style == "high_risk":
        # === Clearly high risk ===
        region = random.choice([r for r in REGIONS if r["high_risk"]] + REGIONS[:2])
        amount = round(random.uniform(1000000, 10000000), 2)
        payment = random.choice(["Check", "Cash", "Bank Draft"])
        channel = random.choice(["Counter", "Phone Order", "Institutional Direct"])
        trade_hour = random.choice([8, 16, 17, 22, 23])
        account_age_days = random.randint(1, 30)
        recent_tx_count_7d = random.randint(15, 50)
        recent_tx_count_30d = random.randint(30, 100)
        recent_tx_amount_7d = round(random.uniform(3000000, 20000000), 2)
        recent_tx_amount_30d = round(random.uniform(8000000, 50000000), 2)
        same_day_tx_count = random.randint(8, 30)
        same_fund_tx_count = random.randint(3, 10)
        ip_change_count_7d = random.randint(5, 20)
        device_change_count_7d = random.randint(3, 8)
        login_fail_count_24h = random.randint(3, 10)
        aml_flag = random.choice([0, 1, 1])
        blacklist_hit = random.choice([False, True])
        watchlist_hit = random.choice([False, True])
        is_related_party = random.choice([False, True])
        kyc_score = random.randint(10, 40)
    elif style == "suspicious":
        # === Gray area: some features abnormal, some normal -> medium risk ===
        region = random.choice(REGIONS)
        amount = round(random.uniform(300000, 2000000), 2)
        payment = random.choice(["Bank Transfer", "Wire Transfer", "Check", "Cash", "Third-party Payment"])
        channel = random.choice(["Online", "Mobile App", "Counter", "Phone Order"])
        trade_hour = random.choice([9, 10, 11, 14, 15, 16])
        account_age_days = random.randint(30, 365)
        recent_tx_count_7d = random.randint(5, 15)
        recent_tx_count_30d = random.randint(10, 40)
        recent_tx_amount_7d = round(random.uniform(500000, 5000000), 2)
        recent_tx_amount_30d = round(random.uniform(1000000, 10000000), 2)
        same_day_tx_count = random.randint(2, 8)
        same_fund_tx_count = random.randint(1, 4)
        ip_change_count_7d = random.randint(2, 6)
        device_change_count_7d = random.randint(1, 3)
        login_fail_count_24h = random.randint(1, 4)
        aml_flag = random.choice([0, 0, 1])
        blacklist_hit = False
        watchlist_hit = random.choice([False, False, True])
        is_related_party = random.choice([False, False, True])
        kyc_score = random.randint(35, 70)
    else:
        # === Normal transaction ===
        region = random.choice([r for r in REGIONS if not r["high_risk"]])
        amount = round(random.uniform(1000, 500000), 2)
        payment = random.choice(["Bank Transfer", "Bank Transfer", "Bank Transfer", "Wire Transfer", "Third-party Payment"])
        channel = random.choice(["Online", "Mobile App", "Mobile App", "Third-party Platform"])
        trade_hour = random.randint(9, 15)
        account_age_days = random.randint(180, 3650)
        recent_tx_count_7d = random.randint(0, 5)
        recent_tx_count_30d = random.randint(0, 15)
        recent_tx_amount_7d = round(random.uniform(0, 500000), 2)
        recent_tx_amount_30d = round(random.uniform(0, 2000000), 2)
        same_day_tx_count = random.randint(1, 3)
        same_fund_tx_count = random.randint(0, 1)
        ip_change_count_7d = random.randint(0, 2)
        device_change_count_7d = random.randint(0, 1)
        login_fail_count_24h = random.randint(0, 1)
        aml_flag = 0
        blacklist_hit = False
        watchlist_hit = False
        is_related_party = False
        kyc_score = random.randint(60, 100)

    # Customer info
    customer_id = generate_customer_id()
    investor_type = random.choice(INVESTOR_TYPES)
    age = random.randint(22, 65)

    trade_time = trade_date.replace(hour=trade_hour, minute=random.randint(0, 59),
                                     second=random.randint(0, 59))

    # Shares and NAV
    nav = round(random.uniform(0.5, 5.0), 4)
    shares = round(amount / nav, 2) if nav > 0 else 0
    fee_rate = round(random.uniform(0, 0.015), 4)
    fee_amount = round(amount * fee_rate, 2)

    # Holdings info
    holding_fund_count = random.randint(1, 15)
    total_holding_amount = round(random.uniform(amount * 2, amount * 20), 2)
    holding_ratio = round(amount / max(total_holding_amount, 1), 4)

    transaction = {
        # === Basic Transaction Info ===
        "transaction_id": str(uuid.uuid4()),
        "trade_date": trade_date.strftime("%Y-%m-%d"),
        "trade_time": trade_time.strftime("%Y-%m-%d %H:%M:%S"),
        "trade_timestamp": int(trade_time.timestamp()),
        "settlement_date": (trade_date + timedelta(days=random.choice([1, 2, 3]))).strftime("%Y-%m-%d"),
        "transaction_type": tx_type,
        "transaction_status": random.choice(["Confirmed", "Pending", "Processing"]),

        # === Amount & Shares ===
        "amount": amount,
        "currency": random.choice(CURRENCIES),
        "nav": nav,
        "shares": shares,
        "fee_rate": fee_rate,
        "fee_amount": fee_amount,
        "net_amount": round(amount - fee_amount, 2),

        # === Fund Product Info ===
        "fund_code": fund["code"],
        "fund_name": fund["name"],
        "fund_type": fund["type"],
        "fund_risk_level": fund["risk_level"],
        "fund_company_id": company["id"],
        "fund_company_name": company["name"],
        "fund_company_rating": company["rating"],

        # === Customer Info ===
        "customer_id": customer_id,
        "investor_type": investor_type,
        "customer_age": age,
        "id_type": random.choice(ID_TYPES),
        "customer_risk_tolerance": random.randint(1, 5),
        "is_qualified_investor": random.choice([True, False]),
        "kyc_score": kyc_score,
        "aml_flag": aml_flag,

        # === Region Info ===
        "region_code": region["code"],
        "region_name": region["name"],
        "is_high_risk_region": region["high_risk"],

        # === Channel & Payment ===
        "channel": channel,
        "payment_method": payment,
        "bank_code": f"BANK{random.randint(1, 20):03d}",

        # === Account Behavior Features ===
        "account_age_days": account_age_days,
        "recent_tx_count_7d": recent_tx_count_7d,
        "recent_tx_count_30d": recent_tx_count_30d,
        "recent_tx_amount_7d": recent_tx_amount_7d,
        "recent_tx_amount_30d": recent_tx_amount_30d,
        "same_day_tx_count": same_day_tx_count,
        "same_fund_tx_count": same_fund_tx_count,

        # === Holdings Info ===
        "holding_fund_count": holding_fund_count,
        "total_holding_amount": total_holding_amount,
        "holding_ratio": holding_ratio,

        # === Device & Network ===
        "ip_change_count_7d": ip_change_count_7d,
        "device_change_count_7d": device_change_count_7d,
        "is_new_device": random.choice([False, False, False, True]) if force_risky else False,
        "login_fail_count_24h": login_fail_count_24h,

        # === Compliance Flags ===
        "is_large_transaction": amount >= 1000000,
        "is_cross_border": region["high_risk"],
        "is_related_party": is_related_party,
        "blacklist_hit": blacklist_hit,
        "watchlist_hit": watchlist_hit,

        # === Trade Time Features ===
        "trade_hour": trade_hour,
        "is_trading_hours": 9 <= trade_hour <= 15,
        "is_month_end": trade_date.day >= 28,
        "is_quarter_end": trade_date.month in [3, 6, 9, 12] and trade_date.day >= 28,
    }

    return transaction


def label_transaction(tx):
    """
    Label transactions based on multi-dimensional features.
    Simulates real-world risk determination logic.
    Returns: 0=Normal, 1=High Risk
    """
    risk_score = 0

    # Large transaction
    if tx["amount"] >= 2000000:
        risk_score += 2
    elif tx["amount"] >= 1000000:
        risk_score += 1

    # High-risk region
    if tx["is_high_risk_region"]:
        risk_score += 3

    # Abnormal payment method
    if tx["payment_method"] in ["Check", "Cash", "Bank Draft"]:
        risk_score += 2

    # New account large transaction
    if tx["account_age_days"] < 30 and tx["amount"] >= 500000:
        risk_score += 3

    # Frequent transactions
    if tx["recent_tx_count_7d"] >= 15:
        risk_score += 2

    # Non-trading hours
    if not tx["is_trading_hours"]:
        risk_score += 1

    # Device/IP anomalies
    if tx["ip_change_count_7d"] >= 5:
        risk_score += 2
    if tx["device_change_count_7d"] >= 3:
        risk_score += 1

    # AML flag
    if tx["aml_flag"] == 1:
        risk_score += 3

    # Blacklist / watchlist
    if tx["blacklist_hit"]:
        risk_score += 5
    if tx["watchlist_hit"]:
        risk_score += 2

    # Related party transaction
    if tx["is_related_party"]:
        risk_score += 1

    # Same-day repeated transactions on same fund
    if tx["same_fund_tx_count"] >= 3:
        risk_score += 1

    # Excessive holding concentration
    if tx["holding_ratio"] > 0.5:
        risk_score += 1

    # Customer risk tolerance vs fund risk mismatch
    if tx["customer_risk_tolerance"] < tx["fund_risk_level"]:
        risk_score += 1

    # Multiple login failures
    if tx["login_fail_count_24h"] >= 3:
        risk_score += 2

    # Add random noise to simulate real scenarios
    risk_score += random.uniform(-1, 1)

    return 1 if risk_score >= 5 else 0


def generate_risk_rules():
    """Generate layered risk control rules: categories -> sub-rules"""
    rules = [
        {
            "category_id": "C01",
            "category_name": "AML Rules",
            "category_description": "Anti-money laundering monitoring rules",
            "risk_weight": 5,
            "sub_rules": [
                {"rule_id": "C01-001", "name": "AML Flag Hit", "field": "aml_flag", "operator": "==", "value": 1, "description": "Customer triggered AML system flag"},
                {"rule_id": "C01-002", "name": "Large Cash Transaction", "field": "amount", "operator": ">=", "value": 500000, "condition": "payment_method in ['Cash']", "description": "Single cash transaction exceeds 500K"},
                {"rule_id": "C01-003", "name": "Split Transaction Suspect", "field": "same_day_tx_count", "operator": ">=", "value": 8, "condition": "amount < 500000", "description": "8+ same-day transactions under 500K each, suspected structuring"},
                {"rule_id": "C01-004", "name": "Cross-border Large Transfer", "field": "is_cross_border", "operator": "==", "value": True, "condition": "amount >= 200000", "description": "Cross-border transaction amount exceeds 200K"},
                {"rule_id": "C01-005", "name": "Short-term Dense Trading", "field": "recent_tx_count_7d", "operator": ">=", "value": 20, "description": "20+ transactions within 7 days"},
            ]
        },
        {
            "category_id": "C02",
            "category_name": "Customer Identity Rules",
            "category_description": "Customer KYC, qualified investor, blacklist and identity rules",
            "risk_weight": 4,
            "sub_rules": [
                {"rule_id": "C02-001", "name": "Blacklist Hit", "field": "blacklist_hit", "operator": "==", "value": True, "description": "Customer on blacklist"},
                {"rule_id": "C02-002", "name": "Watchlist Hit", "field": "watchlist_hit", "operator": "==", "value": True, "description": "Customer on watchlist"},
                {"rule_id": "C02-003", "name": "Low KYC Score", "field": "kyc_score", "operator": "<", "value": 40, "description": "Customer KYC score below 40"},
                {"rule_id": "C02-004", "name": "Unqualified Investor High-risk Product", "field": "is_qualified_investor", "operator": "==", "value": False, "condition": "fund_risk_level >= 4", "description": "Non-qualified investor purchasing risk level 4+ product"},
                {"rule_id": "C02-005", "name": "Risk Tolerance Mismatch", "field": "customer_risk_tolerance", "operator": "<", "value": "fund_risk_level", "description": "Customer risk tolerance below fund risk level"},
                {"rule_id": "C02-006", "name": "New Account Large Transaction", "field": "account_age_days", "operator": "<=", "value": 30, "condition": "amount >= 500000", "description": "Single transaction exceeds 500K within 30 days of account opening"},
            ]
        },
        {
            "category_id": "C03",
            "category_name": "Transaction Amount Rules",
            "category_description": "Monitoring rules for abnormal transaction amounts",
            "risk_weight": 3,
            "sub_rules": [
                {"rule_id": "C03-001", "name": "Ultra-large Transaction", "field": "amount", "operator": ">=", "value": 5000000, "description": "Single transaction exceeds 5M"},
                {"rule_id": "C03-002", "name": "Large Transaction", "field": "amount", "operator": ">=", "value": 1000000, "description": "Single transaction exceeds 1M"},
                {"rule_id": "C03-003", "name": "7-day Cumulative Amount Anomaly", "field": "recent_tx_amount_7d", "operator": ">=", "value": 5000000, "description": "7-day cumulative transaction amount exceeds 5M"},
                {"rule_id": "C03-004", "name": "30-day Cumulative Amount Anomaly", "field": "recent_tx_amount_30d", "operator": ">=", "value": 20000000, "description": "30-day cumulative transaction amount exceeds 20M"},
                {"rule_id": "C03-005", "name": "Excessive Holding Concentration", "field": "holding_ratio", "operator": ">", "value": 0.5, "description": "Single transaction exceeds 50% of total holdings"},
            ]
        },
        {
            "category_id": "C04",
            "category_name": "Transaction Behavior Rules",
            "category_description": "Monitoring for anomalies in frequency, timing, and channels",
            "risk_weight": 3,
            "sub_rules": [
                {"rule_id": "C04-001", "name": "Off-hours Trading", "field": "is_trading_hours", "operator": "==", "value": False, "description": "Transaction submitted outside normal trading hours (9:00-15:00)"},
                {"rule_id": "C04-002", "name": "7-day Frequency Anomaly", "field": "recent_tx_count_7d", "operator": ">=", "value": 15, "description": "15+ transactions within 7 days"},
                {"rule_id": "C04-003", "name": "Same-day Same-fund Repeat", "field": "same_fund_tx_count", "operator": ">=", "value": 3, "description": "3+ transactions on same fund in one day"},
                {"rule_id": "C04-004", "name": "Month-end Concentrated Trading", "field": "is_month_end", "operator": "==", "value": True, "condition": "same_day_tx_count >= 5", "description": "5+ transactions on month-end day, suspected volume pumping"},
                {"rule_id": "C04-005", "name": "Quarter-end Large Transaction", "field": "is_quarter_end", "operator": "==", "value": True, "condition": "amount >= 1000000", "description": "Large transaction at quarter-end, suspected AUM adjustment"},
            ]
        },
        {
            "category_id": "C05",
            "category_name": "Region & Cross-border Rules",
            "category_description": "Monitoring for high-risk regions and cross-border transactions",
            "risk_weight": 4,
            "sub_rules": [
                {"rule_id": "C05-001", "name": "High-risk Region Transaction", "field": "is_high_risk_region", "operator": "==", "value": True, "description": "Transaction from high-risk region (offshore centers, etc.)"},
                {"rule_id": "C05-002", "name": "Cross-border Transaction", "field": "is_cross_border", "operator": "==", "value": True, "description": "Involves cross-border fund flow"},
                {"rule_id": "C05-003", "name": "Non-CNY Transaction", "field": "currency", "operator": "!=", "value": "CNY", "description": "Transaction in non-CNY currency"},
            ]
        },
        {
            "category_id": "C06",
            "category_name": "Payment Method Rules",
            "category_description": "Monitoring for abnormal payment methods",
            "risk_weight": 3,
            "sub_rules": [
                {"rule_id": "C06-001", "name": "Check Payment", "field": "payment_method", "operator": "==", "value": "Check", "description": "Payment by check"},
                {"rule_id": "C06-002", "name": "Cash Payment", "field": "payment_method", "operator": "==", "value": "Cash", "description": "Payment by cash"},
                {"rule_id": "C06-003", "name": "Bank Draft Payment", "field": "payment_method", "operator": "==", "value": "Bank Draft", "description": "Payment by bank draft"},
                {"rule_id": "C06-004", "name": "Large Wire Transfer", "field": "payment_method", "operator": "==", "value": "Wire Transfer", "condition": "amount >= 1000000", "description": "Wire transfer amount exceeds 1M"},
            ]
        },
        {
            "category_id": "C07",
            "category_name": "Device & Network Security Rules",
            "category_description": "Monitoring for login device, IP address security anomalies",
            "risk_weight": 3,
            "sub_rules": [
                {"rule_id": "C07-001", "name": "Frequent IP Changes", "field": "ip_change_count_7d", "operator": ">=", "value": 5, "description": "5+ IP address changes within 7 days"},
                {"rule_id": "C07-002", "name": "Frequent Device Changes", "field": "device_change_count_7d", "operator": ">=", "value": 3, "description": "3+ device changes within 7 days"},
                {"rule_id": "C07-003", "name": "New Device Transaction", "field": "is_new_device", "operator": "==", "value": True, "condition": "amount >= 500000", "description": "Large transaction (500K+) from new device"},
                {"rule_id": "C07-004", "name": "Frequent Login Failures", "field": "login_fail_count_24h", "operator": ">=", "value": 3, "description": "3+ login failures within 24 hours"},
                {"rule_id": "C07-005", "name": "Login Failure then Large TX", "field": "login_fail_count_24h", "operator": ">=", "value": 2, "condition": "amount >= 500000", "description": "Large transaction after 2+ login failures"},
            ]
        },
        {
            "category_id": "C08",
            "category_name": "Related Party Rules",
            "category_description": "Monitoring for related party transactions and benefit transfer",
            "risk_weight": 3,
            "sub_rules": [
                {"rule_id": "C08-001", "name": "Related Party Transaction", "field": "is_related_party", "operator": "==", "value": True, "description": "Counterparty is a related party"},
                {"rule_id": "C08-002", "name": "Related Party Large TX", "field": "is_related_party", "operator": "==", "value": True, "condition": "amount >= 1000000", "description": "Related party transaction exceeds 1M"},
                {"rule_id": "C08-003", "name": "Related Party Frequent TX", "field": "is_related_party", "operator": "==", "value": True, "condition": "same_day_tx_count >= 3", "description": "3+ transactions with related party in one day"},
            ]
        },
        {
            "category_id": "C09", "category_name": "Global Statistical Anomaly Rules",
            "category_description": "Anomaly detection based on market/fund/region-level daily statistics", "risk_weight": 4,
            "sub_rules": [
                {"rule_id": "C09-001", "name": "High Customer Fund Share", "field": "ctx_customer_share_of_fund", "operator": ">=", "value": 0.3, "description": "Customer's daily TX amount exceeds 30% of fund's daily total"},
                {"rule_id": "C09-002", "name": "High Customer Market Share", "field": "ctx_customer_share_of_market", "operator": ">=", "value": 0.1, "description": "Customer's daily TX amount exceeds 10% of market daily total"},
                {"rule_id": "C09-003", "name": "Customer Daily TX Count Anomaly", "field": "ctx_customer_today_count", "operator": ">=", "value": 10, "description": "Customer has 10+ transactions today"},
                {"rule_id": "C09-004", "name": "Customer Daily Amount Anomaly", "field": "ctx_customer_today_amount", "operator": ">=", "value": 5000000, "description": "Customer's daily cumulative amount exceeds 5M"},
                {"rule_id": "C09-005", "name": "Customer Cross-fund Diversification", "field": "ctx_customer_today_fund_variety", "operator": ">=", "value": 5, "description": "Customer traded 5+ different funds today, suspected dispersion"},
                {"rule_id": "C09-006", "name": "Region Concentration Anomaly", "field": "ctx_region_share_of_market", "operator": ">=", "value": 0.5, "description": "Region's daily TX exceeds 50% of market total"},
            ]
        },
    ]
    return rules



def generate_training_data():
    """Generate training dataset"""
    print("Generating training data...")
    transactions = []

    from rule_engine import match_rules as _mr

    # 90% normal transactions
    normal_count = int(NUM_TRAINING_SAMPLES * 0.9)
    for _ in range(normal_count):
        tx = generate_transaction(force_risky=False)
        rr = _mr(tx)
        tx["rule_hit_count"] = rr["hit_count"]
        tx["rule_hit_category_count"] = rr["hit_category_count"]
        tx["rule_has_veto"] = int(any(r.get("veto") for cat in rr["hit_categories"] for r in cat["hit_rules"]))
        tx["risk_label"] = label_transaction(tx)
        transactions.append(tx)

    # 10% forced high-risk features
    risky_count = NUM_TRAINING_SAMPLES - normal_count
    for _ in range(risky_count):
        tx = generate_transaction(force_risky=True)
        rr = _mr(tx)
        tx["rule_hit_count"] = rr["hit_count"]
        tx["rule_hit_category_count"] = rr["hit_category_count"]
        tx["rule_has_veto"] = int(any(r.get("veto") for cat in rr["hit_categories"] for r in cat["hit_rules"]))
        tx["risk_label"] = label_transaction(tx)
        transactions.append(tx)

    random.shuffle(transactions)

    df = pd.DataFrame(transactions)
    os.makedirs(DATA_DIR, exist_ok=True)
    df.to_csv(TRAINING_DATA_FILE, index=False, encoding="utf-8-sig")

    label_counts = df["risk_label"].value_counts()
    print(f"Training data generated: {len(df)} records")
    print(f"  Normal transactions: {label_counts.get(0, 0)}")
    print(f"  High-risk transactions: {label_counts.get(1, 0)}")
    return df


def generate_realtime_transactions():
    """Generate simulated real-time transaction JSON files to incoming directory"""
    print(f"\nGenerating {NUM_REALTIME_SAMPLES} simulated real-time transactions...")
    os.makedirs(INCOMING_DIR, exist_ok=True)

    for i in range(NUM_REALTIME_SAMPLES):
        force_risky = random.random() < 0.3
        tx = generate_transaction(trade_date=datetime.now(), force_risky=force_risky)

        filename = f"tx_{tx['trade_timestamp']}_{i:04d}.json"
        filepath = os.path.join(INCOMING_DIR, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(tx, f, ensure_ascii=False, indent=2)

    print(f"Real-time transaction files generated at: {INCOMING_DIR}")


def generate_risk_rules_file():
    """Generate risk rules JSON file"""
    os.makedirs(DATA_DIR, exist_ok=True)
    rules = generate_risk_rules()
    with open(RISK_RULES_FILE, "w", encoding="utf-8") as f:
        json.dump(rules, f, ensure_ascii=False, indent=2)
    print(f"Risk rules file generated: {RISK_RULES_FILE}")


if __name__ == "__main__":
    generate_risk_rules_file()
    generate_training_data()
    generate_realtime_transactions()
    print("\nAll simulated data generation complete!")
