import json
import os

STANDARDS_PATH = "standards/standards.json"


def load_standards() -> list:
    if not os.path.exists(STANDARDS_PATH):
        return []
    with open(STANDARDS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_standards(standards: list):
    os.makedirs(os.path.dirname(STANDARDS_PATH), exist_ok=True)
    with open(STANDARDS_PATH, "w", encoding="utf-8") as f:
        json.dump(standards, f, ensure_ascii=False, indent=2)
