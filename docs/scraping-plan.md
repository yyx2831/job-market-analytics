# 国内招聘网站数据采集计划

> 项目：job-market-analytics  
> 日期：2026-06-04  
> 目标：从国内主流招聘网站爬取真实岗位数据，替代当前假数据

---

## 一、目标网站分析

### 1.1 候选平台

| 平台 | 岗位量 | 反爬强度 | 覆盖度 | 优先级 |
|------|--------|----------|--------|--------|
| **BOSS直聘** | ⭐⭐⭐⭐⭐ | 🔴 极高 | 全行业，尤其互联网 | P0 |
| **前程无忧（51job）** | ⭐⭐⭐⭐ | 🟡 中等 | 全行业，企业覆盖面广 | P0 |
| **智联招聘** | ⭐⭐⭐⭐ | 🟡 中高 | 全行业，传统行业多 | P1 |
| **拉勾网** | ⭐⭐⭐ | 🟠 较高 | 互联网/IT 垂直 | P1 |
| **猎聘** | ⭐⭐⭐ | 🟠 较高 | 中高端岗位为主 | P2 |

### 1.2 各平台反爬技术拆解

#### BOSS直聘（bosszp.com / zhipin.com）

- **登录强制**：搜索/查看岗位详情必须先登录（手机号注册）
- **验证码**：极验（Geetest）滑块验证，登录时触发频率高
- **渲染方式**：React SPA，纯 JS 渲染，直接请求 HTML 为空壳
- **接口加密**：搜索 API 返回数据经过 `zp_token` / `__zp_stoken__` 加密
- **频率限制**：同一账号短时间多次搜索触发滑块验证，严重时封号
- **反调试**：`devtools` 检测，检测到控制台打开则阻止请求
- **数据接口**：`wapi/zpgeek/search/joblist.json`（搜索列表）、`wapi/zpgeek/job/detail.json`（详情）
- **最大翻页**：单个搜索条件最多展示 10 页，约 150 条结果

#### 前程无忧（51job.com）

- **登录**：搜索可免登录，但翻页超过一定次数后弹登录框
- **验证码**：登录时有滑块验证，浏览过程中偶发
- **渲染方式**：混合渲染，列表页部分 SSR，详情页 JS 渲染
- **接口加密**：搜索接口参数含 `sign` 签名，由前端 JS 动态生成
- **频率限制**：单 IP 短时间高频请求触发 403 或验证码
- **反爬特征**：请求头检测（Referer、User-Agent）、`window._did` 设备指纹
- **最大翻页**：搜索结果最多 100 页，但 60 页后数据大量重复

#### 智联招聘（zhaopin.com）

- **登录**：查看详情前需登录
- **验证码**：极验或网易易盾
- **渲染方式**：Vue SPA，全 JS 渲染
- **反爬**：API 请求带动态 token，类似 BOSS

#### 拉勾网（lagou.com）

- **登录**：登录后才能搜索，限制了未登录用户
- **验证码**：滑块验证，高频操作触发
- **反爬**：前端重度使用 Webpack + 代码混淆，API 参数复杂
- **当前状态**：2024 年后活跃度下降，岗位量减少

---

## 二、技术架构

### 2.1 总体架构

