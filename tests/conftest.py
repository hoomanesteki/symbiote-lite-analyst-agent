import sys
from pathlib import Path

# Ensure project root is on PYTHONPATH for tests
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
print(f"Project root added to PYTHONPATH: {PROJECT_ROOT}")