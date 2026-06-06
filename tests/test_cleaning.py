from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.cleaning import canonical_job_key, extract_skills, parse_salary


def test_parse_k_salary() -> None:
    parsed = parse_salary("10-15K")
    assert parsed["salary_min"] == 10000
    assert parsed["salary_max"] == 15000
    assert parsed["salary_avg"] == 12500
    assert parsed["salary_unit"] == "month"


def test_parse_months() -> None:
    parsed = parse_salary("15-25K·13薪")
    assert parsed["salary_min"] == 15000
    assert parsed["salary_max"] == 25000
    assert parsed["salary_months"] == 13


def test_parse_wan_salary() -> None:
    parsed = parse_salary("8千-1.2万")
    assert parsed["salary_min"] == 8000
    assert parsed["salary_max"] == 12000


def test_extract_skills() -> None:
    skills = extract_skills(["熟悉 Python、SQL、React 和数据分析"])
    assert "Python" in skills
    assert "SQL" in skills
    assert "React" in skills


def test_canonical_job_key_prefers_source_job_id() -> None:
    key = canonical_job_key(
        {
            "source": "51job",
            "source_job_id": "12345",
            "title": "Python 后端工程师",
            "company_name": "成都某科技有限公司",
            "district": "高新区",
        }
    )
    assert key == "51job|12345"


def test_canonical_job_key_falls_back_to_city_and_district() -> None:
    key = canonical_job_key(
        {
            "title": "Python 后端工程师",
            "company_name": "成都某科技有限公司",
            "city": "成都",
            "district": "高新区",
        }
    )
    assert key == "python 后端工程师|成都某科技有限公司|成都|高新区"
