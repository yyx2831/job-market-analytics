#!/bin/zsh
# 极简51job采集：xb.cjs + Python JSON解析
# 必须先导航到搜索页，再从搜索页调 sync XHR API
# Usage: zsh scripts/collect_simple.sh [city1 city2 ...]

set -e

NODE="${QCLAW_CLI_NODE_BINARY:-node}"
XB="$HOME/Library/Application Support/QClaw/openclaw/config/skills/xbrowser/scripts/xb.cjs"
RAW_DIR="/Users/yangyuxiao/codes/job-market-analytics/data/raw"

mkdir -p "$RAW_DIR"

city_code() {
    case "$1" in
        武汉) echo "180200";;  西安) echo "290200";;
        重庆) echo "060200";;  南京) echo "070200";;
        北京) echo "010000";;  上海) echo "020000";;
        广州) echo "030200";;  深圳) echo "040000";;
        杭州) echo "080200";;  成都) echo "090200";;
        *) echo "";;
    esac
}

KEYWORDS=("Python" "Java" "前端" "测试" "运维" "产品经理" "数据分析" "AI算法" "嵌入式" "销售")

PAGES_PER_KW=2
PAGE_SLEEP_MIN=18
PAGE_SLEEP_MAX=28
KW_SLEEP_MIN=35
KW_SLEEP_MAX=55
CITY_WAIT_MIN=120
CITY_WAIT_MAX=180

# xb_eval: execute JS in browser, return the .result field as string
xb_eval() {
    local js="$1" timeout="${2:-20}"
    local escaped
    escaped=$(python3 -c "import sys,json; print(json.dumps(sys.argv[1]))" "$js")
    "$NODE" "$XB" run --browser default --timeout "$timeout" eval "$escaped" 2>/dev/null | \
        python3 -c "
import sys,json
t=sys.stdin.read();i=t.find('{')
if i==-1:print('{}');sys.exit(0)
d=json.loads(t[i:])
if not d.get('ok'):print(json.dumps({'error':'xb_fail'}));sys.exit(0)
r=d.get('data',{}).get('result',{}).get('data',{}).get('result','{}')
print(r)
"
}

fetch_page_json() {
    local keyword="$1" code="$2" page="$3"
    xb_eval "(function(){
var u='https://we.51job.com/api/job/search-pc?api_key=51job&timestamp='+Date.now()+'&keyword=${keyword}&searchType=2&jobArea=${code}&sortType=0&pageNum=${page}&pageSize=20';
var xhr=new XMLHttpRequest();
xhr.open('GET',u,false);
xhr.send();
if(xhr.status!==200) return JSON.stringify({error:'HTTP_'+xhr.status});
var d=JSON.parse(xhr.responseText);
if(d.status!=='1') return JSON.stringify({error:d.message||'api_error'});
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
})()" 25
}

collect_city() {
    local city="$1"
    local code outfile
    code=$(city_code "$city")
    outfile="$RAW_DIR/job51_${city}.jsonl"
    local total=0

    echo "=== $city ($code) ==="

    # Navigate to search page (establishes session)
    printf "  Navigating to search page..."
    "$NODE" "$XB" run --browser default --timeout 20 open \
        "https://we.51job.com/pc/search?keyword=Python&location=${code}" 2>/dev/null >/dev/null
    sleep 7 || true
    echo " done"

    local kw_idx=0
    for kw in $KEYWORDS; do
        printf "  %s: " "$kw"
        local kw_jobs=0 last_cnt=0

        for ((p=1; p<=PAGES_PER_KW; p++)); do
            local resp
            resp=$(fetch_page_json "$kw" "$code" "$p")

            # Check for error
            local err
            err=$(echo "$resp" | python3 -c "import sys,json;d=json.loads(sys.stdin.read());print(d.get('error',''))" 2>/dev/null || echo "parse_err")
            if [ -n "$err" ]; then
                printf "p%d=%s " "$p" "$err"
                break
            fi

            last_cnt=$(echo "$resp" | python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('count',0))" 2>/dev/null || echo "0")
            if [ "$last_cnt" = "0" ]; then
                printf "p%d=0 " "$p"
                break
            fi

            # Append items to output file
            echo "$resp" | python3 -c "
import sys,json
d=json.load(sys.stdin)
for item in d.get('items',[]):
    item['_keyword']='$kw'; item['_city']='$city'
    print(json.dumps(item,ensure_ascii=False))
" >> "$outfile"

            kw_jobs=$((kw_jobs + last_cnt))
            printf "p%d=%d " "$p" "$last_cnt"

            if [ $p -lt $PAGES_PER_KW ]; then
                sleep $((PAGE_SLEEP_MIN + RANDOM % (PAGE_SLEEP_MAX - PAGE_SLEEP_MIN + 1)))
            fi
        done

        total=$((total + kw_jobs))
        echo "(${kw_jobs} jobs)"

        kw_idx=$((kw_idx + 1))
        # Don't sleep after last keyword
        if [ $kw_idx -lt ${#KEYWORDS[@]} ]; then
            local kw_wait=$((KW_SLEEP_MIN + RANDOM % (KW_SLEEP_MAX - KW_SLEEP_MIN + 1)))
            echo "  ...sleeping ${kw_wait}s..."
            sleep "$kw_wait"
        fi
    done

    echo "  Total: $total jobs -> $outfile"
    return $total
}

# ── Main ──
CITIES=("$@")
if [ ${#CITIES[@]} -eq 0 ]; then
    CITIES=("武汉" "西安" "重庆" "南京")
fi

echo "Cities: ${CITIES[@]}"
echo "Keywords (${#KEYWORDS[@]}): ${KEYWORDS[@]}"
echo "Pages/kw: $PAGES_PER_KW, Page interval: ${PAGE_SLEEP_MIN}-${PAGE_SLEEP_MAX}s, KW interval: ${KW_SLEEP_MIN}-${KW_SLEEP_MAX}s"
echo ""

GRAND_TOTAL=0
local i=0
for city in $CITIES; do
    collect_city "$city"
    city_total=$?  # captures return value (0-255 only!)
    GRAND_TOTAL=$((GRAND_TOTAL + city_total))

    if [ $i -lt $((${#CITIES[@]} - 1)) ]; then
        local cwait=$((CITY_WAIT_MIN + RANDOM % (CITY_WAIT_MAX - CITY_WAIT_MIN + 1)))
        echo ""
        echo "=== City cool-down ${cwait}s ==="
        sleep "$cwait"
    fi
    i=$((i + 1))
done

echo ""
echo "Done. Grand total: $GRAND_TOTAL jobs in $RAW_DIR/"
ls -lh "$RAW_DIR"/job51_*.jsonl 2>/dev/null
