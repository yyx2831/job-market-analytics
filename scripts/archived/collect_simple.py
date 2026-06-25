#!/usr/bin/env python3
"""51job 采集脚本 - 使用 xb.cjs eval + sync XHR 批量采集多城市岗位数据。

修复记录:
- v2: 修复 xb_eval 的 json.dumps bug（JS代码应以原始字符串传入 eval）
- v2: 文件写入改用追加模式
- v2: 修正城市码（西安=200200，重庆=060000）
- v2: XB 路径使用 expanduser
- v2: 城市间重启浏览器，清除 cookie 污染
- v2: WAF 检测 + 智能重试

用法:
    python3 scripts/collect_simple.py [城市...]
    python3 scripts/collect_simple.py 武汉 西安  # 只采这两个
    python3 scripts/collect_simple.py            # 所有默认城市
"""
import json, os, random, subprocess, sys, time
from pathlib import Path

# ── 配置 ──────────────────────────────────────────────────

XB_CJS = os.path.expanduser(
    "~/Library/Application Support/QClaw/openclaw/config/skills/xbrowser/scripts/xb.cjs"
)
NODE = os.environ.get("QCLAW_CLI_NODE_BINARY", "node")
RAW_DIR = Path("/Users/yangyuxiao/codes/job-market-analytics/data/raw")
RAW_DIR.mkdir(parents=True, exist_ok=True)

# 城市码（与 job51_xbrowser.py 保持一致）
CITY_CODES = {
    "武汉": "180200", "西安": "200200", "重庆": "060000", "南京": "070200",
    "北京": "010000", "上海": "020000", "广州": "030200", "深圳": "040000",
    "杭州": "080200", "成都": "090200",
}

KEYWORDS = ["Python", "Java", "前端", "测试", "运维", "产品经理", "数据分析", "AI算法", "嵌入式", "销售"]
PAGES_PER_KW = 2
PAGE_SLEEP = (20, 35)        # 页间间隔（加强版，防 WAF）
KW_SLEEP = (40, 65)          # 关键词间间隔
CITY_SLEEP = (120, 180)      # 城市间间隔 + 浏览器重启
WAF_COOLDOWN = 300           # WAF 触发后冷却秒数

# ── JS 采集模板 ───────────────────────────────────────────

JS_EXTRACT = """(function(){
var u='https://we.51job.com/api/job/search-pc?api_key=51job&timestamp='+Date.now()+'&keyword=KW_PH&searchType=2&jobArea=CA_PH&sortType=0&pageNum=PG_PH&pageSize=20';
var xhr=new XMLHttpRequest();
xhr.open('GET',u,false);
xhr.send();
if(xhr.status!==200) return JSON.stringify({_err:'HTTP_'+xhr.status});
var t=xhr.responseText;
if(t.indexOf('<!doctype')>-1 || t.indexOf('aliyun_waf')>-1) return JSON.stringify({_err:'WAF'});
var d=JSON.parse(t);
if(d.status!=='1') return JSON.stringify({_err:d.message||'api_error'});
var items=d.resultbody.job.items;
var out=items.map(function(j){return{
id:j.jobId||'',title:(j.jobName||'').trim(),company:(j.companyName||j.coName||'').trim(),
salary:(j.provideSalary||j.jobSalary||'').trim(),area:(j.workAreaText||j.jobArea||'').trim(),
exp:(j.workYear||'').trim(),edu:(j.degreeName||'').trim(),
industry:(j.industryName||'').trim(),coSize:(j.companySizeText||'').trim(),
coType:(j.companyTypeText||'').trim(),desc:(j.jobDescription||j.jobInfo||'').trim(),
date:(j.issuedate||j.publishDate||'').trim(),
tags:Array.isArray(j.jobTags)?j.jobTags:[],href:j.jobHref||'',
salaryMin:j.jobSalaryMin||'',salaryMax:j.jobSalaryMax||''};});
return JSON.stringify({total:d.resultbody.job.totalCount,count:out.length,items:out});
})()"""


# ── xbrowser 操作 ─────────────────────────────────────────

