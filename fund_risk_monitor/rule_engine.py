# -*- coding: utf-8 -*-
"""
Rule Matching Engine
Checks each transaction against layered risk rules
"""

import json
import os
from config import RISK_RULES_FILE

_rules_cache = None


def load_rules():
    global _rules_cache
    if _rules_cache is None:
        if os.path.exists(RISK_RULES_FILE):
            with open(RISK_RULES_FILE, "r", encoding="utf-8") as f:
                _rules_cache = json.load(f)
        else:
            _rules_cache = []
    return _rules_cache


def _check_condition(tx, condition_str):
    """Check if additional condition is satisfied"""
    if not condition_str:
        return True
    try:
        return eval(condition_str, {"__builtins__": {}}, tx)
    except Exception:
        return False


def _check_sub_rule(tx, rule):
    """Check if a single sub-rule is triggered"""
    field = rule.get("field")
    operator = rule.get("operator")
    value = rule.get("value")
    condition = rule.get("condition")

    if field not in tx:
        return False

    tx_value = tx[field]

    compare_value = value
    if isinstance(value, str) and value in tx:
        compare_value = tx[value]

    try:
        if operator == "==":
            matched = tx_value == compare_value
        elif operator == "!=":
            matched = tx_value != compare_value
        elif operator == ">=":
            matched = float(tx_value) >= float(compare_value)
        elif operator == "<=":
            matched = float(tx_value) <= float(compare_value)
        elif operator == ">":
            matched = float(tx_value) > float(compare_value)
        elif operator == "<":
            matched = float(tx_value) < float(compare_value)
        else:
            matched = False
    except (ValueError, TypeError):
        return False

    if not matched:
        return False

    if condition and not _check_condition(tx, condition):
        return False

    return True


def match_rules(tx: dict) -> dict:
    """
    Match all rules against a transaction.
    Returns: {
        "hit_categories": [{"category_id", "category_name", "hit_rules": [...]}],
        "hit_count": total sub-rules hit,
        "hit_category_count": categories hit,
        "hit_summary": "C01-001,C02-003,..." short summary
    }
    """
    rules = load_rules()
    hit_categories = []
    all_hit_ids = []

    for category in rules:
        hit_sub_rules = []
        for sub_rule in category.get("sub_rules", []):
            if _check_sub_rule(tx, sub_rule):
                hit_sub_rules.append({
                    "rule_id": sub_rule["rule_id"],
                    "name": sub_rule["name"],
                    "description": sub_rule["description"],
                    "veto": sub_rule.get("veto", False),
                })
                all_hit_ids.append(sub_rule["rule_id"])

        if hit_sub_rules:
            hit_categories.append({
                "category_id": category["category_id"],
                "category_name": category["category_name"],
                "risk_weight": category["risk_weight"],
                "hit_rules": hit_sub_rules,
            })

    return {
        "hit_categories": hit_categories,
        "hit_count": len(all_hit_ids),
        "hit_category_count": len(hit_categories),
        "hit_summary": ",".join(all_hit_ids) if all_hit_ids else "",
    }
