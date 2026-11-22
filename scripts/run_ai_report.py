"""CLI runner untuk Deliverable 5: AI Financial Insights (CSV -> JSON)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.ai_report_service import generate_ai_report_from_file  # noqa: E402


def main() -> None:
    csv_path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "payment_data.csv"
    report = generate_ai_report_from_file(csv_path, use_external_llm=False)
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
