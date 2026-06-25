#!/usr/bin/env python3
"""51job 成都高新区附近采集 - 为中和街道定制。

搜索 Chengdu 全城前端+全栈关键词，使用 URL 直接导航（绕过已失效的 Vue 内部调用），
采集后按距中和街道最近的区过滤：高新区、武侯区、天府新区、双流区 → 增量入库

用法:
    python3 scripts/collect_near_zhonghe.py
"""
import json, os, random, re, subprocess, sys, time, sqlite3, urllib.parse
from pathlib import Path

# ── 配置 ──
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

# 区位：中和街道位于高新区，交界武侯区/天府新区/双流区
TARGET_DISTRICTS = ["高新区", "武侯区", "天府新区", "双流区"]

# 前端+全栈相关关键词（20个核心词）
KEYWORDS = [
    # 前端核心
    "前端", "React", "Vue", "JavaScript", "TypeScript", "Node.js",
    # 全栈
    "全栈", "Web前端", "H5前端",
    # 相关技术
    "小程序", "Uni-app", "Angular", "Electron", "Flutter",
    # 关联岗位
    "UI设计", "UX设计", "交互设计",
    # 工程化
    "前端架构", "Web开发", "跨平台",
]

PAGES = 3        # 每关键词搜3页
PAGE_WAIT = 3    # 页间等待秒
KW_SLEEP_MIN = 2
KW_SLEEP_MAX = 5

OUTFILE = RAW_DIR / f"job51_{CITY}_zhonghe_{int(time.time())}.jsonl"


# ──xbrowser 操作──
def xb_cmd(*args, timeout=30):
    r = subprocess.run(
        [NODE, XB_CJS, "run", "--browser", "default", "--timeout", str(timeout)] + list(args),
        capture_output=True, text=True, timeout=timeout + 15
    )
    return r.stdout

def _parse_xb_response(out):
    """解析 xb.cjs 返回的 JSON 格式。"""
    if '<!doctype' in out.lower() or 'aliyun_waf' in out.lower():
        return {'_err': 'WAF'}
    # 修复可能的裸 HTML 输出
    idx = out.find('{')
    if idx == -1:
        return {'_err': 'no_json', '_raw': out[:500]}
    try:
        return json.loads(out[idx:])
    except json.JSONDecodeError:
        return {'_err': 'bad_json', '_raw': out[idx:idx+500]}


def xb_eval(js, timeout=30):
    """执行 JS 并返回解析后的 eval 结果 dict。"""
    out = xb_cmd("eval", js, timeout=timeout)
    d = _parse_xb_response(out)
    if d.get('_err'):
        return d
    # xb.cjs 响应结构: {ok, data: {result: {success, data: {origin, result: "JSON string"}}}}
    try:
        result_str = d['data']['result']['data']['result']
        return json.loads(result_str)
    except (KeyError, json.JSONDecodeError, TypeError) as e:
        return {'_err': 'parse', '_msg': str(e), '_raw': out[:500]}


def navigate_to_kw(kw, timeout=25):
    """通过 URL 直接导航到关键词搜索结果页。"""
    kw_encoded = urllib.parse.quote(kw)
    url = f"https://we.51job.com/pc/search?keyword={kw_encoded}&jobArea={CITY_CODE}&searchType=2"
    xb_cmd("open", url, timeout=timeout)
    time.sleep(5)


def click_page(pg_num):
    """通过 JS 点击分页器页码。"""
    js = f"""(()=>{{
var items = document.querySelectorAll('.el-pager li.number');
if(items.length >= {pg_num}){{
  items[{pg_num - 1}].click();
  return JSON.stringify({{ok:1, clicked: '{pg_num}'}});
}}
return JSON.stringify({{ok:0, available: items.length}});
}})()"""
    r = xb_eval(js)
    return r.get('ok') == 1


def extract_page():
    """从当前页面提取岗位列表。"""
    js = """(()=>{
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
})()"""
    r = xb_eval(js)
    if r.get('_err'):
        return []
    data = r.get('data', [])
    return data if isinstance(data, list) else []