```
┌──────────────────────────────────────────────────────┐
│                    调度层 (Scheduler)                  │
│  APScheduler / Celery Beat                           │
│  每日凌晨 2:00 触发增量采集，每周日全量刷新            │
└──────────────┬───────────────────────────────────────┘
               │
┌──────────────▼───────────────────────────────────────┐
│                采集引擎 (Spider Engine)                │
│                                                       │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐           │
│  │ BOSS直聘 │  │ 前程无忧  │  │ 拉勾网   │  ...      │
│  │ Spider   │  │ Spider   │  │ Spider   │           │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘           │
│       │              │              │                 │
│  ┌────▼──────────────▼──────────────▼─────┐          │
│  │         Playwright / CDP 浏览器层        │          │
│  │  (多实例 + Cookie 持久化 + 代理池)       │          │
│  └────────────────┬───────────────────────┘          │
│                   │                                   │
│  ┌────────────────▼───────────────────────┐          │
│  │           中间件层 (Middleware)          │          │
│  │  • 请求限速 (Rate Limiter)              │          │
│  │  • Cookie 池 (Cookie Pool)             │          │
│  │  • 代理池 (Proxy Pool)                 │          │
│  │  • 重试 & 退避 (Retry & Backoff)       │          │
│  │  • 验证码处理 (Captcha Handler)        │          │
│  └────────────────┬───────────────────────┘          │
└───────────────────┼───────────────────────────────────┘
                    │
┌───────────────────▼───────────────────────────────────┐
│              数据处理层 (Data Pipeline)                │
│                                                       │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐         │
│  │ 原始数据  │──▶│  清洗    │──▶│  入库    │         │
│  │ (JSON)   │   │ (dedup)  │   │ (SQLite  │         │
│  │          │   │ (parse)  │   │  / PG)   │         │
│  └──────────┘   └──────────┘   └──────────┘         │
└───────────────────────────────────────────────────────┘
```

### 2.2 技术选型

| 组件 | 选型 | 理由 |
|------|------|------|
| 浏览器自动化 | **Playwright (Python)** | 比 Selenium 快，原生支持 CDP，多浏览器上下文 |
| 请求库 | **httpx** + **curl_cffi** | httpx 做异步请求，curl_cffi 模拟 Chrome TLS 指纹 |
| 任务调度 | **APScheduler** | 轻量级，Python 原生，够用 |
| 代理管理 | 自建代理池 + 付费住宅代理 | 比公开免费代理稳定 |
| 数据存储 | SQLite（当前）→ PostgreSQL（后期） | 渐进式升级 |
| 任务队列 | Celery + Redis（后期） | 量大后引入 |
| 监控告警 | 日志 + 企业微信/钉钉通知 | 采集异常时及时感知 |

### 2.3 核心依赖

```txt
# requirements-scraping.txt
playwright>=1.40.0
httpx>=0.25.0
curl_cffi>=0.6.0
apscheduler>=3.10.0
loguru>=0.7.0
pydantic>=2.0.0
lxml>=4.9.0
parsel>=1.8.0
```

---

## 三、反爬对抗策略（分平台）

### 3.1 BOSS直聘 专项策略

**最难的平台，优先级最高、投入最大。**

| 层面 | 策略 | 详细说明 |
|------|------|----------|
| **账号** | 5-10 个手机号注册的账号 | 轮换使用，每个账号每日搜索 ≤20 次 |
| **IP** | 住宅代理 IP 池（国内） | 每个 IP 每日请求 ≤ 50 次，成本约 40-80 元/GB |
| **浏览器指纹** | Playwright Context 随机化 | 随机 UA、视口大小、时区、语言、WebGL 指纹 |
| **行为模拟** | 人类化操作 | 搜索前先浏览首页 → 随机停留 → 缓慢输入关键词 → 随机滚动 |
| **Cookie 持久化** | 登录后保存 `storage_state` | `browser_context.storage_state(path="state_boss.json")` |
| **验证码** | 手动 + 打码平台双通道 | 触发验证码时暂停当前任务，推送通知人工处理或调用超级鹰 |
| **接口解密** | 逆向 `zp_token` 生成逻辑 | 从 JS 中提取加密函数，或用 Playwright 拦截真实请求获取响应 |
| **限速** | 搜索间隔 30-60 秒随机 | 翻页间隔 15-30 秒，模拟真人浏览速度 |
| **设备指纹** | `__zp_stoken__` 模拟 | 需逆向 Webpack 打包的 JS 模块 |

**BOSS直聘数据流：**

```
启动浏览器 → 加载持久化的登录态 →
访问首页（模拟自然人）→ 随机浏览推荐岗位 →
输入搜索关键词（成都 + 技术岗）→ 等待结果 →
解析搜索结果列表（每页 15 条）→ 随机间隔翻页 →
逐个打开岗位详情 → 提取结构化字段 →
最大 10 页 / 关键词，约 150 条/关键词 →
切换关键词 → 重复
```

### 3.2 前程无忧 专项策略

