#!/usr/bin/env python3
"""智联招聘 成都深度采集 - DOM提取方案

特点：
- URL 直接导航（每关键词新页面），无需 Vue 状态注入
- 按地点字段后筛选（".jobinfo__other-info-item[0]" 包含"成都"）
- 每页 20 条，支持多页翻页（URL /p1, /p2, /p3...）

用法:
    python3 scripts/collect_chengdu_zhaopin.py
    python3 scripts/collect_chengdu_zhaopin.py --pages 5
"""
import json, os, random, re, subprocess, sys, time
from pathlib import Path

# ── 配置 ──
XB_CJS = os.path.expanduser(
    "~/Library/Application Support/QClaw/openclaw/config/skills/xbrowser/scripts/xb.cjs"
)
NODE = os.environ.get("QCLAW_CLI_NODE_BINARY", "node")
PROJECT = Path("/Users/yangyuxiao/codes/job-market-analytics")
RAW_DIR = PROJECT / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

CITY_NAME = "成都"
# 智联城市码（jl489=四川，后筛选成都）
ZL_CITY_CODE = "489"

# 关键词：与 51job 一致
KEYWORDS = [
    "Python", "Java", "前端", "测试", "运维", "产品经理",
    "数据分析", "AI算法", "嵌入式", "销售", "Go", "C++",
    "项目经理", "UI设计", "运营", "HR", "市场", "财务",
    "网络安全", "区块链",
]
PAGES_PER_KW = 3
PAGE_WAIT_MS = 4000   # 等 DOM 刷新
KW_SLEEP_MIN = 3
KW_SLEEP_MAX = 6

OUTFILE = RAW_DIR / f"zhaopin_{CITY_NAME}_v1.jsonl"


# ── xbrowser 操作 ──
def xb_cmd(*args, timeout=30):
    r = subprocess.run(
        [NODE, XB_CJS, "run", "--browser", "default", "--timeout", str(timeout)] + list(args),
        capture_output=True, text=True, timeout=timeout + 15
    )
    return r.stdout

