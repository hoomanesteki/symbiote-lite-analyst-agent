from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple

DATASET_YEAR = 2022
MIN_DATE = datetime(2022, 1, 1)
MAX_DATE = datetime(2023, 1, 1)

ISO_DATE_RE = re.compile(r"\b(\d{4})[-/](\d{2})[-/](\d{2})\b")
Q_RE = re.compile(r"\bq([1-4])\b", re.IGNORECASE)

SEASON_MAP = {
    "spring": (3, 6), "summer": (6, 9), "fall": (9, 12),
    "autumn": (9, 12), "winter": (1, 3),
}

MONTH_MAP = {
    "jan": 1, "january": 1, "janurary": 1, "janury": 1, "januarry": 1, "janaury": 1,
    "feb": 2, "february": 2, "febuary": 2, "feburary": 2, "februrary": 2, "febrary": 2,
    "mar": 3, "march": 3, "mach": 3, "mrch": 3,
    "apr": 4, "april": 4, "apirl": 4, "apil": 4,
    "may": 5,
    "jun": 6, "june": 6, "juen": 6,
    "jul": 7, "july": 7, "jully": 7,
    "aug": 8, "august": 8, "agust": 8, "augst": 8,
    "sep": 9, "sept": 9, "september": 9, "septmber": 9, "setember": 9,
    "oct": 10, "october": 10, "octobor": 10, "ocotber": 10,
    "nov": 11, "november": 11, "novemeber": 11, "novmber": 11,
    "dec": 12, "december": 12, "decmber": 12, "dicember": 12,
}

def _parse_date(s: str) -> datetime:
    s = s.strip().replace("/", "-")
    return datetime.strptime(s, "%Y-%m-%d")

def validate_date(date_str: str) -> None:
    try:
        dt = _parse_date(date_str)
    except Exception:
        raise ValueError("Invalid date format. Use YYYY-MM-DD (example: 2022-06-01).")
    if not (MIN_DATE <= dt < MAX_DATE):
        raise ValueError(f"Date must be in {DATASET_YEAR}.")

def validate_range(start: str, end: str) -> None:
    s, e = _parse_date(start), _parse_date(end)
    if not (MIN_DATE <= s < MAX_DATE) or not (MIN_DATE <= e <= MAX_DATE):
        raise ValueError(f"Dates must be in {DATASET_YEAR}.")
    if e <= s:
        raise ValueError("end_date must be AFTER start_date (end_date is exclusive).")

def _get_month_num(word: str) -> int:
    w = word.lower().strip()
    if w in MONTH_MAP:
        return MONTH_MAP[w]
    if len(w) >= 3:
        prefix = w[:3]
        if prefix in MONTH_MAP:
            return MONTH_MAP[prefix]
    for key, val in MONTH_MAP.items():
        if len(key) >= 3 and len(w) >= 3 and key[:3] == w[:3]:
            return val
    return 0

def find_months_in_text(text: str) -> List[int]:
    found = []
    words = re.findall(r"\b[a-zA-Z]{3,12}\b", text.lower())
    for word in words:
        month_num = _get_month_num(word)
        if month_num > 0 and month_num not in found:
            found.append(month_num)
    return found

def extract_dates(text: str) -> Tuple[List[datetime], List[str]]:
    """Return (dates, invalid_dates)."""
    dates, invalid_dates = [], []
    found_iso = False

    for y, m, d in ISO_DATE_RE.findall(text):
        found_iso = True
        try:
            dt = datetime(int(y), int(m), int(d))
            if dt.year == DATASET_YEAR:
                dates.append(dt)
            elif int(y) == 2023 and int(m) == 1 and int(d) == 1:
                dates.append(dt)  # allow exclusive end
        except ValueError:
            invalid_dates.append(f"{y}-{m}-{d}")

    if found_iso and (dates or invalid_dates):
        return (sorted(dates), invalid_dates)

    t = text.lower()

    whole_year = ["whole year", "all of 2022", "entire year", "full year",
                  "all year", "the year", "year 2022"]
    if any(p in t for p in whole_year):
        return ([datetime(2022, 1, 1), datetime(2023, 1, 1)], [])

    if "year" in t and any(w in t for w in ["monthly", "month", "breakdown", "trends", "by"]):
        if "2022" in t or not re.search(r"\b20\d{2}\b", t):
            return ([datetime(2022, 1, 1), datetime(2023, 1, 1)], [])

    qm = Q_RE.search(t)
    if qm and ("2022" in t or not re.search(r"\b20\d{2}\b", t)):
        q = int(qm.group(1))
        start_month = (q - 1) * 3 + 1
        end_month = start_month + 3
        start = datetime(2022, start_month, 1)
        end = datetime(2022, end_month, 1) if end_month <= 12 else datetime(2023, 1, 1)
        return ([start, end], [])

    for season, (m1, m2) in SEASON_MAP.items():
        if season in t:
            if re.search(r"\b20(?:1\d|2[013-9])\b", t):
                return ([], [])
            return ([datetime(2022, m1, 1), datetime(2022, m2, 1)], [])

    found_months = find_months_in_text(t)
    if found_months and ("2022" in t or not re.search(r"\b20\d{2}\b", t)):
        if len(found_months) == 1:
            m = found_months[0]
            start = datetime(2022, m, 1)
            end = datetime(2022, m + 1, 1) if m < 12 else datetime(2023, 1, 1)
            return ([start, end], [])
        if len(found_months) >= 2:
            start = datetime(2022, min(found_months), 1)
            end_m = max(found_months)
            end = datetime(2022, end_m + 1, 1) if end_m < 12 else datetime(2023, 1, 1)
            return ([start, end], [])

    return ([], [])

def recommend_granularity(start: datetime, end: datetime) -> str:
    days = (end - start).days
    if days <= 14:
        return "daily"
    if days <= 90:
        return "weekly"
    return "monthly"
