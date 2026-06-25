#!/usr/bin/env python3
"""
拉勾/猎聘 移动端 API 采集器。

拉勾 API:
  https://www.lagou.com/wn/jobs?city={city}&kd={keyword}&pn={page}

猎聘 API:
  更加严格的登录要求和签名校验

限制:
- 拉勾2025年后 API 加强了反爬保护
- 猎聘需要登录态 (token/cookie) 才能访问职位列表
- 多次请求触发验证码和 IP 封禁
- 猎聘使用极验/腾讯验证码

如果 WAF 无法突破，记录原因并跳过。

用法:
  python3 scripts/collect_lagou.py --city 成都 --keyword Python --pages 5
  python3 scripts/collect_lagou.py --source liepin --city 成都 --keyword Python
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# 拉勾移动端 API
LAGOU_API = "https://www.lagou.com/wn/jobs"

# 猎聘搜索 API (需要登录态)
LIEPIN_API = "https://www.liepin.com/zhaopin/"

# 模拟移动端请求头
MOBILE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://m.lagou.com/",
    "X-Requested-With": "XMLHttpRequest",
}


def collect_lagou(
    city: str = "成都",
    keyword: str = "Python",
    pages: int = 5,
    min_delay: float = 2.0,
    max_delay: float = 5.0,
) -> list[dict]:
    """尝试通过拉勾移动端 API 采集岗位数据。

    已知反爬机制：
    1. Cookie 校验: 需要 X_HTTP_TOKEN + user_trace_token
    2. 频率限制: 短时间内多次请求返回空结果
    3. UA 检测: 非移动端 UA 拒绝访问
    4. Referer 校验: 需要来自 lagou.com 的 Referer

    返回: list[dict]
    """
    results = []
    session = requests.Session()
    session.headers.update(MOBILE_HEADERS)

    # 先访问首页获取 cookie
    try:
        home_resp = session.get("https://m.lagou.com/", timeout=15)
        print(f"  🏠 首页: {home_resp.status_code}")
    except Exception as e:
        print(f"  ⚠️  首页访问失败: {e}")

    for page in range(1, pages + 1):
        params = {
            "city": city,
            "kd": keyword,
            "pn": page,
            "needAddtionalResult": "false",
        }

        try:
            resp = session.get(
                LAGOU_API,
                params=params,
                timeout=15,
                headers={
                    **MOBILE_HEADERS,
                    "Referer": f"https://m.lagou.com/search.html?city={city}&kd={keyword}",
                },
            )

            print(f"  📄 第 {page}/{pages} 页 | 状态码: {resp.status_code} | 大小: {len(resp.text)} bytes")

            if resp.status_code == 200:
                try:
                    data = resp.json()
                except json.JSONDecodeError:
                    if "<html" in resp.text[:100].lower():
                        print(f"    ⚠️  WAF 拦截 — 返回 HTML，需要更高级的反反爬策略")
                        results.append({"error": "WAF拦截-HTML", "page": page})
                    else:
                        print(f"    ⚠️  非 JSON 响应: {resp.text[:100]}")
                        results.append({"error": "非JSON响应", "page": page})
                    continue

                # 拉勾 API 响应结构
                # content.data.page.result[] 或直接 result
                content = data.get("content") or data
                job_items = []
                if isinstance(content, dict):
                    data_block = content.get("data") or content
                    if isinstance(data_block, dict):
                        page_info = data_block.get("page") or data_block
                        if isinstance(page_info, dict):
                            job_items = page_info.get("result", [])
                        elif isinstance(page_info, list):
                            job_items = page_info
                    else:
                        job_items = data_block if isinstance(data_block, list) else []

                if isinstance(content, list):
                    job_items = content

                if not job_items:
                    code = data.get("code")
                    msg = data.get("message", "未知错误")
                    print(f"    ⚠️  空结果 | code={code} | msg={msg}")
                    results.append({"error": f"空结果: {msg}", "page": page, "code": code})
                    continue

                for job in job_items:
                    results.append({
                        "source": "lagou",
                        "source_job_id": str(job.get("positionId", job.get("id", ""))),
                        "title": job.get("positionName", job.get("title", "")),
                        "company_name": job.get("companyFullName", job.get("company", "未知")),
                        "city": job.get("city", city),
                        "district": job.get("district", ""),
                        "salary_text": job.get("salary", ""),
                        "experience": job.get("workYear", ""),
                        "education": job.get("education", ""),
                        "industry": job.get("industryField", ""),
                        "company_size": job.get("companySize", ""),
                        "financing_stage": job.get("financeStage", ""),
                        "skills": ",".join(job.get("skillLables", []) or []),
                        "description": job.get("positionAdvantage", ""),
                        "source_url": f"https://www.lagou.com/jobs/{job.get('positionId', '')}.html",
                    })

                print(f"    ✅ 采集 {len(job_items)} 条")
                time.sleep(random.uniform(min_delay, max_delay))

            elif resp.status_code == 403:
                print(f"    🚫 403 Forbidden")
                results.append({"error": "403 Forbidden", "page": page})
                break
            elif resp.status_code == 302:
                print(f"    🔀 重定向 — 需要登录")
                results.append({"error": "需要登录", "page": page})
                break
            else:
                print(f"    ❓ HTTP {resp.status_code}")
                results.append({"error": f"HTTP {resp.status_code}", "page": page})

        except requests.Timeout:
            print(f"    ⏱️ 超时")
            results.append({"error": "超时", "page": page})
        except requests.ConnectionError:
            print(f"    🔌 连接失败")
            results.append({"error": "连接失败", "page": page})
        except Exception as e:
            print(f"    ❌ 异常: {e}")
            results.append({"error": str(e), "page": page})

    return results


def collect_liepin(
    city: str = "成都",
    keyword: str = "Python",
    pages: int = 5,
    min_delay: float = 3.0,
    max_delay: float = 6.0,
) -> list[dict]:
    """尝试猎聘采集（需要登录态，大概率被拦截）。

    猎聘反爬特点：
    - 必须登录（需要有效的 JWT token）
    - 使用极验/腾讯滑块验证码
    - API 返回加密数据或 HTML 影子 DOM
    - 请求频率限制极严
    """
    results = []
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "application/json",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": "https://www.liepin.com/",
    })

    for page in range(1, pages + 1):
        try:
            params = {
                "key": keyword,
                "dqs": city,
                "curPage": page,
                "pageSize": 20,
            }
            resp = session.get(
                "https://www.liepin.com/zhaopin/",
                params=params,
                timeout=15,
            )

            print(f"  📄 第 {page}/{pages} 页 | 状态码: {resp.status_code} | 大小: {len(resp.text)} bytes")

            if "请先登录" in resp.text or "login" in resp.text.lower()[:500]:
                print(f"    🔒 需要登录 — 猎聘强制登录才能查看岗位列表")
                results.append({"error": "需要登录", "page": page})
                break

            if resp.status_code == 200 and len(resp.text) < 500:
                print(f"    ⚠️  返回内容过短，可能是反爬页面")
                results.append({"error": "反爬拦截", "page": page, "raw": resp.text[:200]})
                continue

            if "验证" in resp.text or "verify" in resp.text.lower():
                print(f"    🛡️ 触发验证码")
                results.append({"error": "验证码拦截", "page": page})
                break

            results.append({"error": "HTML页面-需浏览器渲染", "page": page})
            break  # 猎聘大概率返回 HTML，继续请求无意义

        except Exception as e:
            print(f"    ❌ {e}")
            results.append({"error": str(e), "page": page})

    return results


def main():
    parser = argparse.ArgumentParser(description="拉勾/猎聘采集器")
    parser.add_argument("--source", choices=["lagou", "liepin", "all"], default="lagou", help="采集源")
    parser.add_argument("--city", default="成都", help="目标城市")
    parser.add_argument("--keyword", default="Python", help="搜索关键词")
    parser.add_argument("--pages", type=int, default=5, help="采集页数")
    parser.add_argument("--output", "-o", help="输出 JSON 路径")
    args = parser.parse_args()

    all_results = []

    if args.source in ("lagou", "all"):
        print(f"🔍 拉勾: {args.city} · {args.keyword}")
        print("=" * 60)
        lg_results = collect_lagou(
            city=args.city,
            keyword=args.keyword,
            pages=args.pages,
        )
        all_results.extend(lg_results)

        lg_jobs = [r for r in lg_results if "error" not in r]
        lg_errors = [r for r in lg_results if "error" in r]
        print(f"📊 拉勾: 成功 {len(lg_jobs)} 条, 错误 {len(lg_errors)} 条")
        if lg_errors:
            print(f"   错误类型: {set(e['error'] for e in lg_errors)}")

    if args.source in ("liepin", "all"):
        print(f"\n🔍 猎聘: {args.city} · {args.keyword}")
        print("=" * 60)
        lp_results = collect_liepin(
            city=args.city,
            keyword=args.keyword,
            pages=args.pages,
        )
        all_results.extend(lp_results)

        lp_jobs = [r for r in lp_results if "error" not in r]
        lp_errors = [r for r in lp_results if "error" in r]
        print(f"📊 猎聘: 成功 {len(lp_jobs)} 条, 错误 {len(lp_errors)} 条")

    jobs = [r for r in all_results if "error" not in r]

    if args.output and jobs:
        out_path = Path(args.output)
        out_path.write_text(json.dumps(jobs, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"💾 已保存 {len(jobs)} 条至: {out_path}")

    if not jobs:
        print("\n⚠️  未能采集到数据。Boss/拉勾/猎聘均使用了较强的反爬保护。")
        print("   建议方案:")
        print("   1. 使用 xbrowser skill 通过已登录浏览器采集")
        print("   2. 使用官方开放 API (如有)")
        print("   3. 购买第三方数据服务")
        print("   4. 当前以 51job 为主要数据源（已有 2866+552=3418 条）")


if __name__ == "__main__":
    main()