def xb_stop():
    subprocess.run([NODE, XB_CJS, "run", "--browser", "default", "--timeout", "5", "stop"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)

def xb_open(url, timeout=25):
    xb_cmd("open", url, timeout=timeout)

def xb_eval_raw(js, timeout=30):
    out = xb_cmd("eval", js, timeout=timeout)
    idx = out.find('{')
    if idx == -1:
        return {'_err': 'no_json', '_raw': out[:200]}
    try:
        d = json.loads(out[idx:])
    except json.JSONDecodeError:
        return {'_err': 'bad_json', '_raw': out[idx:idx+200]}
    if not d.get('ok'):
        return {'_err': d.get('data', {}).get('result', {}).get('error', 'xb_error')}
    return d


def search_kw(kw):
    """打开关键词搜索页，返回是否成功。"""
    url = f"https://www.zhaopin.com/sou/?kw={kw}&city={ZL_CITY_CODE}"
    xb_open(url, timeout=25)
    time.sleep(PAGE_WAIT_MS / 1000)
    return True


def goto_page(page_num):
    """翻页：点击下一页或直接导航。"""
    js = f"""
    (() => {{
      const next = document.querySelector('.soupager__btn--next');
      if (next && !next.classList.contains('soupager__btn--disabled')) {{
        next.click();
        return JSON.stringify({{clicked: true}});
      }}
      // fallback: navigate
      const url = new URL(location.href);
      url.pathname = url.pathname.replace(/\\/p\\d+$/, '/p{page_num}');
      location.href = url.toString();
      return JSON.stringify({{navigated: true}});
    }})()"""
    r = xb_eval_raw(js, timeout=15)
    time.sleep(PAGE_WAIT_MS / 1000)
    return r.get("ok") == 1


def extract_page(city_filter="成都"):
    """从当前 DOM 提取职位卡片，按城市筛选。"""
    js = f"""
    (() => {{
      const items = document.querySelectorAll('.joblist-box__item');
      const out = [];
      items.forEach(el => {{
        const titleEl = el.querySelector('.jobinfo__name a, .jobinfo__name');
        const salaryEl = el.querySelector('.jobinfo__salary');
        const compEl = el.querySelector('.company__name');
        const descItems = el.querySelectorAll('.jobinfo__other-info-item');
        const tags = el.querySelectorAll('.jobinfo__tag');
        const compTags = el.querySelectorAll('.company__tag');

        const location = descItems[0]?.textContent?.trim() || '';
        const experience = descItems[1]?.textContent?.trim() || '';
        const education = descItems[2]?.textContent?.trim() || '';

        const tagTexts = Array.from(tags).map(t => t.textContent.trim().replace(/\\s+/g, ' '));
        const compTagTexts = Array.from(compTags).map(t => t.textContent.trim().replace(/\\s+/g, ' '));

        // 公司名：取第一行
        const compFull = compEl?.textContent?.trim() || '';
        const compLines = compFull.split('\\n').map(s => s.trim()).filter(Boolean);
        const company = compLines[0] || '';

        out.push({{
          title: titleEl?.textContent?.trim() || '',
          salary: salaryEl?.textContent?.trim() || '',
          location: location,
          experience: experience,
          education: education,
          company: company,
          compTags: compTagTexts,
          skills: tagTexts,
          link: titleEl?.href || '',
        }});
      }});

      // 过滤城市
      const filtered = out.filter(j => j.location.includes('{city_filter}'));
      return JSON.stringify({{total: out.length, filtered: filtered.length, items: filtered}});
    }})()"""
    r = xb_eval_raw(js)
    if not r.get("ok"):
        return [], r.get("_err", "unknown")
    data = r.get("data", {}).get("result", {}).get("data", {}).get("result", "")
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except:
            return [], "parse_error"
    return data.get("items", []), None


# ── 主流程 ──
def main():
    pages = PAGES_PER_KW

    for a in sys.argv[1:]:
        if a.startswith("--pages="):
            pages = int(a.split("=")[1])

    print(f"\n🚀 智联招聘 {CITY_NAME}采集 (URL导航方案)")
    print(f"📋 关键词: {len(KEYWORDS)} 个")
    print(f"📄 每词 {pages} 页 × 20 条（过滤前）")
    print(f"📁 输出: {OUTFILE}")
    print()

    # 启动浏览器
    print("🔄 启动浏览器...")
    xb_stop()
    time.sleep(2)

    # 先打开首页预热
    xb_open(f"https://www.zhaopin.com/sou/?kw=Python&city={ZL_CITY_CODE}", timeout=30)
    time.sleep(6)

    total_jobs = 0
    total_raw = 0

    for kw_idx, kw in enumerate(KEYWORDS):
        print(f"\n[{kw_idx+1}/{len(KEYWORDS)}] {kw}:", end="", flush=True)

        # 搜索关键词
        if kw_idx > 0:
            search_kw(kw)
            time.sleep(2)

        kw_jobs = 0
        kw_raw = 0

        for p in range(1, pages + 1):
            if p > 1:
                if not goto_page(p):
                    print(f" p{p}=⛔", end="", flush=True)
                    break

            items, err = extract_page("成都")
            if err:
                print(f" p{p}={err}", end="", flush=True)
                break

            cnt = len(items)
            kw_raw += 20  # each page has 20 items before filtering

            if cnt == 0:
                print(f" p{p}=0", end="", flush=True)
                # Continue to next page even if 0 on this one
                continue

            print(f" p{p}={cnt}", end="", flush=True)

            with open(OUTFILE, 'a', encoding='utf-8') as f:
                for item in items:
                    item['_keyword'] = kw
                    item['_city'] = CITY_NAME
                    item['_source'] = 'zhaopin'
                    f.write(json.dumps(item, ensure_ascii=False) + '\n')

            kw_jobs += cnt

            if p < pages:
                s = random.uniform(1.5, 3)
                time.sleep(s)

        total_jobs += kw_jobs
        total_raw += kw_raw
        print(f" → {kw_jobs}条(共{kw_raw}条raw)", flush=True)

        if kw_idx < len(KEYWORDS) - 1:
            s = random.uniform(KW_SLEEP_MIN, KW_SLEEP_MAX)
            print(f"  💤 {s:.1f}s...", flush=True)
            time.sleep(s)

    print(f"\n{'='*50}")
    print(f"✅ 完成！总计: {total_jobs} 条（{total_raw} 条原始）")
    print(f"📁 → {OUTFILE}")
    print(f"{'='*50}")
    return total_jobs


if __name__ == "__main__":
    main()