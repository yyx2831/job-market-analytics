#!/usr/bin/env python3
"""51job 多城市DOM采集器 - V2稳定版

策略：
- URL直接跳转搜索页（jobArea参数切换城市）
- JS点击翻页 + DOM提取
- 增量upsert到SQLite
- 反爬：关键词间隔15-25s，翻页间隔6-10s，每3个城市reload

用法: python3 scripts/collect_multicity.py
"""

import json, os, random, re, subprocess, sys, time, sqlite3
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

# ── 路径配置 ──
XB_CJS = os.path.expanduser(
    "~/Library/Application Support/QClaw/openclaw/config/skills/xbrowser/scripts/xb.cjs"
)
NODE = os.environ.get("QCLAW_CLI_NODE_BINARY") or "/Applications/QClaw.app/Contents/Resources/node/node"
PROJECT = Path("/Users/yangyuxiao/codes/job-market-analytics")
RAW_DIR = PROJECT / "data" / "raw"
DB_PATH = PROJECT / "data" / "processed" / "jobs.db"
RAW_DIR.mkdir(parents=True, exist_ok=True)

# ── 采集参数 ──
BATCH_ID = datetime.now().strftime("batch_%Y%m%d_%H%M_multicity")

CITY_CODES = {
    "北京": "010000", "上海": "020000", "广州": "030200",
    "深圳": "040000", "杭州": "080200", "成都": "090200",
    "南京": "070200", "武汉": "180200", "西安": "200200",
    "重庆": "060000",
}

# 前端+IT通用关键词（覆盖你的求职方向）
KEYWORDS = [
    "前端开发", "React", "Vue", "TypeScript", "Web前端",
    "Node.js", "全栈", "小程序", "JavaScript", "Uni-app",
]

PAGES_PER_KW = 2
PAGE_WAIT = (6, 10)       # 翻页间隔
KW_SLEEP = (15, 25)       # 关键词间隔
RELOAD_EVERY_N_CITIES = 3

# 目标城市（5个一线对比 + 成都）
CITIES = ["北京", "上海", "广州", "深圳", "杭州", "成都"]

OUTFILE = RAW_DIR / f"job51_multicity_{BATCH_ID}.jsonl"


# ── 工具函数 ──
def xb_eval(js, timeout=20):
    """在浏览器执行JS并返回解析结果"""
    r = subprocess.run(
        [NODE, XB_CJS, "run", "--browser", "default", "--timeout", str(timeout), "eval", js],
        capture_output=True, text=True, timeout=timeout + 15
    )
    out = r.stdout
    try:
        idx = out.index("{")
        outer = json.loads(out[idx:])
        inner_str = outer["data"]["result"]["data"]["result"]
        return json.loads(inner_str)
    except (ValueError, json.JSONDecodeError, KeyError, TypeError) as e:
        return {"ok": 0, "err": f"parse_error: {e}", "raw": out[:200]}


def xb_open(url, timeout=30):
    """打开URL"""
    subprocess.run(
        [NODE, XB_CJS, "run", "--browser", "default", "--timeout", str(timeout), "open", url],
        capture_output=True, text=True, timeout=timeout + 15
    )


def reload_browser():
    """重新打开51job首页"""
    xb_open("https://we.51job.com/pc/search?keyword=Java&jobArea=090200&searchType=2", timeout=25)
    time.sleep(6)


