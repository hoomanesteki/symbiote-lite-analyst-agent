from __future__ import annotations

import re

SQL_INJECTION_PATTERNS = [
    r";\s*drop\s+", r";\s*delete\s+", r";\s*insert\s+", r";\s*update\s+",
    r";\s*alter\s+", r";\s*create\s+", r";\s*truncate\s+", r"--\s*$",
    r"'\s*;\s*", r"'\s*or\s+['\"1]", r"'\s*and\s+", r"union\s+select",
    r"exec\s*\(", r"execute\s*\(", r"xp_\w+", r"sp_\w+",
    r"0x[0-9a-f]+", r"char\s*\(", r"concat\s*\(",
]

def detect_sql_injection(user_input: str) -> bool:
    """Heuristic detection of common SQL injection patterns."""
    t = (user_input or "").lower()
    for pattern in SQL_INJECTION_PATTERNS:
        if re.search(pattern, t, re.IGNORECASE):
            return True
    return False

def safe_select_only(sql: str) -> str:
    """Ensure SQL is SELECT/WITH only (no mutations)."""
    low = (sql or "").lower().strip()
    if not (low.startswith("select") or low.startswith("with")):
        raise ValueError("Only SELECT queries are allowed.")
    dangerous = [
        "insert", "update", "delete", "drop", "alter", "create",
        "truncate", "grant", "revoke", "exec", "execute",
    ]
    for kw in dangerous:
        if re.search(rf"\\b{kw}\\b", low):
            raise ValueError("Unsafe SQL detected.")
    return sql
