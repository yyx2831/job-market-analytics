"""购买力薪资调整 — 生活成本归一化。

不同城市的生活成本差异巨大（房租=最大变量），直接比薪资不公平。
引入城市生活成本系数，将薪资折算为「成都等值薪资」，消除地域差异。

数据来源：综合公开租房/物价/交通数据估算，以成都为基准(100)。
"""

from __future__ import annotations

from typing import Dict, List, Optional

import pandas as pd

# ── 城市生活成本指数（成都=100）──
# 综合房租(40%)+餐饮(25%)+交通(10%)+日常消费(25%)
CITY_COST_INDEX: Dict[str, float] = {
    # 基准
    "成都": 100.0,
    # 一线
    "北京": 230.0,
    "上海": 245.0,
    "深圳": 250.0,
    "广州": 185.0,
    # 新一线
    "杭州": 175.0,
    "南京": 145.0,
    "武汉": 115.0,
    "西安": 105.0,
    "重庆": 95.0,
    # 其他
    "苏州": 145.0,
    "长沙": 90.0,
    "天津": 140.0,
    "东莞": 120.0,
    "郑州": 100.0,
    "合肥": 105.0,
    "厦门": 160.0,
    "福州": 115.0,
    "济南": 105.0,
    "青岛": 120.0,
    "沈阳": 95.0,
    "大连": 110.0,
    "长春": 85.0,
    "哈尔滨": 85.0,
    "昆明": 95.0,
    "贵阳": 85.0,
    "南宁": 85.0,
    "海口": 110.0,
    "拉萨": 100.0,
    "远程办公": 100.0,
}


def get_cost_index(city: str) -> float:
    """获取城市生活成本指数。"""
    return CITY_COST_INDEX.get(city, 100.0)


def purchasing_power_salary(salary: float, city: str) -> float:
    """将薪资折算为「成都等值购买力薪资」。

    Formula: adjusted = salary / cost_index * 100

    Args:
        salary: 原始月薪 (K)
        city: 城市名称

    Returns:
        调整后月薪 (K)
    """
    idx = get_cost_index(city)
    if idx <= 0:
        return salary
    return salary / idx * 100.0


def add_purchasing_power(df: pd.DataFrame) -> pd.DataFrame:
    """为 DataFrame 添加购买力调整薪资列。

    新增列：
    - pp_salary: 购买力调整后薪资（成都等值）
    - cost_index: 生活成本指数

    Args:
        df: 岗位 DataFrame，需包含 city 和 salary_avg 列

    Returns:
        添加了 pp_salary 和 cost_index 列的 DataFrame
    """
    result = df.copy()

    if "city" not in result.columns or "salary_avg" not in result.columns:
        return result

    result["cost_index"] = result["city"].apply(get_cost_index)
    result["pp_salary"] = result.apply(
        lambda r: r["salary_avg"] / r["cost_index"] * 100
        if r["cost_index"] and not pd.isna(r["salary_avg"])
        else None,
        axis=1,
    )
    return result


def city_comparison_adjusted(df: pd.DataFrame) -> pd.DataFrame:
    """生成城市对比表（含购买力调整）。

    Returns:
        城市对比 DataFrame，含原始均薪、购买力均薪、成本指数
    """
    if "city" not in df.columns or "salary_avg" not in df.columns:
        return pd.DataFrame()

    real = df[df["salary_avg"].notna()].copy()
    if real.empty:
        return pd.DataFrame()

    real = add_purchasing_power(real)

    stats = real.groupby("city").agg(
        岗位数=("id", "count"),
        原始均薪=("salary_avg", "mean"),
        原始中位=("salary_avg", "median"),
        购买力均薪=("pp_salary", "mean"),
        购买力中位=("pp_salary", "median"),
        成本指数=("cost_index", "first"),
    ).reset_index()

    stats["原始均薪"] = stats["原始均薪"].round(1)
    stats["原始中位"] = stats["原始中位"].round(1)
    stats["购买力均薪"] = stats["购买力均薪"].round(1)
    stats["购买力中位"] = stats["购买力中位"].round(1)
    stats["成本指数"] = stats["成本指数"].astype(int)

    return stats.sort_values("购买力均薪", ascending=False)