def parse_salary(text):
    """薪资解析 - 处理多种格式"""
    if not text or not text.strip():
        return None, None
    text = text.strip()
    # 8千-1.1万
    m = re.match(r'(\d+\.?\d*)\s*千\s*-\s*(\d+\.?\d*)\s*万', text)
    if m: return int(float(m.group(1)) * 1000), int(float(m.group(2)) * 10000)
    # 8千-12千
    m = re.match(r'(\d+\.?\d*)\s*千\s*-\s*(\d+\.?\d*)\s*千', text)
    if m: return int(float(m.group(1)) * 1000), int(float(m.group(2)) * 1000)
    # 0.8-1.2万
    m = re.match(r'(\d+\.?\d*)\s*万\s*-\s*(\d+\.?\d*)\s*万', text)
    if m: return int(float(m.group(1)) * 10000), int(float(m.group(2)) * 10000)
    # 8-12万
    m = re.match(r'(\d+\.?\d*)\s*-\s*(\d+\.?\d*)\s*万', text)
    if m: return int(float(m.group(1)) * 10000), int(float(m.group(2)) * 10000)
    # 8-12千
    m = re.match(r'(\d+\.?\d*)\s*-\s*(\d+\.?\d*)\s*千', text)
    if m: return int(float(m.group(1)) * 1000), int(float(m.group(2)) * 1000)
    # 8-12K
    m = re.match(r'(\d+\.?\d*)\s*-\s*(\d+\.?\d*)\s*[Kk]', text)
    if m:
        a, b = float(m.group(1)), float(m.group(2))
        if a < 100: a *= 1000
        if b < 100: b *= 1000
        return int(a), int(b)
    # 8-12 (万为单位假定)
    m = re.match(r'(\d+\.?\d*)\s*-\s*(\d+\.?\d*)\s*元', text)
    if m:
        a, b = float(m.group(1)), float(m.group(2))
        if a < 100: a *= 1000; b *= 1000
        return int(a), int(b)
    # 裸数字
    m = re.match(r'(\d+\.?\d*)\s*-\s*(\d+\.?\d*)', text)
    if m:
        a, b = float(m.group(1)), float(m.group(2))
        if a < 100: a *= 1000; b *= 1000
        if a <= 5: a *= 10000; b *= 10000
        return int(a), int(b)
    return None, None


def search_city_kw(city, city_code, kw):
    """对一个城市的一个关键词执行搜索并提取"""
    url = f"https://we.51job.com/pc/search?keyword={quote(kw)}&jobArea={city_code}&searchType=2"
    xb_open(url, timeout=25)
    time.sleep(5)

    all_jobs = []
    for pg in range(1, PAGES_PER_KW + 1):
        if pg > 1:
            js = f"""(()=>{{
                var btns=document.querySelectorAll('.j_page .page_btn');
                var nxt=null;
                for(var i=0;i<btns.length;i++){{if(btns[i].textContent.trim()==='{pg}' && btns[i].tagName==='A')nxt=btns[i];}}
                if(nxt)nxt.click();else{{var a=document.querySelector('.j_page .page_next');if(a)a.click();}}
                return 'ok';
            }})()"""
            r = xb_eval(js, timeout=15)
            wt = random.uniform(*PAGE_WAIT)
            time.sleep(wt)

        # 提取岗位
        js = """(()=>{
        try{
        var cards=document.querySelectorAll('.joblist-item');
        var out=[];
        cards.forEach(function(c){
        var t=c.querySelector('.joblist-item-jobname');
        var sal=c.querySelector('.sal');
        var area=c.querySelector('.area');
        var co=c.querySelector('.cname');
        var info=c.querySelectorAll('.info .t');
        var link=c.querySelector('a');
        var tags=c.querySelectorAll('.tag');
        var tagList=[];tags.forEach(function(tg){tagList.push(tg.textContent.trim());});
        out.push({
        title:t?t.textContent.trim():'',
        salary:sal?sal.textContent.trim():'',
        district:area?area.textContent.trim():'',
        company:co?co.textContent.trim():'',
        info:[info[0]?info[0].textContent.trim():'',info[1]?info[1].textContent.trim():''],
        url:link?link.href:'',
        tags:tagList
        });
        });
        return JSON.stringify({ok:1,count:out.length,data:out});
        }catch(e){return JSON.stringify({err:e.message});}
        })()"""
        d = xb_eval(js, timeout=15)
        if not d.get('ok'):
            print(f"      ❌ 提取: {d.get('err', 'unknown')}")
            continue

        jobs = d.get('data', [])
        print(f"      📄 第{pg}页: {len(jobs)}条")
        for j in jobs:
            j['_city'] = city
            j['_city_code'] = city_code
            j['_keyword'] = kw
        all_jobs.extend(jobs)

        if len(jobs) < 15:
            break

    return all_jobs


