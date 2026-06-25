"""SQLite 数据库层：建表、CSV 增量 upsert 导入、采集运行记录。

三表结构：
- jobs — 岗位主表，dedupe_key UNIQUE 约束实现增量 upsert
- job_skills — 岗位-技能多对多关联表
- crawl_runs — 采集运行审计表

核心函数：
- import_csv_with_stats() — CSV 导入，返回 ImportStats(inserted, updated, skipped)
- record_crawl_run() — 记录每次采集的执行情况
"""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path
from typing import NamedTuple

from .cleaning import canonical_job_key, extract_skills, normalize_text, now_iso, parse_salary


SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  id INTEGER PRIMARY KEY,
  source TEXT NOT NULL,
  source_job_id TEXT,
  title TEXT NOT NULL,
  company_name TEXT,
  city TEXT,
  district TEXT,
  salary_text TEXT,
  salary_min INTEGER,
  salary_max INTEGER,
  salary_avg INTEGER,
  salary_months INTEGER,
  salary_unit TEXT,
  experience TEXT,
  education TEXT,
  industry TEXT,
  company_size TEXT,
  financing_stage TEXT,
  skills TEXT,
  description TEXT,
  source_url TEXT,
  publish_time TEXT,
  crawl_time TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  dedupe_key TEXT UNIQUE
);

CREATE TABLE IF NOT EXISTS job_skills (
  id INTEGER PRIMARY KEY,
  job_id INTEGER NOT NULL,
  skill TEXT NOT NULL,
  UNIQUE(job_id, skill),
  FOREIGN KEY (job_id) REFERENCES jobs(id)
);

