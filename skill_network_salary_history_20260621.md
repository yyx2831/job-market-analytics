# 技能共现网络 + 薪资历史追踪 — 实现报告

**Date:** 2026-06-21 16:02 CST  
**Duration:** ~2h

## Objective
实现两大分析模块：技能共现网络（可视化效果） + 薪资历史追踪（数据基础），作为仪表盘第 8、9 标签页。

---

## 模块 1：技能共现网络 `🔗 技能网络`

### 实现文件
- `src/analytics/skill_network.py` (4,943 字节) — 图分析引擎
- `src/ui/skill_network.py` (10,030 字节) — Plotly 交互可视化

### 核心能力
| 能力 | 实现 | 当前数据验证 |
|------|------|-------------|
| 图构建 | 加权无向图，节点=技能，边权重=共现次数 | 51 节点, 442 边 |
| 社区检测 | python-louvain (Louvain 算法) | 15 个技能社群 |
| 中心性 | DegreeCentrality + PageRank + BetweennessCentrality | SQL > Python > Java |
| 路径发现 | shortest_path (Dijkstra) | Python→K8s: 4 步 |
| 邻域子图 | ego_network (radius=N) | Python 邻域: 37 节点 |

### 社群结构 (Top 5)
1. **SQL 社群** (14 技能, 4,056 需求)
2. **Python 社群** (13 技能, 2,891 需求)
3. **Java 社群** (6 技能, 1,688 需求)
4. **需求分析 社群** (5 技能, 651 需求)
5. **销售 社群** (3 技能, 263 需求)

### UI 功能
- 网络图 (力导向/环形布局, 按社群着色)
- 网络指标卡片 (密度、连通分量、聚类系数)
- 社群分解浏览
- PageRank 排行 + 介数中心性排行 (双栏)
- 技能升级路径发现器 (选起点→终点, 高亮最短路径)
- 社群速览 (选社群看内部关系)

---

## 模块 2：薪资历史追踪 `📈 薪资追踪`

### 实现文件
- `src/analytics/salary_tracker.py` (5,950 字节) — 快照引擎
- `src/ui/salary_trend.py` (6,601 字节) — 趋势可视化

### 数据模型
```sql
CREATE TABLE salary_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    city TEXT NOT NULL,
    skill TEXT NOT NULL,
    record_date TEXT NOT NULL,       -- 快照日期
    job_count INTEGER NOT NULL,      -- 该技能岗位数
    avg_salary REAL,                 -- 均薪
    median_salary REAL,             -- 中位薪资
    p25_salary REAL,                -- 25分位
    p75_salary REAL,                -- 75分位
    UNIQUE(city, skill, record_date)
);
```

### 核心函数
| 函数 | 功能 |
|------|------|
| `init_salary_history()` | 建表 + 首次快照 (270 条记录) |
| `snapshot_skill_salaries()` | 按城市×技能聚合生成快照 |
| `load_salary_history()` | 加载历史 (≥2 记录才返回趋势) |
| `compute_salary_changes()` | 首末对比：变化额、变化率 |
| `get_available_skills_for_tracking()` | 有历史追踪的技能列表 |

### UI 功能
- 📸 一键快照按钮
- 城市 + 技能筛选
- 薪资变化排行榜 (涨/跌双栏对比)
- 技能薪资走势折线图 (多选)
- 可选分位区间图 (P25-P75)

### 使用方式
1. 首次加载 → 点「📸 生成快照」初始化
2. 后续每次采集后 → 再点一次快照
3. 积累≥2次快照后 → 趋势图表自动显示

---

## Bug 修复 (附带)
- `trends.py`: `publish_time` 混合格式 (日期 + datetime) → `format='mixed'` 解决
- `skill_network.py`: 变量命名 typo 修正

## 仪表盘现状
9 标签页全部正常运行 | 40/40 测试通过 | http://localhost:8501

## 新增依赖
- `networkx==3.2.1`
- `python-louvain==0.16`