def upsert_job(job, city, batch_id):
    """增量upsert"""
    title = job.get('title', '')
    company = job.get('company', '')
    district = job.get('district', '')
    salary = job.get('salary', '')
    url = job.get('url', '')
    info = job.get('info', [])
    exp = info[0] if len(info) > 0 else ''
    edu = info[1] if len(info) > 1 else ''

    # clean district
    if district and '·' in district:
        district = district.split('·', 1)[-1]

    dedupe_key = f"51job_multicity:{city}:{title}:{company}:{district}"
    sal_min, sal_max = parse_salary(salary)
    now = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')

    db = sqlite3.connect(str(DB_PATH))
    try:
        db.execute("""
            INSERT OR REPLACE INTO jobs
            (source, source_job_id, title, company_name, city, district,
             salary_text, salary_min, salary_max, experience, education,
             source_url, crawl_time, created_at, updated_at, dedupe_key,
             collection_batch, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        """, ("51job_multicity", "", title, company, city, district,
              salary, sal_min, sal_max, exp, edu, url,
              now, now, now, dedupe_key, batch_id))
        db.commit()
        return True
    except Exception as e:
        return False
    finally:
        db.close()


def main():
    print("=" * 60)
    print(f"🚀 51job 多城采集 V2")
    print(f"   批次: {BATCH_ID}")
    print(f"   城市: {', '.join(CITIES)}")
    print(f"   关键词: {len(KEYWORDS)} 个 × {PAGES_PER_KW} 页/词")
    print(f"   间隔: 翻页{PAGE_WAIT}s 关键词{KW_SLEEP}s")
    print("=" * 60)

    total_all = 0
    total_saved = 0
    city_stats = {}

    for ci, city in enumerate(CITIES):
        city_code = CITY_CODES[city]
        if ci > 0 and ci % RELOAD_EVERY_N_CITIES == 0:
            print(f"\n🔄 reload浏览器...")
            reload_browser()

        print(f"\n{'─' * 50}")
        print(f"🏙️  [{ci+1}/{len(CITIES)}] {city} ({city_code})")
        print(f"{'─' * 50}")

        city_total = 0
        city_saved = 0

        for ki, kw in enumerate(KEYWORDS):
            print(f"  🔍 [{ki+1}/{len(KEYWORDS)}] {kw} ...", end="", flush=True)

            try:
                jobs = search_city_kw(city, city_code, kw)
            except Exception as e:
                print(f" ❌ 异常: {e}")
                continue

            city_total += len(jobs)
            saved = 0
            for j in jobs:
                if upsert_job(j, city, BATCH_ID):
                    saved += 1

            city_saved += saved
            print(f" → {len(jobs)}条, 入库{saved}条")

            # 关键词间休息
            wt = random.uniform(*KW_SLEEP)
            time.sleep(wt)

        city_stats[city] = {"collected": city_total, "saved": city_saved}
        total_all += city_total
        total_saved += city_saved

        print(f"  📊 {city}: 采集{city_total} 入库{city_saved}")

    # ── 汇总 ──
    print(f"\n{'=' * 60}")
    print(f"✅ 多城采集完成")
    print(f"   总采集: {total_all} | 总入库: {total_saved}")
    for city, stats in city_stats.items():
        print(f"   {city:6s}: 采集{stats['collected']:>4} 入库{stats['saved']:>4}")
    print(f"   批次: {BATCH_ID}")
    print(f"   DB: {DB_PATH}")


if __name__ == "__main__":
    main()
