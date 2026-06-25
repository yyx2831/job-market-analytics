"""薪资历史追踪器 — 记录并查询技能薪资随时间的变化。

每次采集后 snapshot 即可跟踪薪资走势。
"""

from __future__ import annotations

import sqlite3
import re
from collections import defaultdict
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

import pandas as pd


def ensure_salary_history_table(conn: sqlite3.Connection) -> None:
    """创建薪资历史表（如果不存在）。"""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS salary_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            city TEXT NOT NULL,
            skill TEXT NOT NULL,
            record_date TEXT NOT NULL,
            job_count INTEGER NOT NULL,
            avg_salary REAL,
            median_salary REAL,
            p25_salary REAL,
            p75_salary REAL,
            created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
            UNIQUE(city, skill, record_date)
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_salary_history_skill
        ON salary_history(city, skill, record_date)
    """)
    conn.commit()


def snapshot_skill_salaries(conn: sqlite3.Connection, record_date: Optional[str] = None) -> int:
    """根据当前 jobs 表按 (城市, 技能) 生成薪资快照。

    返回写入的记录数。
    """
    ensure_salary_history_table(conn)

    if record_date is None:
        record_date = date.today().isoformat()

    # 从 jobs 中按 (city, skill) 聚合薪资
    df = pd.read_sql_query("""
        SELECT j.city, js.skill, j.salary_avg
        FROM jobs j
        JOIN job_skills js ON j.id = js.job_id
        WHERE j.salary_avg IS NOT NULL
    """, conn)

    if df.empty:
        return 0

    stats = df.groupby(["city", "skill"])["salary_avg"].agg(
        count="count",
        mean="mean",
        median="median",
        p25=lambda x: x.quantile(0.25),
        p75=lambda x: x.quantile(0.75),
    ).reset_index()

    inserted = 0
    for _, row in stats.iterrows():
        if row["count"] < 3:
            continue
        conn.execute("""
            INSERT OR REPLACE INTO salary_history
                (city, skill, record_date, job_count, avg_salary, median_salary, p25_salary, p75_salary)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            row["city"], row["skill"], record_date,
            int(row["count"]),
            round(row["mean"], 1),
            round(row["median"], 1),
            round(row["p25"], 1),
            round(row["p75"], 1),
        ))
        inserted += 1

    conn.commit()
    return inserted


def load_salary_history(
    conn: sqlite3.Connection,
    skill: Optional[str] = None,
    city: Optional[str] = None,
    min_records: int = 2,
) -> pd.DataFrame:
    """加载薪资历史数据，可筛选技能/城市。

    返回 DataFrame，含 city, skill, record_date, job_count, avg_salary, median_salary。
    自动过滤仅有单次记录的 (city, skill) 组合。
    """
    ensure_salary_history_table(conn)

    where_parts = ["1=1"]
    params: list = []

    if skill:
        where_parts.append("skill = ?")
        params.append(skill)
    if city:
        where_parts.append("city = ?")
        params.append(city)

    where = " AND ".join(where_parts)

    df = pd.read_sql_query(f"""
        SELECT * FROM (
            SELECT sh.*,
                   COUNT(*) OVER (PARTITION BY city, skill) AS record_count
            FROM salary_history sh
            WHERE {where}
        ) sub
        WHERE record_count >= ?
        ORDER BY record_date
    """, conn, params=params + [min_records])

    if not df.empty:
        df["record_date"] = pd.to_datetime(df["record_date"])

    return df


def compute_salary_changes(
    conn: sqlite3.Connection,
    city: Optional[str] = None,
    top_n: int = 20,
) -> pd.DataFrame:
    """计算每个技能在时间段内的薪资变化（首条记录 → 最新记录）。

    返回城市、技能、首次日期、最新日期、首次均薪、最新均薪、变化额、变化率。
    按变化额绝对值排序。
    """
    ensure_salary_history_table(conn)

    city_filter = "AND city = ?" if city else ""
    params: list = [city] if city else []

    df = pd.read_sql_query(f"""
        WITH ranked AS (
            SELECT city, skill, record_date, avg_salary, job_count,
                   ROW_NUMBER() OVER (PARTITION BY city, skill ORDER BY record_date ASC) AS rn_first,
                   ROW_NUMBER() OVER (PARTITION BY city, skill ORDER BY record_date DESC) AS rn_last
            FROM salary_history
            WHERE 1=1 {city_filter}
        ),
        first_rec AS (
            SELECT city, skill, record_date AS first_date, avg_salary AS first_salary
            FROM ranked WHERE rn_first = 1
        ),
        last_rec AS (
            SELECT city, skill, record_date AS last_date, avg_salary AS last_salary
            FROM ranked WHERE rn_last = 1
        )
        SELECT f.city, f.skill, f.first_date, l.last_date,
               f.first_salary, l.last_salary,
               (l.last_salary - f.first_salary) AS change,
               CASE WHEN f.first_salary > 0
                    THEN ROUND((l.last_salary - f.first_salary) / f.first_salary * 100, 1)
                    ELSE 0 END AS change_pct
        FROM first_rec f
        JOIN last_rec l ON f.city = l.city AND f.skill = l.skill
        WHERE f.first_date < l.last_date
        ORDER BY ABS(l.last_salary - f.first_salary) DESC
        LIMIT ?
    """, conn, params=params + [top_n])

    if not df.empty:
        df["first_date"] = pd.to_datetime(df["first_date"])
        df["last_date"] = pd.to_datetime(df["last_date"])

    return df


def get_available_skills_for_tracking(conn: sqlite3.Connection) -> List[str]:
    """返回有历史追踪数据的技能列表。"""
    ensure_salary_history_table(conn)
    cur = conn.execute("""
        SELECT DISTINCT skill FROM salary_history
        WHERE skill IN (
            SELECT skill FROM salary_history
            GROUP BY skill, city
            HAVING COUNT(*) >= 2
        )
        ORDER BY skill
    """)
    return [r[0] for r in cur.fetchall()]


def init_salary_history(conn: sqlite3.Connection) -> int:
    """一键初始化：建表 + 生成首次快照。"""
    ensure_salary_history_table(conn)
    return snapshot_skill_salaries(conn)