# ── 数据库 ──
def upsert_job(job, source="51job_zhonghe"):
    """增量写入一条岗位。"""
    title = job.get('title', '')
    company = job.get('company', '')
    district = job.get('district', '')
    salary = job.get('salary', '')
    url = job.get('url', '')
    info = job.get('info', [])

    dedupe_key = f"{source}:{district}:{title}:{company}:{salary}"

    # 薪资解析
    sal_min, sal_max = None, None
    if salary:
        nums = re.findall(r'(\d+\.?\d*)\s*-?\s*(\d+\.?\d*)\s*[万千]', salary)
        if not nums:
            nums = re.findall(r'(\d+\.?\d*)', salary)
            if nums:
                val = float(nums[0])
                if val < 100:
                    val *= 1000
                sal_min = sal_max = int(val)
        else:
            a, b = float(nums[0][0]), float(nums[0][1])
            if a < 100 and b < 100:
                a *= 1000; b *= 1000
            sal_min, sal_max = int(a), int(b)

    exp = info[0] if len(info) > 0 else ''
    edu = info[1] if len(info) > 1 else ''

    db = sqlite3.connect(str(DB_PATH))
    try:
        db.execute("""
            INSERT OR REPLACE INTO jobs
            (source, source_job_id, title, company_name, city, district,
             salary_text, salary_min, salary_max, experience, education,
             source_url, crawl_time, created_at, updated_at, dedupe_key)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'), datetime('now'), ?)
        """, (source, '', title, company, CITY, district,
              salary, sal_min, sal_max, exp, edu, url, dedupe_key))
        db.commit()
        return True
    except Exception as e:
        print(f"  ⚠️ DB error: {e}")
        return False
    finally:
        db.close()


# ── 主流程 ──
def main():
    print(f"🎯 中和街道周边岗位采集")
    print(f"   城市: {CITY} ({CITY_CODE})")
    print(f"   目标区域: {', '.join(TARGET_DISTRICTS)}")
    print(f"   关键词: {len(KEYWORDS)} 个 × {PAGES} 页")
    print(f"   输出: {OUTFILE}\n")

    total_collected = 0
    total_saved = 0
    districts_collected = {}

    all_jobs = []

    for ki, kw in enumerate(KEYWORDS):
        print(f"\n🔍 [{ki+1}/{len(KEYWORDS)}] {kw}")

        # URL 导航到关键词搜索结果
        navigate_to_kw(kw)
        time.sleep(random.uniform(1, 3))

        for pg in range(1, PAGES + 1):
            if pg > 1:
                if not click_page(pg):
                    print(f"  ⚠️ 翻页 {pg} 失败（共 {PAGES} 页）")
                    break
                time.sleep(PAGE_WAIT)

            jobs = extract_page()
            if not jobs:
                print(f"  📄 第{pg}页: 无结果")
                break

            # 按区域过滤
            filtered = [j for j in jobs if any(d in (j.get('district', '') or '') for d in TARGET_DISTRICTS)]

            # 统计
            for j in filtered:
                d = j.get('district', '未知')
                districts_collected[d] = districts_collected.get(d, 0) + 1

            if filtered:
                district_preview = ', '.join(j.get('district', '?') for j in filtered[:5])
                print(f"  📄 第{pg}页: {len(jobs)}条 → 🎯 {len(filtered)}条命中 [{district_preview}...]")
            else:
                print(f"  📄 第{pg}页: {len(jobs)}条 → 🎯 0条命中目标区域")

            # 保存 & 入库
            for j in filtered:
                all_jobs.append(j)
                total_collected += 1
                record = j.copy()
                record['city'] = CITY
                if upsert_job(record):
                    total_saved += 1

            if len(jobs) < 15:
                break

        # 关键词间休息
        time.sleep(random.uniform(KW_SLEEP_MIN, KW_SLEEP_MAX))

    # ── 写入JSONL ──
    with open(OUTFILE, 'w', encoding='utf-8') as f:
        for j in all_jobs:
            j['city'] = CITY
            f.write(json.dumps(j, ensure_ascii=False) + '\n')

    # ── 报告 ──
    print(f"\n{'='*50}")
    print(f"✅ 采集完成！")
    print(f"   采集总数: {total_collected}")
    print(f"   入库成功: {total_saved}")
    print(f"   JSONL: {OUTFILE}")
    print(f"\n   区域分布:")
    for d, c in sorted(districts_collected.items(), key=lambda x: -x[1]):
        print(f"     {d}: {c}")
    print(f"{'='*50}")


if __name__ == '__main__':
    main()