| 层面 | 策略 |
|------|------|
| **账号** | 3-5 个账号，部分搜索可免登录 |
| **IP** | 住宅代理，频率可稍高 |
| **sign 签名** | 逆向 `search.51job.com` 的 JS 签名逻辑，或直接用 Playwright 拦截 |
| **接口** | `https://search.51job.com/list/000000,000000,0000,00,9,99,{keyword},2,{page}.html` |
| **翻页** | 最多 100 页，建议取前 60 页 |

### 3.3 通用反爬层

```python
# 伪代码：反爬中间件示意
class AntiDetectionMiddleware:
    """统一反反爬层"""
    
    # 1. 请求头随机化
    # 2. 浏览器指纹随机化（每 N 个请求切换 context）
    # 3. 人类行为延迟（随机正态分布间隔）
    # 4. 代理 IP 自动切换（连续失败 3 次换 IP）
    # 5. Cookie 池轮换
    # 6. 验证码检测 → 暂停 → 通知人工
    # 7. 请求失败自动重试（指数退避，最多 3 次）
    # 8. 日志记录每次请求的 IP、Cookie、耗时、结果
```

---

## 四、数据采集流水线

### 4.1 采集参数

| 维度 | 取值 |
|------|------|
| 目标城市 | 成都（第一阶段）、后续扩展到北上广深杭 |
| 关键词 | Python、Java、前端、数据分析、测试、运维、产品经理、UI 设计、运营、销售 |
| 采集频率 | 每日增量（每天新增岗位），每周全量刷新 |
| 单平台量级 | 目标 500-2000 条/天 |
| 多平台总量 | 目标 2000-5000 条/天 |

### 4.2 提取字段（与现有数据结构对齐）

| 字段 | 来源方式 | 说明 |
|------|----------|------|
| `source_job_id` | 平台原始 ID | 去重主键 |
| `title` | 页面解析 | 岗位名称 |
| `company_name` | 页面解析 | 公司名称 |
| `salary_text` | 页面解析 | 原始薪资文本 |
| `city` | 搜索参数 / 解析 | 城市 |
| `district` | 页面解析 | 行政区 |
| `experience` | 页面解析 | 经验要求 |
| `education` | 页面解析 | 学历要求 |
| `industry` | 页面解析 | 行业 |
| `company_size` | 详情页解析 | 公司规模 |
| `financing_stage` | 详情页解析 | 融资阶段 |
| `skills` | 描述 NLP 提取 | 技能标签 |
| `description` | 详情页解析 | 岗位描述 |
| `source` | 硬编码 | 如 "bosszhipin" |
| `source_url` | 拼接 | 岗位原始链接 |
| `publish_time` | 页面解析 | 发布时间 |
| `crawl_time` | 系统时间 | 采集时间戳 |

### 4.3 存储策略

```
data/
├── raw/                          # 原始采集数据（JSON）
│   ├── 2026-06-04/
│   │   ├── bosszhipin_001.json
│   │   ├── job51_001.json
│   │   └── ...
│   └── ...
├── processed/                    # 清洗后 CSV
│   └── chengdu_jobs_20260604.csv
└── db/
    └── jobs.db                   # SQLite 数据库
```

---

## 五、实施计划（分阶段）

### 阶段 0：基础设施准备（1-2 天）

- [ ] 购买国内住宅代理服务（推荐：芝麻代理、快代理、豌豆代理）
- [ ] 准备 5-10 个手机号注册 BOSS直聘/前程无忧 账号
- [ ] 手动登录每个账号，保存 `storage_state`（Playwright Cookie 持久化）
- [ ] 搭建项目目录结构

### 阶段 1：前程无忧先行（3-5 天）

> 先攻克反爬最弱的平台，尽快拿到第一批真实数据。

- [ ] 实现搜索页 HTML 解析（免登录模式）
- [ ] 实现详情页解析 + 字段提取
- [ ] 对接代理池 + 请求限速
- [ ] 搜索 `sign` 签名逆向（或用 Playwright 绕过）
- [ ] 数据去重 + CSV 导出
- [ ] 跑通成都地区 10 个关键词的首次采集

### 阶段 2：BOSS直聘攻坚（7-10 天）

