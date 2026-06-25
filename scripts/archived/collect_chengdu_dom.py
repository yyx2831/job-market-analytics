#!/usr/bin/env python3
"""51job 成都深度采集 - DOM提取（Vue状态切换方案）。

特点：
- 直接修改 Vue 组件状态切换城市，不触发 WAF
- DOM 选择器提取，走 SPA 渲染结果
- 支持更多关键词和页数
- 增量入库（避免重复）

用法:
    python3 scripts/collect_chengdu_dom.py
    python3 scripts/collect_chengdu_dom.py --pages 5 --max-sleep 10
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
CITY_CODE = "090200"

# 关键词：扩量到60个
KEYWORDS = [
    # 编程语言 (11)
    "Python", "Java", "JavaScript", "Go", "C++", "C语言", "PHP", "Rust", "TypeScript", "C#", "Kotlin",
    # 前端/移动 (6)
    "前端", "React", "Vue", "Android", "iOS", "Flutter",
    # 后端/数据 (8)
    "后端", "数据库", "大数据", "数据分析", "算法工程师", "AI算法", "机器学习", "深度学习",
    # 测试/运维/安全 (7)
    "测试", "运维", "网络安全", "安全工程师", "DevOps", "SRE", "DBA",
    # 产品/设计/运营 (8)
    "产品经理", "UI设计", "UX", "运营", "新媒体", "电商运营", "游戏策划", "交互设计",
    # 硬件/嵌入式 (4)
    "嵌入式", "硬件工程师", "芯片", "FPGA",
    # 通用岗位 (8)
    "项目经理", "销售", "HR", "财务", "会计", "法务", "行政", "客服",
    # 新兴/热门 (8)
    "架构师", "区块链", "云计算", "AIGC", "自动驾驶", "量化", "量化交易", "物联网",
]
PAGES_PER_KW = 5
PAGE_WAIT_MS = 3000   # 等 DOM 刷新
KW_SLEEP_MIN = 2      # 关键词间最小等待
KW_SLEEP_MAX = 5

OUTFILE = RAW_DIR / f"job51_{CITY_NAME}_dom_v3_60kw.jsonl"


# ── xbrowser 操作 ──
def xb_cmd(*args, timeout=30):
    """执行 xb.cjs 命令，返回 stdout 文本。"""
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
    """在浏览器执行 JS，返回解析后的 JSON。"""
    out = xb_cmd("eval", js, timeout=timeout)

    # WAF check
    if '<!doctype' in out.lower() or 'aliyun_waf' in out.lower():
        return {'_err': 'WAF'}

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


def switch_city(code):
    """通过 Vue 组件切换城市。"""
    js = f"""(()=>{{
try{{var a=document.querySelector('#app').__vue__;
var s=a.$children[0].$children[1];
var c=s.$children[0];
var t=c.cityInfo;t.code='{code}';
c.areaTags=[{{code:'{code}',value:''}}];
s.searchParams.jobArea='{code}';
s.searchParams.pageNum=1;
c.$nextTick(function(){{s.getSearch();}});
return JSON.stringify({{ok:1}});
}}catch(e){{return JSON.stringify({{err:e.message}});}}
}})()"""
    r = xb_eval_raw(js)
    return r.get("ok") == 1


def search_keyword(kw, city_code='090200'):
    """修改关键词并触发搜索（保持城市）。"""
    js = f"""(()=>{{
try{{var a=document.querySelector('#app').__vue__;
var s=a.$children[0].$children[1];
var c=s.$children[0];
s.searchParams.keyword='{kw}';
s.searchParams.jobArea='{city_code}';
s.searchParams.pageNum=1;
c.cityInfo.code='{city_code}';
c.areaTags=[{{code:'{city_code}',value:''}}];
s.getSearch();
return JSON.stringify({{ok:1}});
}}catch(e){{return JSON.stringify({{err:e.message}});}}
}})()"""
    r = xb_eval_raw(js)
    return r.get("ok") == 1


def goto_page(pg):
    """翻页。"""
    js = f"""(()=>{{
try{{var a=document.querySelector('#app').__vue__;
var s=a.$children[0].$children[1];
s.searchParams.pageNum={pg};
s.getJobList();
return JSON.stringify({{ok:1}});
}}catch(e){{return JSON.stringify({{err:e.message}});}}
}})()"""
    r = xb_eval_raw(js)
    return r.get("ok") == 1


def extract_page():
    """从当前 DOM 提取职位卡片。"""
    js = """(()=>{
try{
var cards=document.querySelectorAll('.joblist-item');
if(!cards.length){cards=document.querySelectorAll('.joblist-item');}
var out=[];
cards.forEach(function(c){
var t=c.querySelector('.joblist-item-jobname');
var s=c.querySelector('.sal');
var a=c.querySelector('.area');
var co=c.querySelector('.cname');
var info=c.querySelectorAll('.info .t');
var link=c.querySelector('a');
var tags=c.querySelectorAll('.tag');
var tagList=[];tags.forEach(function(tg){tagList.push(tg.textContent.trim());});
out.push({
title:t?t.textContent.trim():'',
salary:s?s.textContent.trim():'',
area:a?a.textContent.trim():'',
company:co?co.textContent.trim():'',
info:Array.from(info).map(function(i){return i.textContent.trim();}).join(' | '),
link:link?link.href:'',
tags:tagList,
count:out.length
});
});
return JSON.stringify({count:out.length,items:out});
}catch(e){return JSON.stringify({err:e.message});}
})()"""
    r = xb_eval_raw(js)
    if not r.get("ok"):
        return [], r.get("_err", "unknown")
    data = r.get("data", {}).get("result", {}).get("data", {}).get("result", "")
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except:
            return [], "parse_error"
    if isinstance(data, dict):
        return data.get("items", []), None
    return [], "no_data"


# ── 主流程 ──
def main():
    pages = 5
    max_sleep = 5

    for a in sys.argv[1:]:
        if a.startswith("--pages="):
            pages = int(a.split("=")[1])
        elif a.startswith("--max-sleep="):
            max_sleep = int(a.split("=")[1])

    total_expected = len(KEYWORDS) * pages * 20
    print(f"\n🚀 51job 成都深度采集 (DOM方案)")
    print(f"📋 关键词: {len(KEYWORDS)} 个")
    print(f"📄 每词 {pages} 页 × 20 条 = 每词最多 {pages * 20} 条")
    print(f"🎯 理论最大: {total_expected} 条")
    print(f"📁 输出: {OUTFILE}")
    print()

    # 启动浏览器
    print("🔄 启动浏览器...")
    xb_stop()
    time.sleep(2)
    xb_open(f"https://we.51job.com/pc/search?keyword=Python&jobArea={CITY_CODE}", timeout=30)
    time.sleep(10)

    # 切换城市
    print(f"📍 切换城市 → {CITY_NAME}...", end=" ")
    if not switch_city(CITY_CODE):
        print("❌ 失败")
        return
    time.sleep(3)
    print("✅")

    total_jobs = 0
    for kw_idx, kw in enumerate(KEYWORDS):
        print(f"\n[{kw_idx+1}/{len(KEYWORDS)}] {kw}:", end="", flush=True)

        # 切换关键词
        if not search_keyword(kw):
            print(" ❌ 搜索失败")
            continue
        time.sleep(PAGE_WAIT_MS / 1000)

        kw_jobs = 0
        for p in range(1, pages + 1):
            if p > 1:
                # 翻页
                if not goto_page(p):
                    print(f" p{p}=⛔", end="", flush=True)
                    time.sleep(2)
                    if not goto_page(p):
                        break
                time.sleep(PAGE_WAIT_MS / 1000)

            # 提取
            items, err = extract_page()
            if err:
                print(f" p{p}={err}", end="", flush=True)
                break

            cnt = len(items)
            if cnt == 0:
                print(f" p{p}=0", end="", flush=True)
                break

            print(f" p{p}={cnt}", end="", flush=True)

            # 写入
            with open(OUTFILE, 'a', encoding='utf-8') as f:
                for item in items:
                    item['_keyword'] = kw
                    item['_city'] = CITY_NAME
                    f.write(json.dumps(item, ensure_ascii=False) + '\n')

            kw_jobs += cnt

            if p < pages and cnt > 0:
                s = random.uniform(KW_SLEEP_MIN, KW_SLEEP_MIN + 0.5)
                time.sleep(s)

        total_jobs += kw_jobs
        print(f" → {kw_jobs}条", flush=True)

        if kw_idx < len(KEYWORDS) - 1:
            s = random.uniform(KW_SLEEP_MIN, max_sleep)
            print(f"  💤 {s:.1f}s...", flush=True)
            time.sleep(s)

    print(f"\n{'='*50}")
    print(f"✅ 完成！总计: {total_jobs} 条 → {OUTFILE}")
    print(f"{'='*50}")
    return total_jobs


if __name__ == "__main__":
    main()