def xb_stop():
    """停止浏览器 daemon."""
    subprocess.run([NODE, XB_CJS, "run", "--browser", "default", "--timeout", "10", "stop"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)


def xb_open(url, timeout=20):
    """打开 URL."""
    subprocess.run([NODE, XB_CJS, "run", "--browser", "default", "--timeout", str(timeout),
                    "open", url],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout + 10)


def xb_eval(js, timeout=30):
    """在浏览器中执行 JS 并返回解析后的 dict.

    注意：js 必须以原始 JS 字符串传入（不要 json.dumps），
    因为 xb.cjs 的 eval 命令需要可执行的 JavaScript 代码。
    """
    r = subprocess.run(
        [NODE, XB_CJS, "run", "--browser", "default", "--timeout", str(timeout), "eval", js],
        capture_output=True, text=True, timeout=timeout + 15
    )
    out = r.stdout

    # WAF 检测
    if '<!doctype' in out.lower() or 'aliyun_waf' in out.lower():
        return {'_err': 'WAF', '_detail': 'WAF HTML in xb response'}

    idx = out.find('{')
    if idx == -1:
        return {'_err': 'parse', '_detail': 'no JSON found', '_raw': out[:200]}

    try:
        d = json.loads(out[idx:])
    except json.JSONDecodeError:
        return {'_err': 'parse', '_detail': 'invalid JSON', '_raw': out[idx:idx + 200]}

    if not d.get('ok'):
        err = d.get('data', {}).get('result', {}).get('error', 'unknown')
        return {'_err': 'xb', '_detail': err}

    result_val = d['data']['result']['data']['result']

    # result_val 可能是字符串（JS 返回值）或已解析对象
    if isinstance(result_val, dict):
        return result_val

    try:
        return json.loads(result_val)
    except (json.JSONDecodeError, TypeError):
        return {'_err': 'parse', '_detail': f'result not JSON', '_raw': str(result_val)[:300]}


def fetch_page(keyword, city_code, page):
    """调用 51job API 获取一页数据."""
    js = JS_EXTRACT.replace('KW_PH', keyword).replace('CA_PH', city_code).replace('PG_PH', str(page))
    return xb_eval(js, timeout=30)


# ── 采集逻辑 ──────────────────────────────────────────────

def collect_city(city):
    """采集单个城市的所有关键词数据，返回成功条数."""
    code = CITY_CODES.get(city)
    if not code:
        print(f"  ❌ 未知城市: {city}")
        return 0

    outfile = RAW_DIR / f"job51_{city}.jsonl"
    total = 0
    waf_strikes = 0
    max_waf_strikes = 3

    print(f"\n{'='*60}")
    print(f"  📍 {city} (code={code})")
    print(f"  📁 输出: {outfile}")
    print(f"{'='*60}")

    # 每次城市启动新浏览器会话（清除 cookie）
    print("  🔄 重启浏览器...", end=" ", flush=True)
    xb_stop()
    time.sleep(3)
    xb_open(f"https://we.51job.com/pc/search?keyword=Python&location={code}", timeout=25)
    time.sleep(8)
    print("ok")

    for kw_idx, kw in enumerate(KEYWORDS):
        label = f"  [{kw_idx+1}/{len(KEYWORDS)}] {kw}:"
        print(f"  {label:<30}", end="", flush=True)
        kw_jobs = 0

        for p in range(1, PAGES_PER_KW + 1):
            resp = fetch_page(kw, code, p)

            if resp.get('_err') == 'WAF':
                waf_strikes += 1
                print(f"⛔WAF ", end="", flush=True)
                if waf_strikes >= max_waf_strikes:
                    print(f"\n    ⚠️ 连续 {max_waf_strikes} 次 WAF，放弃此城市")
                    return total
                print(f"(冷却{WAF_COOLDOWN}s)...", end="", flush=True)
                time.sleep(WAF_COOLDOWN)
                continue

            if resp.get('_err'):
                print(f"p{p}={resp['_err']} ", end="", flush=True)
                break

            items = resp.get('items', [])
            cnt = len(items)
            if cnt == 0:
                print(f"p{p}=0 ", end="", flush=True)
                break

            # 追加写入 JSONL
            with open(outfile, 'a', encoding='utf-8') as f:
                for item in items:
                    item['_keyword'] = kw
                    item['_city'] = city
                    f.write(json.dumps(item, ensure_ascii=False) + '\n')

            kw_jobs += cnt
            print(f"p{p}={cnt} ", end="", flush=True)

            if p < PAGES_PER_KW:
                sleep_time = random.randint(*PAGE_SLEEP)
                time.sleep(sleep_time)

        total += kw_jobs
        print(f"→ {kw_jobs}条", flush=True)

        # 关键词间隔
        if kw_idx < len(KEYWORDS) - 1:
            sleep_time = random.randint(*KW_SLEEP)
            print(f"    💤 关键词间隔 {sleep_time}s...", flush=True)
            time.sleep(sleep_time)

    print(f"  ✅ {city} 完成: {total} 条 → {outfile.name}", flush=True)
    return total


def main():
    cities = sys.argv[1:] if len(sys.argv) > 1 else ["武汉", "西安", "重庆", "南京"]

    print(f"🚀 51job 批量采集启动")
    print(f"📋 城市: {cities}")
    print(f"🏷️  关键词({len(KEYWORDS)}): {', '.join(KEYWORDS)}")
    print(f"📄 每词 {PAGES_PER_KW} 页 x 20 条 = 每词最多 {PAGES_PER_KW * 20} 条")
    print(f"⏱️  页间 {PAGE_SLEEP[0]}-{PAGE_SLEEP[1]}s | 词间 {KW_SLEEP[0]}-{KW_SLEEP[1]}s | 城间 {CITY_SLEEP[0]}-{CITY_SLEEP[1]}s")
    print()

    grand_total = 0
    for i, city in enumerate(cities):
        city_total = collect_city(city)
        grand_total += city_total

        if i < len(cities) - 1:
            sleep_time = random.randint(*CITY_SLEEP)
            print(f"\n{'~'*40}")
            print(f"  🌃 城市冷却 {sleep_time}s... (下次将要重启浏览器)")
            print(f"{'~'*40}")
            time.sleep(sleep_time)

    print(f"\n{'='*60}")
    print(f"  🎉 全部完成！总计: {grand_total} 条")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
