# 51job 移动站采集器 — 完成报告

**时间：** 2026-06-21 21:21-21:42  
**目标：** 修复 51job 数据采集（WAF JS Challenge 阻断）

---

## 问题诊断

| 方案 | 状态 | 原因 |
|------|------|------|
| job51 API 直连 | ❌ blocked | WAF JS Challenge |
| PC 站 xbrowser | ❌ 空 DOM | 竞态/iframe 隔离 |
| **移动站 m.51job.com** | ✅ 成功 | 完整 DOM 可用 |

---

## 实现方案

**文件：** `src/scraping/sources/mobile_51job.py` (18.5KB)

```
流程：xbrowser(CFT)打开 m.51job.com → xb fill搜索框 → CDP点击搜索 → 
     CDP滚动加载多页 → xb snapshot ARIA → Python状态机解析 → SQLite入库
```

### 核心模块

| 模块 | 行数 | 功能 |
|------|------|------|
| `xb_*()` 封装 | ~200 | xbrowser CFT 生命周期管理 |
| `CdpClient` | ~60 | CDP WebSocket 自动化 |
| `ParsedJob` | ~80 | 数据模型 + 薪资正则 + 正则单位转换(万/千/元→统一元/月) |
| `parse_snapshot()` | ~90 | ARIA 状态机解析器 (out/in_strong/expect_salary/in_tags/expect_company_type/in_emphasis/expect_contact) |
| `collect()` | ~30 | 采集主流程 |
| `save_to_db()` | ~50 | SQLite 写入(匹配现有 schema) |

### 已修复的问题

1. **薪资单位不匹配** → 统一转换为 `元/月`，`salary_unit="month"`，`salary_min/max` 为实际元值
2. **source 名不一致** → 统一使用 `"job51"`
3. **SQL 列/值数量不匹配** → 24列全对齐（含 `updated_at`）
4. **技能关键词误判为公司名** → 新增 `_SKILL_KEYWORDS_LOWER` 集合（60+技能名）
5. **空 `job_market.db`** → 已删除，实际使用 `data/processed/jobs.db`

---

## 验证结果

```
关键词    条数  入库  ID范围
Python   10   10   ✅
Java     10   10   ✅
前端      10   10   ✅
数据分析   10   10   ✅
AI       10   10   ✅
───────────────
合计     50   50   6185-6194
```

DB 总量：3979 → 3989

---

## 集成方式

```bash
# 命令行直接调用
python3 -m src.scraping.sources.mobile_51job --keyword Python --limit 30 --db data/processed/jobs.db

# 通过主采集入口
python3 scripts/run_spider.py --source job51_mobile --keywords Python Java --limit-per-kw 30

# 全量关键词
python3 scripts/run_spider.py --source job51_mobile --all-keywords --limit-per-kw 30
```

---

## 已知限制

1. 移动站不支持城市筛选 → 全国搜索结果
2. 每关键词单次最多 ~10条（每页10条）
3. 部分字段解析质量待提升（公司名、技能标签遗漏）
4. 依赖 xbrowser CFT 浏览器 + CDP WebSocket
