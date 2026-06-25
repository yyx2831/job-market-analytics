from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.sample_data import generate_sample_csv


if __name__ == "__main__":
    output = ROOT / "data" / "raw" / "chengdu_jobs_sample.csv"
    generate_sample_csv(output)
    print(f"Generated sample data: {output}")

