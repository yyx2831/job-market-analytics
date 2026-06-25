# 数据质量 v2 + 采集稳健性 + 岗位对标 — 完成记录

## 时间
2026-06-21 22:25 ~ 22:55

## 🥇 数据质量 v2：薪资三路修复

### 执行结果
- **年薪制 (÷12)**: 69 条 — salary_text 含 "万/年" 但存储值为年薪量级
- **年薪制 (改 label)**: 83 条 — 存储值已是月薪量级,仅将 salary_unit 改为 "year"
- **日薪制 (×22)**: 13 条 — 从 salary_text 提取日薪 ×22 工作日转月薪
- **"千"×10 bug**: 311 条 — "8千" 被错误解析为 80000 (应为 8000), 修复后 avg 从 ¥46K 降至 ¥9.5K

**总计修复**: 476 条 (69+83+13+311)

### 修复前 vs 修复后
| 指标 | 修复前 | 修复后 |
|------|--------|--------|
| 平均月薪 | ¥22.4K | ¥14.7K |
| >80K 异常条目 | 75 | **0** |
| salary_unit="day" | 13 | **0** |
| salary_months=NULL | 10 | 10 (未处理) |

### 保留问题
- 10 条 salary_months=NULL (低优先级)
- 4 条 salary_unit=NULL (低优先级)

## 🥈 采集稳健性增强

### run_spider.py 修改
- `--delay` (默认 3.0s): 关键词间延迟,含 0.8×~1.2× jitter 防反爬
- `--retries` (默认 2): 失败重试, backoff 5/10s
- `--checkpoint <path>`: 断点续传,记录已完成关键词,中断后可恢复

### mobile_51job.py 修改
- `collect()` 增加防御性错误处理
- 明确异常类型: RuntimeError (xbrowser/CDP 不可用), ValueError (无结果)
- xb_cleanup 异常不阻断流程

### Cron 更新
- 命令: `--delay 5 --retries 3 --checkpoint data/raw/.crawl_checkpoint`
- 每日 9:00 执行, timeout 480s

## 🥉 岗位对标分析器

### 新文件: `src/analytics/position_benchmark.py` (16.6KB)

### 核心能力
1. **标题标准化**: 去除地点/公司/薪资格式后缀, 识别职级 (junior/mid/senior/lead/manager), 归类职位族 (AI/算法, 后端开发, 前端开发, 数据, 测试/QA, 运维/DevOps, 嵌入式/硬件, 产品, 销售/运营, C++开发, 安全)
2. **市场对标** (`benchmark`): 给定职位+城市+薪资 → 返回全国/本城 P25/P50/P75, 百分位, 差值百分比, 评估建议, TOP 技能
3. **城市热力** (`city_heatmap`): 跨城市 P25/P50/P75 薪资对比
4. **职位差距** (`position_gap_analysis`): 同职位的城市间极差 + 排名

### CLI 用法
```
python3 -m src.analytics.position_benchmark benchmark --title "AI算法工程师" --salary 25000 --city "北京"
python3 -m src.analytics.position_benchmark heatmap --family "AI/算法"
python3 -m src.analytics.position_benchmark gap --title "Java开发"
```

### 验证结果
- AI/算法 北京 P50=¥20K, 成都 P50=¥15K, 重庆 P50=¥11.5K
- 前端开发 成都 ¥12K → 百分位 48.3% (中等偏下)
- AI算法 北京 ¥25K → 百分位 76.4% (高于市场)
- Java开发 城市极差 ¥8K (上海 ¥19.5K vs 重庆 ¥11.5K)
