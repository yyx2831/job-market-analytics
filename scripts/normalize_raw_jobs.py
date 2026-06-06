"""离线归一化入口：将原始 JSONL 转为兼容 CSV，生成质量报告。

用法:
  python scripts/normalize_raw_jobs.py --input data/raw/job51/2026-06-04/job51.jsonl
  python scripts/normalize_raw_jobs.py --input data/raw/job51/2026-06-04/job51.jsonl --output data/processed/my.csv
  python scripts/normalize_raw_jobs.py --input data/raw/job51/2026-06-04/job51.jsonl --import-db
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.scraping.pipeline import load_raw_jobs, pipeline
from src.scraping.quality import generate_quality_report, print_report, save_report
from src.database import connect, import_csv, init_db


PROCESSED_DIR = ROOT / "data" / "processed"
REPORTS_DIR = PROCESSED_DIR / "reports"
DB_PATH = PROCESSED_DIR / "jobs.db"


def main() -> None:
    parser = argparse.ArgumentParser(description="离线归一化")
    parser.add_argument("--input", required=True, help="原始 JSONL 路径")
    parser.add_argument("--output", help="输出 CSV 路径（默认自动生成）")
    parser.add_argument("--import-db", action="store_true", help="同步导入 SQLite")
    parser.add_argument("--source", help="数据源名（默认从路径推断）")
    args = parser.parse_args()

    jsonl_path = Path(args.input)
    if not jsonl_path.exists():
        print(f"文件不存在: {jsonl_path}")
        sys.exit(1)

    source = args.source or jsonl_path.parent.name or "unknown"

    # 输出路径
    if args.output:
        csv_path = Path(args.output)
    else:
        date_str = jsonl_path.stem.split("_")[-1] if "_" in jsonl_path.stem else ""
        if not date_str:
            from datetime import datetime
            date_str = datetime.now().strftime("%Y-%m-%d")
        csv_path = PROCESSED_DIR / f"jobs_{source}_{date_str}.csv"

    # 管道
    count, normalized = pipeline(jsonl_path, csv_path)
    print(f"归一化完成: {count} 条 -> {csv_path}")

    # 质量报告
    raw_jobs = load_raw_jobs(jsonl_path)
    report = generate_quality_report(raw_jobs, normalized, source)
    print_report(report)
    report_path = save_report(report, REPORTS_DIR)
    print(f"质量报告: {report_path}")

    # 入库
    if args.import_db:
        conn = connect(DB_PATH)
        init_db(conn)
        inserted = import_csv(conn, csv_path)
        conn.close()
        print(f"入库: {inserted} 条新记录 -> {DB_PATH}")

    print("\n后续步骤:")
    print(f"  streamlit run app.py")
    print(f"  python scripts/build_database.py --csv {csv_path}")


if __name__ == "__main__":
    main()
