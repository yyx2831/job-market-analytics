#!/usr/bin/env python3
"""
Boss直聘 移动端 API 采集器。

通过移动端 API 采集岗位数据，处理常见的反爬机制。

限制:
- Boss直聘使用强大的 WAF (Web Application Firewall) 保护
- 移动端 API 需要有效的 zp_stoken / __zp_stoken__ cookie
- 频繁请求会触发 IP 封禁和验证码
- API 有签名校验机制 (zpAppId + 时间戳签名)

如果 WAF 无法突破，记录原因并跳过。

用法:
  python3 scripts/collect_boss.py --city 成都 --keyword Python后端 --pages 5
"""

from __future__ import annotations

import argparse
import json
import random
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# Boss直聘城市代码映射
BOS_CITY_CODE = {
    "成都": "101270100",
    "北京": "101010100",
    "上海": "101020100",
    "深圳": "101280600",
    "广州": "101280100",
    "杭州": "101210100",
    "武汉": "101200100",
    "西安": "101110100",
    "南京": "101190100",
    "重庆": "101040100",
}

# Boss API 端点
BOS_SEARCH_API = "https://www.zhipin.com/wapi/zpgeek/search/joblist.json"

# 请求头模拟移动端
MOBILE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148",
    "Accept": "application/json",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Origin": "https://www.zhipin.com",
    "Referer": "https://www.zhipin.com/",
    "zpAppId": "1",
}


def collect_boss(
    city: str = "成都",
    keyword: str = "Python后端",
    pages: int = 5,
    min_delay: float = 2.0,
    max_delay: float = 5.0,
) -> list[dict]:
    """尝试通过 Boss 直聘移动端 API 采集岗位数据。

    已知反爬机制：
    1. Cookie 校验: 需要 __zp_stoken__ + __c / __g 等 cookie
    2. 签名校验: 部分接口需要签名 (zpSign)
    3. IP 频率限制: 超过阈值触发验证码或直接返回空数据
    4. UA 检测: 非移动端 UA 返回降级页面
    5. Headers 校验: 缺少 Referer/Origin 直接拒绝

    返回: [(成功/失败原因, 岗位数据list)]
    """
    city_code = BOS_CITY_CODE.get(city)
    if not city_code:
        return [{"error": f"不支持的城市: {city}"}]

    results = []
    session = requests.Session()
    session.headers.update(MOBILE_HEADERS)

    for page in range(1, pages + 1):
        params = {
            "query": keyword,
            "city": city_code,
            "page": page,
            "pageSize": 20,
        }

        try:
            resp = session.get(
                BOS_SEARCH_API,
                params=params,
                timeout=15,
            )

            print(f"  📄 第 {page}/{pages} 页 | 状态码: {resp.status_code} | 大小: {len(resp.text)} bytes")

            if resp.status_code == 200:
                try:
                    data = resp.json()
                except json.JSONDecodeError:
                    # 返回了 HTML → WAF 拦截
                    if "<html" in resp.text[:100].lower():
                        print(f"    ⚠️  WAF 拦截 — 返回 HTML 而非 JSON")
                        results.append({"error": "WAF拦截", "page": page, "raw_preview": resp.text[:200]})
                    else:
                        print(f"    ⚠️  非 JSON 响应")
                        results.append({"error": "非JSON响应", "page": page})
                    continue

                # 检查 zpduck API 结构
                zp_data = data.get("zpData") or data
                job_list = zp_data.get("jobList") or []

                if not job_list:
                    code = data.get("code")
                    msg = data.get("message", "未知错误")
                    print(f"    ⚠️  空结果 | code={code} | message={msg}")
                    results.append({"error": f"空结果: {msg}", "page": page, "code": code})
                    continue

                for job in job_list:
                    results.append({
                        "source": "boss",
                        "source_job_id": str(job.get("encryptId", job.get("jobId", ""))),
                        "title": job.get("jobName", ""),
                        "company_name": job.get("brandName", "未知"),
                        "city": job.get("cityName", city),
                        "district": job.get("areaDistrict", ""),
                        "salary_text": job.get("salaryDesc", ""),
                        "experience": job.get("jobExperience", ""),
                        "education": job.get("jobDegree", ""),
                        "industry": job.get("brandIndustry", ""),
                        "company_size": f"{job.get('brandScaleName', '')}",
                        "financing_stage": job.get("brandStageName", ""),
                        "skills": ",".join(job.get("skills", []) or []),
                        "description": job.get("jobLabels", ""),
                        "source_url": f"https://www.zhipin.com/job_detail/{job.get('encryptId', '')}.html",
                    })

                print(f"    ✅ 采集 {len(job_list)} 条")
                time.sleep(random.uniform(min_delay, max_delay))

            elif resp.status_code == 403:
                print(f"    🚫 403 Forbidden — IP 被封或需要验证")
                results.append({"error": "403 Forbidden", "page": page})
                break
            elif resp.status_code == 302 or resp.status_code == 301:
                print(f"    🔀 重定向 — 可能需要登录")
                results.append({"error": "重定向到登录页", "page": page})
                break
            else:
                print(f"    ❓ 未知状态: {resp.status_code}")
                results.append({"error": f"HTTP {resp.status_code}", "page": page})

        except requests.Timeout:
            print(f"    ⏱️ 请求超时")
            results.append({"error": "超时", "page": page})
        except requests.ConnectionError:
            print(f"    🔌 连接失败")
            results.append({"error": "连接失败", "page": page})
        except Exception as e:
            print(f"    ❌ 异常: {e}")
            results.append({"error": str(e), "page": page})

    return results


def main():
    parser = argparse.ArgumentParser(description="Boss直聘采集器")
    parser.add_argument("--city", default="成都", help="目标城市")
    parser.add_argument("--keyword", default="Python后端", help="搜索关键词")
    parser.add_argument("--pages", type=int, default=5, help="采集页数")
    parser.add_argument("--output", "-o", help="输出 JSON 文件路径")
    args = parser.parse_args()

    print(f"🔍 Boss直聘: {args.city} · {args.keyword} · {args.pages} 页")
    print("=" * 60)

    results = collect_boss(
        city=args.city,
        keyword=args.keyword,
        pages=args.pages,
    )

    # 分离成功和失败
    errors = [r for r in results if "error" in r]
    jobs = [r for r in results if "error" not in r]

    print(f"\n{'='*60}")
    print(f"📊 采集完成: 成功 {len(jobs)} 条, 错误 {len(errors)} 条")

    if errors:
        unique_errors = set(e["error"] for e in errors)
        print(f"🚫 失败原因: {', '.join(unique_errors)}")

    if args.output:
        out_path = Path(args.output)
        out_path.write_text(json.dumps(jobs, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"💾 已保存: {out_path}")
    elif jobs:
        print(json.dumps(jobs[:3], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
