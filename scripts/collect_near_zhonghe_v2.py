#!/usr/bin/env python3
"""[ARCHIVED REFERENCE] 51job 成都前端岗位补充采集（v2）- 针对上次被反爬阻断的13个关键词。

⚠️ 这是一次性定制采集脚本，保留作为参考。日常采集请使用: run_spider.py

改进：
- 关键词间隔 12-20s（之前 2-5s）
- 翻页间隔 6-8s（之前 3s）
- 每3个词reload一次浏览器
- 只采2页（减少触发概率）

用法: python3 scripts/collect_near_zhonghe_v2.py
"""
import json, os, random, re, subprocess, sys, time, sqlite3
from pathlib import Path

XB_CJS = os.path.expanduser(
    "~/Library/Application Support/QClaw/openclaw/config/skills/xbrowser/scripts/xb.cjs"
)
NODE = os.environ.get("QCLAW_CLI_NODE_BINARY") or "/Applications/QClaw.app/Contents/Resources/node/node"
PROJECT = Path("/Users/yangyuxiao/codes/job-market-analytics")
RAW_DIR = PROJECT / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = PROJECT / "data" / "processed" / "jobs.db"

CITY = "成都"
CITY_CODE = "090200"
TARGET_DISTRICTS = ["高新区", "武侯区"]

# 上次被反爬阻断的13个关键词
KEYWORDS = [
    "Web前端", "H5前端", "小程序", "Uni-app", "Angular",
    "Electron", "Flutter", "UI设计", "UX设计", "交互设计",
    "前端架构", "Web开发", "跨平台",
]

PAGES = 2
PAGE_WAIT_MIN = 6
PAGE_WAIT_MAX = 8
KW_SLEEP_MIN = 12
KW_SLEEP_MAX = 20
RELOAD_EVERY = 3  # 每N个词reload浏览器

OUTFILE = RAW_DIR / f"job51_{CITY}_zhonghe_v2_{int(time.time())}.jsonl"


def parse_salary(text):
    """薪资解析，处理 千/万/K 混合格式。"""
    if not text:
        return None, None
    text = text.strip()
    
    m = re.match(r'(\d+\.?\d*)\s*千\s*-\s*(\d+\.?\d*)\s*万', text)
    if m:
        return int(float(m.group(1)) * 1000), int(float(m.group(2)) * 10000)
    m = re.match(r'(\d+\.?\d*)\s*千\s*-\s*(\d+\.?\d*)\s*千', text)
    if m:
        return int(float(m.group(1)) * 1000), int(float(m.group(2)) * 1000)
    m = re.match(r'(\d+\.?\d*)\s*万\s*-\s*(\d+\.?\d*)\s*万', text)
    if m:
        return int(float(m.group(1)) * 10000), int(float(m.group(2)) * 10000)
    m = re.match(r'(\d+\.?\d*)\s*-\s*(\d+\.?\d*)\s*万', text)
    if m:
        return int(float(m.group(1)) * 10000), int(float(m.group(2)) * 10000)
    m = re.match(r'(\d+\.?\d*)\s*-\s*(\d+\.?\d*)\s*千', text)
    if m:
        return int(float(m.group(1)) * 1000), int(float(m.group(2)) * 1000)
    m = re.match(r'(\d+\.?\d*)\s*-\s*(\d+\.?\d*)\s*[Kk]', text)
    if m:
        a, b = float(m.group(1)), float(m.group(2))
        if a < 100 and b < 100:
            a, b = a * 1000, b * 1000
        return int(a), int(b)
    m = re.match(r'(\d+\.?\d*)\s*-\s*(\d+\.?\d*)\s*元', text)
    if m:
        a, b = float(m.group(1)), float(m.group(2))
        if a < 100:
            a, b = a * 1000, b * 1000
        return int(a), int(b)
    m = re.match(r'(\d+\.?\d*)\s*-\s*(\d+\.?\d*)', text)
    if m:
        a, b = float(m.group(1)), float(m.group(2))
        if a < 100:
            a, b = a * 1000, b * 1000
        return int(a), int(b)
    m = re.match(r'(\d+\.?\d*)', text)
    if m:
        v = float(m.group(1))
        if v < 100:
            v *= 1000
        return int(v), int(v)
    return None, None


def xb_cmd(*args, timeout=30):
    r = subprocess.run([NODE, XB_CJS, "run", "--browser", "default", "--timeout", str(timeout)] + list(args),
                       capture_output=True, text=True, timeout=timeout + 15)
    return r.stdout

def reload_page():
    """重新打开51job搜索页"""
    kw = random.choice(["前端", "React", "Vue"])
    url = f"https://we.51job.com/pc/search?keyword={kw}&jobArea={CITY_CODE}&searchType=2"
    xb_cmd("open", url, timeout=25)
    time.sleep(5)
    print(f"  🔄 reload完成 (keyword={kw})")

