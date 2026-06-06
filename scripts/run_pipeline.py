"""采集框架 MVP 全链路：mock raw JSONL → compatible CSV → SQLite → Streamlit。

用法:
  python scripts/run_pipeline.py              # 默认: 生成 500 条 JSONL，写入 CSV/SQLite，启动 Streamlit
  python scripts/run_pipeline.py --rows 200   # 自定义数据量
  python scripts/run_pipeline.py --skip-streamlit  # 只跑数据处理，不启动前端
  python scripts/run_pipeline.py --reset      # 清空数据库重新导入
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.database import connect, import_csv, init_db
from scripts.generate_mock_jsonl import generate_mock_jsonl
from scripts.jsonl_to_csv import jsonl_to_csv


JSONL_PATH = ROOT / "data" / "raw" / "mock_jobs.jsonl"
CSV_PATH = ROOT / "data" / "raw" / "mock_jobs.csv"
DB_PATH = ROOT / "data" / "processed" / "jobs.db"

SEP = "=" * 50


def step1_generate_jsonl(rows: int) -> None:
    print(f"\n{SEP}")
    print(f"Step 1: 生成 mock raw JSONL ({rows} 条)")
    print(SEP)
    generate_mock_jsonl(JSONL_PATH, rows=rows)
    print(f"  OK  {JSONL_PATH}")


def step2_jsonl_to_csv() -> None:
    print(f"\n{SEP}")
    print("Step 2: JSONL -> compatible CSV")
    print(SEP)
    count = jsonl_to_csv(JSONL_PATH, CSV_PATH)
    print(f"  OK  转换 {count} 条 -> {CSV_PATH}")


def step3_csv_to_sqlite(reset: bool) -> None:
    print(f"\n{SEP}")
    print("Step 3: CSV -> SQLite")
    print(SEP)
    conn = connect(DB_PATH)
    init_db(conn)

    if reset:
        conn.execute("DELETE FROM job_skills")
        conn.execute("DELETE FROM jobs")
        conn.commit()
        print("  OK  已清空数据库")

    inserted = import_csv(conn, CSV_PATH)
    conn.close()
    print(f"  OK  导入 {inserted} 条新记录 -> {DB_PATH}")


def step4_streamlit() -> None:
    print(f"\n{SEP}")
    print("Step 4: 启动 Streamlit 仪表盘")
    print(SEP)
    print("  访问 http://localhost:8501")
    print()
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(ROOT / "app.py")])


def main() -> None:
    parser = argparse.ArgumentParser(description="采集框架 MVP 全链路")
    parser.add_argument("--rows", type=int, default=500, help="生成 mock 数据量 (默认 500)")
    parser.add_argument("--skip-streamlit", action="store_true", help="跳过 Streamlit 启动")
    parser.add_argument("--reset", action="store_true", help="清空数据库后重新导入")
    args = parser.parse_args()

    print("\n" + SEP)
    print("采集框架 MVP 全链路")
    print("mock raw JSONL -> compatible CSV -> SQLite -> Streamlit")
    print(SEP)

    step1_generate_jsonl(args.rows)
    step2_jsonl_to_csv()
    step3_csv_to_sqlite(args.reset)

    if args.skip_streamlit:
        print("\n数据处理完成。运行 `streamlit run app.py` 启动仪表盘。")
        return

    step4_streamlit()


if __name__ == "__main__":
    main()
