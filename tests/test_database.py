"""database.py 测试：建表、CSV upsert、采集记录。"""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.database import (
    SCHEMA,
    ImportStats,
    connect,
    import_csv_with_stats,
    init_db,
    record_crawl_run,
)


def _temp_db() -> sqlite3.Connection:
    """创建临时数据库并初始化 schema。"""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


def _write_csv(path: Path, rows: list[dict]) -> None:
    """写入测试 CSV 文件。"""
    fieldnames = [
        "source_job_id", "title", "company_name", "salary_text",
        "city", "district", "experience", "education", "industry",
        "company_size", "financing_stage", "skills", "description",
        "source", "source_url", "publish_time", "crawl_time",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            complete = {fn: "" for fn in fieldnames}
            complete.update(row)
            writer.writerow(complete)


class TestSchemaCreation:
    """测试数据库 schema 创建。"""

    def test_tables_exist(self) -> None:
        conn = _temp_db()
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        table_names = {r["name"] for r in tables}
        assert "jobs" in table_names
        assert "job_skills" in table_names
        assert "crawl_runs" in table_names

    def test_jobs_unique_dedupe_key(self) -> None:
        conn = _temp_db()
        conn.execute(
            "INSERT INTO jobs (source, title, dedupe_key, crawl_time, created_at, updated_at)"
            " VALUES ('test', 'job1', 'test|1', '2024-01-01', '2024-01-01', '2024-01-01')"
        )
        conn.commit()
        try:
            conn.execute(
                "INSERT INTO jobs (source, title, dedupe_key, crawl_time, created_at, updated_at)"
                " VALUES ('test', 'job2', 'test|1', '2024-01-01', '2024-01-01', '2024-01-01')"
            )
            conn.commit()
            assert False, "Expected UNIQUE constraint violation"
        except sqlite3.IntegrityError:
            pass  # 预期行为：重复 dedupe_key 被拒绝


class TestImportCsvWithStats:
    """测试 CSV 导入和 upsert 统计。"""

    def test_insert_new_rows(self) -> None:
        conn = _temp_db()
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            path = Path(f.name)

        try:
            _write_csv(path, [
                {
                    "source": "51job",
                    "source_job_id": "001",
                    "title": "Python 后端",
                    "company_name": "某科技",
                    "city": "成都",
                    "salary_text": "10-15K",
                },
            ])
            stats = import_csv_with_stats(conn, path)
            assert stats.inserted == 1
            assert stats.updated == 0
        finally:
            path.unlink(missing_ok=True)

    def test_update_existing_row(self) -> None:
        conn = _temp_db()
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            path = Path(f.name)

        try:
            # 第一次导入
            _write_csv(path, [
                {
                    "source": "51job",
                    "source_job_id": "001",
                    "title": "Python 后端",
                    "company_name": "某科技",
                    "city": "成都",
                    "salary_text": "10-15K",
                },
            ])
            stats1 = import_csv_with_stats(conn, path)
            assert stats1.inserted == 1

            # 第二次导入同一岗位，薪资变了
            _write_csv(path, [
                {
                    "source": "51job",
                    "source_job_id": "001",
                    "title": "Python 后端",
                    "company_name": "某科技",
                    "city": "成都",
                    "salary_text": "15-20K",
                },
            ])
            stats2 = import_csv_with_stats(conn, path)
            assert stats2.updated == 1
            assert stats2.inserted == 0

            # 验证薪资已更新
            row = conn.execute(
                "SELECT salary_min, salary_max FROM jobs WHERE dedupe_key='51job|001'"
            ).fetchone()
            assert row["salary_min"] == 15000
            assert row["salary_max"] == 20000
        finally:
            path.unlink(missing_ok=True)

    def test_empty_row_inserted_with_fallback_key(self) -> None:
        """完全空行 → 三级回退生成 |||| → 被插入（非 skip）。

        这是当前 canonical_job_key 的实际行为：第三级回退
        title|company|city|district 永远非空（至少返回 ||||）。
        database.py 的 skip 路径仅当 dedupe_key 为空字符串时触发。
        """
        conn = _temp_db()
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            path = Path(f.name)

        try:
            _write_csv(path, [{}])
            stats = import_csv_with_stats(conn, path)
            assert stats.inserted == 1
        finally:
            path.unlink(missing_ok=True)

    def test_minimal_row_inserted_by_fallback_key(self) -> None:
        """仅 title 的行通过三级回退生成 dedupe_key，应被插入。"""
        conn = _temp_db()
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            path = Path(f.name)

        try:
            _write_csv(path, [{"title": "X"}])
            stats = import_csv_with_stats(conn, path)
            assert stats.inserted == 1
            assert stats.skipped == 0
        finally:
            path.unlink(missing_ok=True)

    def test_job_skills_created(self) -> None:
        """导入后 job_skills 表应包含技能关联。"""
        conn = _temp_db()
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            path = Path(f.name)

        try:
            _write_csv(path, [
                {
                    "source": "51job",
                    "source_job_id": "001",
                    "title": "Python 后端工程师",
                    "company_name": "某科技",
                    "city": "成都",
                    "salary_text": "10-15K",
                    "skills": "Python,SQL,Redis",
                    "description": "熟悉 Python、SQL、Redis 等常用工具",
                },
            ])
            stats = import_csv_with_stats(conn, path)
            assert stats.inserted == 1

            skills = conn.execute(
                "SELECT skill FROM job_skills WHERE job_id=1 ORDER BY skill"
            ).fetchall()
            skill_names = [s["skill"] for s in skills]
            assert "Python" in skill_names
            assert "Redis" in skill_names
        finally:
            path.unlink(missing_ok=True)


class TestCrawlRunRecording:
    """测试采集运行记录。"""

    def test_record_basic_run(self) -> None:
        conn = _temp_db()
        record_crawl_run(
            conn,
            source="job51_xbrowser",
            city="成都",
            keywords=["Python", "Java"],
            start_time="2024-01-01T00:00:00",
            end_time="2024-01-01T00:05:00",
            total_collected=60,
            new_inserted=50,
            updated=10,
        )
        row = conn.execute("SELECT * FROM crawl_runs").fetchone()
        assert row is not None
        assert row["source"] == "job51_xbrowser"
        assert row["city"] == "成都"
        assert row["total_collected"] == 60
        assert row["new_inserted"] == 50