def search_and_extract(kw):
    """URL直接跳转搜索"""
    from urllib.parse import quote
    url = f"https://we.51job.com/pc/search?keyword={quote(kw)}&jobArea={CITY_CODE}&searchType=2"
    xb_cmd("open", url, timeout=25)
    time.sleep(4)
    
    all_jobs = []
    for pg in range(1, PAGES + 1):
        if pg > 1:
            # 点击翻页
            js = f"""(()=>{{
                var btns=document.querySelectorAll('.j_page .page_btn');
                var nxt=null;
                for(var i=0;i<btns.length;i++){{if(btns[i].textContent.trim()==='{pg}' && btns[i].tagName==='A')nxt=btns[i];}}
                if(nxt)nxt.click();else{{var a=document.querySelector('.j_page .page_next');if(a)a.click();}}
                return 'ok';
            }})()"""
            r = subprocess.run([NODE, XB_CJS, "run", "--browser", "default", "--timeout", "15", "eval", js],
                               capture_output=True, text=True, timeout=25)
            time.sleep(random.uniform(PAGE_WAIT_MIN, PAGE_WAIT_MAX))
        
        # 提取
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
        r = subprocess.run([NODE, XB_CJS, "run", "--browser", "default", "--timeout", "15", "eval", js],
                           capture_output=True, text=True, timeout=25)
        out = r.stdout
        try:
            idx = out.index('{')
            outer = json.loads(out[idx:])
            # xb.cjs eval wraps result in: {ok, data: {result: {data: {result: "<json string>"}}}}
            inner_str = outer["data"]["result"]["data"]["result"]
            d = json.loads(inner_str)
        except (ValueError, json.JSONDecodeError, KeyError, TypeError) as e:
            print(f"    ❌ 解析失败 [{type(e).__name__}]: {out[:120]}")
            continue
        
        if not d.get('ok'):
            err = d.get('err', 'unknown')
            print(f"    ❌ 提取错误: {err}")
            continue
        
        jobs = d.get('data', [])
        # 过滤到目标区域
        filtered = [j for j in jobs if any(d2 in (j.get('district', '') or '') for d2 in TARGET_DISTRICTS)]
        
        district_counts = {}
        for j in filtered:
            d = j.get('district', '未知')
            district_counts[d] = district_counts.get(d, 0) + 1
        
        dc_str = ', '.join(f'{k}({v})' for k, v in district_counts.items())
        print(f"    📄 第{pg}页: {len(jobs)}条 → 🎯 {len(filtered)}条 [{dc_str}]")
        
        all_jobs.extend(filtered)
        
        if len(jobs) < 15:
            break
    
    return all_jobs


def upsert_job(job):
    title = job.get('title', '')
    company = job.get('company', '')
    district = job.get('district', '')
    salary = job.get('salary', '')
    url = job.get('url', '')
    info = job.get('info', [])
    
    dedupe_key = f"51job_zhonghe_v2:{district}:{title}:{company}:{salary}"
    sal_min, sal_max = parse_salary(salary)
    exp = info[0] if len(info) > 0 else ''
    edu = info[1] if len(info) > 1 else ''
    
    # Clean district format
    district = district.replace('成都·', '') if district else ''
    
    db = sqlite3.connect(str(DB_PATH))
    try:
        db.execute("""
            INSERT OR REPLACE INTO jobs
            (source, source_job_id, title, company_name, city, district,
             salary_text, salary_min, salary_max, experience, education,
             source_url, crawl_time, created_at, updated_at, dedupe_key)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'), datetime('now'), ?)
        """, ('51job_zhonghe', '', title, company, CITY, district,
              salary, sal_min, sal_max, exp, edu, url, dedupe_key))
        db.commit()
        return True
    except Exception as e:
        print(f"    ⚠️ DB: {e}")
        return False
    finally:
        db.close()


def main():
    print(f"🎯 中和街道周边 v2 补充采集")
    print(f"   目标区域: {', '.join(TARGET_DISTRICTS)}")
    print(f"   关键词: {len(KEYWORDS)} 个 × {PAGES} 页")
    print(f"   间隔: 关键词{KW_SLEEP_MIN}-{KW_SLEEP_MAX}s, 页{PAGE_WAIT_MIN}-{PAGE_WAIT_MAX}s")
    print(f"   冷却: 每{RELOAD_EVERY}词reload浏览器\n")

    total_collected = 0
    total_saved = 0
    district_counts = {}
    all_jobs_collected = []

    for ki, kw in enumerate(KEYWORDS):
        # 每N个词reload
        if ki > 0 and ki % RELOAD_EVERY == 0:
            reload_page()
        
        print(f"\n🔍 [{ki+1}/{len(KEYWORDS)}] {kw}")
        
        try:
            jobs = search_and_extract(kw)
        except Exception as e:
            print(f"  ❌ 异常: {e}")
            continue
        
        for j in jobs:
            d = j.get('district', '未知')
            district_counts[d] = district_counts.get(d, 0) + 1
            total_collected += 1
            j['keyword'] = kw
            j['city'] = CITY
            all_jobs_collected.append(j)
            if upsert_job(j):
                total_saved += 1
        
        # 关键词间休息
        sleep_t = random.uniform(KW_SLEEP_MIN, KW_SLEEP_MAX)
        print(f"  ⏳ 休息 {sleep_t:.1f}s...")
        time.sleep(sleep_t)
    
    # 写JSONL
    with open(OUTFILE, 'w', encoding='utf-8') as f:
        for j in all_jobs_collected:
            f.write(json.dumps(j, ensure_ascii=False) + '\n')
    
    print(f"\n{'='*50}")
    print(f"✅ v2采集完成")
    print(f"   采集: {total_collected} | 入库: {total_saved}")
    print(f"   区域: {dict(district_counts)}")
    print(f"   JSONL: {OUTFILE} ({len(all_jobs_collected)}条)")


if __name__ == '__main__':
    main()
