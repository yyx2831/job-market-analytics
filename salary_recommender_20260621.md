# 14薪换算 + 岗位推荐引擎 — 交付总结

**Date:** 2026-06-21 16:35 CST  
**Duration:** ~15 min

---

## 一、14薪 / 年薪换算 (`src/analytics/salary_parser.py`)

### 背景
- 原有 832 条记录 `salary_months IS NULL`（中文格式 `千/万` 未解析）
- 25 条 `万/年` 格式被错误当成月薪
- 794 条 13-20薪已正确解析

### 交付
- 支持格式: `10-20K`, `1-2万`, `8千-1.2万`, `4-6千`, `15-20万/年`
- 额外薪数: `·13薪`, `·14薪`, `13-16薪`, `年底双薪`, `年终奖2-4月`
- 输出: `salary_annual`(年薪), `salary_monthly_equiv`(折12薪月薪)
- 函数: `parse_salary()`, `enhance_salary_columns()`, `months_distribution()`, `fourteen_month_analysis()`

### 仪表盘集成
- 薪资分析页新增「年薪换算」标签页
- 4 KPI 卡片: 12薪/13+薪岗数+均薪、月薪溢价%、年薪差距
- 年薪月数饼图 + 各薪数箱线图 + 年薪直方图(P50/P75标注)
- 分城市年薪对比表 + 多薪月溢价柱状图

---

## 二、岗位推荐引擎 (`src/analytics/recommender.py`)

### 架构
- `JobSeeker`: 求职者画像 dataclass（技能/城市/薪资/经验/行业 + 权重）
- `JobRecommender`: 
  - TF-IDF 技能向量 → 余弦相似度
  - 薪资拟合度（目标是否在 [min, max] 区间，高斯衰减）
  - 相关性（城市+行业+经验 多信号叠加）
  - 加权综合: 0.55 技能 + 0.25 薪资 + 0.20 相关性（可调）
- `recommend_by_job_id()`: 基于岗位ID找相似岗位
- `skill_gap_analysis()`: 技能缺口检测（critical/moderate/nice-to-have）
- `competitor_analysis()`: 竞品分析（竞争烈度/薪资排名/需求规模）

### 仪表盘集成 (`src/ui/recommender.py`)
- 第 11 标签页「🎯 智能推荐」
- 画像输入: 多选技能 + 目标城市 + 期望月薪 + 经验等级
- 可调权重滑块
- TOP20 推荐表（综合分/技能分/薪资分 颜色编码）
- 技能缺口分析 + 市场竞品分析

---

## 仪表盘现状
**11 标签页**: 概览 → 观点 → 趋势 → 薪资分析(4子页) → 城市对比 → 明细 → 学习路线 → 技能网络 → 薪资追踪 → 雇主画像 → 智能推荐

- 0 运行时异常 / 40/40 测试通过 / HTTP 200