> 最复杂的平台，需要耐心调试。

- [ ] 实现 Cookie 持久化登录
- [ ] 破解 `zp_token` / `__zp_stoken__` 加密（或 Playwright 拦截方案）
- [ ] 实现搜索列表 + 详情页解析
- [ ] 验证码检测与通知机制
- [ ] 账号轮换 + 限速策略
- [ ] 跑通首次采集

### 阶段 3：拉勾 / 智联补充（3-5 天）

- [ ] 复制采集框架，适配平台差异
- [ ] 实现登录 + Cookie 持久化
- [ ] 合并多平台数据去重

### 阶段 4：自动化 & 扩展（3-5 天）

- [ ] APScheduler 定时任务（每日凌晨增量）
- [ ] 日志 + 异常监控
- [ ] 扩展到更多城市
- [ ] 数据质量检查（去重率、缺失率、解析成功率）

---

## 六、成本估算

| 项目 | 月成本（估算） | 说明 |
|------|:---:|------|
| 住宅代理 IP | 200-500 元 | 按流量计费，日均 10-20MB |
| 打码平台（超级鹰等） | 50-100 元 | 按次计费，1 分/次，日均 100-500 次 |
| 手机号（接码平台） | 50-100 元 | 注册账号用，一次性成本 |
| 服务器（可选） | 100-200 元 | 如果不在本地跑，云服务器 |
| **合计** | **400-900 元/月** | 初始月可能更高 |

---

## 七、风险与合规

### 7.1 法律风险

| 风险 | 等级 | 应对 |
|------|:---:|------|
| 违反平台 ToS | 🔴 高 | 仅用于个人学习研究，不公开分发数据 |
| 侵犯著作权 | 🟡 中 | 岗位描述属于平台内容，不可原样公开 |
| 个人信息保护 | 🟡 中 | 不采集个人联系方式，不存储姓名等 PII |
| 计算机系统安全 | 🔴 高 | 不发起 DDoS，严格限速，不绕过付费墙 |

### 7.2 技术风险

- **账号被封**：准备备用账号，分散采集量
- **加密参数更新**：BOSS 的 `zp_token` 可能随版本变更，需持续维护
- **验证码升级**：极验/易盾会升级，打码平台可能跟不上
- **IP 被封**：代理 IP 质量参差不齐，需要备用供应商

---

## 八、代码框架设计

### 8.1 目录结构

```
job-market-analytics/
├── app.py                          # Streamlit 仪表盘（已有）
├── requirements.txt
├── requirements-scraping.txt       # 爬虫依赖
├── src/
│   ├── analytics.py                # 分析模块（已有）
│   ├── cleaning.py                 # 清洗模块（已有）
│   ├── database.py                 # 数据库（已有）
│   ├── sample_data.py              # 假数据生成（已有，保留用于测试）
│   └── skill_dict.py              # 技能词典（已有）
├── spiders/                        # 新增：爬虫模块
│   ├── __init__.py
│   ├── base.py                     # 基类：反反爬中间件、限速、重试
│   ├── boss.py                     # BOSS直聘爬虫
│   ├── job51.py                    # 前程无忧爬虫
│   ├── lagou.py                    # 拉勾网爬虫
│   ├── middleware.py               # 中间件：代理池、Cookie池、验证码
│   └── pipeline.py                 # 数据管道：清洗 → 去重 → 入库
├── scripts/
│   ├── build_database.py           # 已有
│   ├── generate_sample_data.py     # 已有
│   └── run_spider.py               # 新增：爬虫入口脚本
├── config/
│   ├── proxy.yaml                  # 代理配置
│   └── accounts.yaml               # 账号配置（gitignore）
├── data/
│   ├── raw/                        # 原始采集数据
│   ├── processed/                  # 清洗后数据
│   ├── cookies/                    # 持久化的 Cookie（gitignore）
│   └── db/                         # SQLite 数据库
├── logs/                           # 采集日志（gitignore）
└── docs/
    └── scraping-plan.md            # 本文档
```

### 8.2 爬虫基类设计

