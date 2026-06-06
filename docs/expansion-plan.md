# 数据扩容计划 2026-06-06

## 目标
高质量真实数据：目标 5000+ 条，覆盖主流城市 + 10 个技术关键词

## Phase 1: 榨干 51job

### 1.1 扩展关键词（3 → 10）
```
Python, Java, 前端, 数据分析, 测试, 运维, 产品经理, AI/算法, 运营, 销售
```

### 1.2 扩展城市（6 → 10）
```
已有: 北京,上海,广州,深圳,杭州,成都
新增: 南京,武汉,西安,重庆
```

### 1.3 每城每关键词 2 页（40 条）
- 10 城市 × 10 关键词 × 40 条 = 4000 潜力
- 每条城市 ~20 API 调用，WAF 恢复机制兜底
- 预计总耗时 ~80 分钟

### 1.4 修复 bug
`run_spider.py` 中 `run_job51_xbrowser()` 硬编码了 `rate_min=1.5, rate_max=3.0`，
覆盖了类默认的 15-30s。需要修复为使用默认值。

## Phase 2: 新增平台

### BOSS直聘 (zhipin.com)
- 中国最大招聘平台
- 技术方案: xbrowser eval + XHR 抓 API

### 拉勾 (lagou.com)
- 专注互联网/技术岗位
- 技术方案: xbrowser eval + XHR

### 猎聘 (liepin.com)
- 专注中高端岗位
- 技术方案: xbrowser eval + XHR

通用模式: 所有平台共用 RawJob → NormalizedJob → DB 归一化管道
