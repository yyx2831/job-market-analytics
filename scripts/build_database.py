from argparse import ArgumentParser
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.database import connect, import_csv, init_db
from src.sample_data import generate_sample_csv


def main() -> None:
    parser = ArgumentParser()
    parser.add_argument("--csv", default=str(ROOT / "data" / "raw" / "chengdu_jobs_sample.csv"))
    parser.add_argument("--db", default=str(ROOT / "data" / "processed" / "jobs.db"))
    args = parser.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        generate_sample_csv(csv_path)

    conn = connect(Path(args.db))
    init_db(conn)
    inserted = import_csv(conn, csv_path)
    conn.close()
    print(f"Imported {inserted} new jobs into {args.db}")


if __name__ == "__main__":
    main()