```python
# spiders/base.py 核心结构
from playwright.async_api import async_playwright, BrowserContext
from typing import Optional
import random
import asyncio
from loguru import logger

class BaseSpider:
    """爬虫基类，封装通用反反爬逻辑"""
    
    def __init__(self, name: str, proxy_pool, cookie_pool):
        self.name = name
        self.proxy_pool = proxy_pool      # 代理池
        self.cookie_pool = cookie_pool     # Cookie 池
        self.rate_limiter = RateLimiter()  # 限速器
    
    async def create_context(self) -> BrowserContext:
        """创建随机指纹的浏览器上下文"""
        # 随机 UA、视口、时区、语言、WebGL
        ...
    
    async def human_delay(self, base_seconds: float):
        """人类化随机延迟（正态分布）"""
        delay = abs(random.gauss(base_seconds, base_seconds * 0.3))
        await asyncio.sleep(delay)
    
    async def safe_request(self, url: str, ...):
        """带重试、限速、代理切换的安全请求"""
        for attempt in range(3):
            try:
                await self.rate_limiter.wait()
                response = await self.page.goto(url, ...)
                if self._is_blocked(response):
                    await self._rotate_proxy()
                    continue
                return response
            except Exception as e:
                logger.warning(f"Attempt {attempt+1} failed: {e}")
                await asyncio.sleep(2 ** attempt * 10)
        raise Exception(f"All retries failed for {url}")
    
    def _is_blocked(self, response) -> bool:
        """检测是否被反爬拦截"""
        # 403、验证码页面、空结果等
        ...
```

### 8.3 采集入口脚本

```python
# scripts/run_spider.py
"""
采集入口：支持单次采集和定时调度

用法:
  python scripts/run_spider.py --platform boss --city 成都
  python scripts/run_spider.py --platform all --city 成都 --mode daily
"""

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", choices=["boss", "job51", "lagou", "all"])
    parser.add_argument("--city", default="成都")
    parser.add_argument("--keywords", nargs="+", default=KEYWORD_LIST)
    parser.add_argument("--mode", choices=["once", "daily"], default="once")
    args = parser.parse_args()
    
    # 初始化代理池和 Cookie 池
    proxy_pool = ProxyPool.from_config("config/proxy.yaml")
    cookie_pool = CookiePool("data/cookies/")
    
    # 选择爬虫
    if args.platform in ("boss", "all"):
        spider = BossSpider(proxy_pool, cookie_pool)
        await spider.run(args.city, args.keywords)
    
    # 清洗 + 入库
    pipeline = DataPipeline()
    pipeline.process_raw_to_db()
```

---

## 九、里程碑 & 时间线

```
Week 1: 基础设施 + 前程无忧 MVP 跑通
  ├── Day 1-2: 代理、账号、Cookie 准备
  ├── Day 3-4: job51 爬虫开发
  └── Day 5:   首次采集跑通，拿到第一批真实数据

Week 2: BOSS直聘攻坚
  ├── Day 1-3: 加密参数逆向 / Playwright 拦截方案
  ├── Day 4-5: 搜索+详情解析
  └── Day 6-7: 验证码处理 + 联调

Week 3: 扩展 & 自动化
  ├── Day 1-2: 拉勾网适配
  ├── Day 3-4: 定时调度 + 监控
  └── Day 5:   多城市扩展 + 数据质量 review

总计：约 3 周（全职投入），业余时间约 4-6 周
```

---

## 十、注意事项

1. **不要贪快**：初期以稳定、低频率为主，拿不到 5000 条就先拿 500 条，慢慢调优
2. **日志很重要**：每次请求的 IP、Cookie、耗时、结果都记录下来，排查问题全靠日志
3. **先跑通一个平台**：不要同时开发多个，前程无忧是入门首选
4. **Cookie 会过期**：每隔 1-2 天需要重新手动登录刷新，考虑写一个健康检查脚本
5. **不要 7×24 高频采集**：控制在合理频率，避免 IP/账号被永久封禁
6. **验证码是最大变数**：如果打码平台覆盖不了，只能人工过，这会极大影响采集效率
7. **接口会变**：招聘平台的前端迭代频繁，解析逻辑需要持续维护，关注 diff