CREATE TABLE IF NOT EXISTS crawl_runs (
  id INTEGER PRIMARY KEY,
  source TEXT NOT NULL,
  city TEXT NOT NULL,
  keywords TEXT NOT NULL,
  start_time TEXT NOT NULL,
  end_time TEXT NOT NULL,
  total_collected INTEGER NOT NULL DEFAULT 0,
  new_inserted INTEGER NOT NULL DEFAULT 0,
  updated INTEGER NOT NULL DEFAULT 0,
  skipped INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
"""


class ImportStats(NamedTuple):
    """import_csv 返回的统计信息。"""
    inserted: int
    updated: int
    skipped: int


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def import_csv(conn: sqlite3.Connection, csv_path: Path) -> int:
    """导入 CSV，保持向后兼容，返回新增数量。内部使用 upsert。"""
    stats = import_csv_with_stats(conn, csv_path)
    return stats.inserted


def import_csv_with_stats(conn: sqlite3.Connection, csv_path: Path) -> ImportStats:
    """导入 CSV，支持增量 upsert，返回详细统计（新增/更新/跳过）。

    upsert 策略：
    - 以 dedupe_key (source|source_job_id) 为唯一键
    - 已存在则更新可变字段（薪资、技能、描述等）并更新 updated_at
    - title/company_name/city 等核心字段有值时才覆盖
    """
    init_db(conn)
    inserted = 0
    updated = 0
    skipped = 0

    with csv_path.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        for raw in reader:
            row = {key: normalize_text(value, "") for key, value in raw.items()}
            salary = parse_salary(row.get("salary_text"))
            skills = extract_skills([row.get("skills"), row.get("description"), row.get("title")])
            dedupe_key = canonical_job_key(row)
            timestamp = now_iso()
            crawl_time = row.get("crawl_time") or timestamp

            if not dedupe_key:
                # 无法生成去重键，跳过
                skipped += 1
                continue

            # 先查是否已存在
            existing = conn.execute(
                "SELECT id FROM jobs WHERE dedupe_key = ?", (dedupe_key,)
            ).fetchone()

            if existing is None:
                # 新记录：INSERT
                cursor = conn.execute(
                    """
                    INSERT OR IGNORE INTO jobs (
                      source, source_job_id, title, company_name, city, district,
                      salary_text, salary_min, salary_max, salary_avg, salary_months,
                      salary_unit, experience, education, industry, company_size,
                      financing_stage, skills, description, source_url, publish_time,
                      crawl_time, created_at, updated_at, dedupe_key
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row.get("source") or "manual",
                        row.get("source_job_id"),
                        row.get("title") or "未知岗位",
                        row.get("company_name") or "未知公司",
                        row.get("city") or "未知",
                        row.get("district") or "未知",
                        row.get("salary_text"),
                        salary["salary_min"],
                        salary["salary_max"],
                        salary["salary_avg"],
                        salary["salary_months"],
                        salary["salary_unit"],
                        row.get("experience") or "未知",
                        row.get("education") or "未知",
                        row.get("industry") or "未知",
                        row.get("company_size") or "未知",
                        row.get("financing_stage") or "未知",
                        ",".join(skills),
                        row.get("description"),
                        row.get("source_url"),
                        row.get("publish_time"),
                        crawl_time,
                        timestamp,
                        timestamp,
                        dedupe_key,
                    ),
                )
                if cursor.rowcount == 1:
                    inserted += 1
                    job_id = cursor.lastrowid
                    conn.executemany(
                        "INSERT OR IGNORE INTO job_skills (job_id, skill) VALUES (?, ?)",
                        [(job_id, skill) for skill in skills],
                    )
                else:
                    skipped += 1
            else:
                # 已存在：UPDATE 可变字段
                job_id = existing["id"]
                conn.execute(
                    """
                    UPDATE jobs SET
                      salary_text = COALESCE(NULLIF(?, ''), salary_text),
                      salary_min = COALESCE(?, salary_min),
                      salary_max = COALESCE(?, salary_max),
                      salary_avg = COALESCE(?, salary_avg),
                      salary_months = COALESCE(?, salary_months),
                      salary_unit = COALESCE(NULLIF(?, ''), salary_unit),
                      experience = COALESCE(NULLIF(?, ''), experience),
                      education = COALESCE(NULLIF(?, ''), education),
                      industry = COALESCE(NULLIF(?, ''), industry),
                      company_size = COALESCE(NULLIF(?, ''), company_size),
                      financing_stage = COALESCE(NULLIF(?, ''), financing_stage),
                      skills = COALESCE(NULLIF(?, ''), skills),
                      description = COALESCE(NULLIF(?, ''), description),
                      publish_time = COALESCE(NULLIF(?, ''), publish_time),
                      crawl_time = ?,
                      updated_at = ?
                    WHERE dedupe_key = ?
                    """,
                    (
                        row.get("salary_text"),
                        salary["salary_min"],
                        salary["salary_max"],
                        salary["salary_avg"],
                        salary["salary_months"],
                        salary["salary_unit"],
                        row.get("experience"),
                        row.get("education"),
                        row.get("industry"),
                        row.get("company_size"),
                        row.get("financing_stage"),
                        ",".join(skills) if skills else None,
                        row.get("description"),
                        row.get("publish_time"),
                        crawl_time,
                        timestamp,
                        dedupe_key,
                    ),
                )
                updated += 1
                # 更新 job_skills
                conn.executemany(
                    "INSERT OR IGNORE INTO job_skills (job_id, skill) VALUES (?, ?)",
                    [(job_id, skill) for skill in skills],
                )

    conn.commit()
    return ImportStats(inserted=inserted, updated=updated, skipped=skipped)


def record_crawl_run(
    conn: sqlite3.Connection,
    *,
    source: str,
    city: str,
    keywords: list[str],
    start_time: str,
    end_time: str,
    total_collected: int,
    new_inserted: int,
    updated: int,
    skipped: int = 0,
) -> None:
    """记录一次采集任务的执行情况到 crawl_runs 表。"""
    init_db(conn)
    conn.execute(
        """
        INSERT INTO crawl_runs (
          source, city, keywords, start_time, end_time,
          total_collected, new_inserted, updated, skipped, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            source,
            city,
            ",".join(keywords),
            start_time,
            end_time,
            total_collected,
            new_inserted,
            updated,
            skipped,
            now_iso(),
        ),
    )
    conn.commit()
