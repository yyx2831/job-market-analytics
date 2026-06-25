"""scraping 模块测试：pipeline、quality、models。"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.scraping.models import NormalizedJob, QualityReport, RawJob, ScrapeQuery
from src.scraping.pipeline import (
    load_raw_jobs,
    normalize_batch,
    normalize_job,
    parse_location,
    pipeline,
    write_csv,
)
from src.scraping.quality import generate_quality_report, save_report


# ── models ────────────────────────────────────────────

class TestScrapeQuery:
    def test_task_key_format(self) -> None:
        q = ScrapeQuery(
            source="51job",
            city="成都",
            keyword="Python",
            page=2,
            search_url="https://example.com/search",
        )
        assert q.task_key == "51job|成都|Python|2"

    def test_defaults(self) -> None:
        q = ScrapeQuery(source="test", city="test", keyword="test")
        assert q.page == 1
        assert q.search_url == ""


class TestRawJob:
    def test_default_platform_status(self) -> None:
        job = RawJob(source="51job")
        assert job.source_platform_status == "ok"

    def test_raw_skills_is_list(self) -> None:
        job = RawJob(source="51job", raw_skills=["Python", "Go"])
        assert isinstance(job.raw_skills, list)
        assert len(job.raw_skills) == 2


class TestNormalizedJob:
    def test_missing_fields_status(self) -> None:
        job = NormalizedJob(
            source_job_id="",
            title="未知岗位",
            company_name="未知公司",
            salary_text="",
            city="未知",
            district="未知",
            experience="未知",
            education="未知",
            industry="未知",
            company_size="未知",
            financing_stage="未知",
            skills="",
            description="",
            source="51job",
            source_url="",
            publish_time="",
            crawl_time="2024-01-01",
        )
        assert job.normalized_status == "ok"


class TestQualityReport:
    def test_to_dict_structure(self) -> None:
        r = QualityReport(source="51job", date="2024-01-01", raw_count=10, normalized_count=9)
        d = r.to_dict()
        assert d["source"] == "51job"
        assert d["raw_count"] == 10
        assert d["missing_rates"]["title"] == 0.0


# ── pipeline ──────────────────────────────────────────

class TestParseLocation:
    def test_city_district(self) -> None:
        city, district = parse_location("成都·高新区")
        assert city == "成都"
        assert district == "高新区"

    def test_city_only(self) -> None:
        city, district = parse_location("成都")
        assert city == "成都"
        assert district == ""

    def test_empty(self) -> None:
        city, district = parse_location("")
        assert city == ""
        assert district == ""


class TestNormalizeJob:
    def test_basic_normalization(self) -> None:
        raw = RawJob(
            source="51job",
            source_job_id="123",
            source_url="https://example.com/job/123",
            raw_title="Python 工程师",
            raw_company="某科技",
            raw_salary="10-15K",
            raw_location="成都·高新区",
            raw_experience="3-5年",
            raw_education="本科",
            raw_industry="互联网",
            raw_company_size="100-499人",
            raw_financing="B轮",
            raw_skills=["Python", "Django"],
            raw_description="负责 Python 后端开发",
            raw_publish_time="2024-01-01",
            crawl_time="2024-01-01",
        )
        n = normalize_job(raw)
        assert n.title == "Python 工程师"
        assert n.city == "成都"
        assert n.district == "高新区"
        assert n.normalized_status == "ok"
        assert "Python" in n.skills
        assert "Django" in n.skills

    def test_missing_required_fields(self) -> None:
        raw = RawJob(source="51job", source_url="https://example.com/job/1")
        n = normalize_job(raw)
        assert "missing" in n.normalized_status

    def test_salary_text_retained(self) -> None:
        raw = RawJob(
            source="51job",
            source_url="https://example.com/job/1",
            raw_title="X",
            raw_company="Y",
            raw_salary="面议",
        )
        n = normalize_job(raw)
        assert n.salary_text == "面议"


class TestNormalizeBatch:
    def test_filters_blocked(self) -> None:
        raw_jobs = [
            RawJob(source="51job", source_platform_status="blocked"),
            RawJob(source="51job", source_platform_status="ok",
                   source_url="https://example.com/1", raw_title="Test", raw_company="Co"),
        ]
        result = normalize_batch(raw_jobs)
        assert len(result) == 1


class TestPipelineIntegration:
    def test_full_pipeline(self) -> None:
        # 创建临时 JSONL
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
        ) as f:
            jsonl_path = Path(f.name)
            json.dump({
                "source": "51job",
                "source_job_id": "001",
                "source_url": "https://example.com/job/001",
                "raw_title": "Python 后端",
                "raw_company": "某科技",
                "raw_salary": "15-20K",
                "raw_location": "成都·高新区",
                "source_platform_status": "ok",
            }, f)
            f.write("\n")

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            csv_path = Path(f.name)

        try:
            count, normalized = pipeline(jsonl_path, csv_path)
            assert count == 1
            assert len(normalized) == 1
            assert csv_path.exists()
            content = csv_path.read_text()
            assert "Python 后端" in content
            assert "高新区" in content
        finally:
            jsonl_path.unlink(missing_ok=True)
            csv_path.unlink(missing_ok=True)


# ── quality ───────────────────────────────────────────

class TestQualityReport:
    def test_generate_from_data(self) -> None:
        raw_jobs = [
            RawJob(
                source="51job",
                source_job_id="001",
                source_url="https://example.com/job/001",
                raw_title="Python 后端",
                raw_company="某科技",
                raw_salary="15-20K",
                raw_location="成都·高新区",
            ),
        ]
        normalized = normalize_batch(raw_jobs)
        report = generate_quality_report(raw_jobs, normalized, "51job", duration_seconds=5.0)
        assert report.raw_count == 1
        assert report.normalized_count == 1
        assert report.status_ok == 1
        assert report.missing_title == 0.0
        assert report.salary_parse_success_rate == 1.0

    def test_missing_salary_detection(self) -> None:
        raw_jobs = [
            RawJob(
                source="51job",
                source_url="https://example.com/1",
                raw_title="T",
                raw_company="C",
                raw_salary="",  # 无薪资
            ),
        ]
        normalized = normalize_batch(raw_jobs)
        report = generate_quality_report(raw_jobs, normalized, "51job")
        assert report.missing_salary == 1.0

    def test_save_report(self) -> None:
        raw_jobs = [
            RawJob(
                source="51job",
                source_url="https://example.com/1",
                raw_title="T",
                raw_company="C",
            ),
        ]
        normalized = normalize_batch(raw_jobs)
        report = generate_quality_report(raw_jobs, normalized, "51job")

        with tempfile.TemporaryDirectory() as d:
            reports_dir = Path(d)
            saved = save_report(report, reports_dir)
            assert saved.exists()
            data = json.loads(saved.read_text())
            assert data["source"] == "51job"
