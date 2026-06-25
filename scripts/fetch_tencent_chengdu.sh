#!/bin/bash
# 拉腾讯招聘 API 全量岗位，过滤成都，输出 JSONL
set -e
TMP=$(mktemp -d)
trap "rm -rf $TMP" EXIT
API="https://careers.tencent.com/tencentcareer/api/post/Query"
UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
OUT="data/raw/tencent_chengdu.jsonl"

> "$OUT"
page=1
total=0
while [ $page -le 50 ]; do
  ts=$(date +%s000)
  body=$(curl -s --max-time 20 \
    -H "User-Agent: $UA" \
    "${API}?timestamp=${ts}&keyword=&pageIndex=${page}&pageSize=50" 2>/dev/null)
  
  if [ -z "$body" ]; then
    echo "page${page}: empty response, stopping"
    break
  fi
  
  # 提取Posts数组，过滤包含"成都"的
  count=$(echo "$body" | python3 -c "
import sys,json
d=json.load(sys.stdin)
posts=d.get('Data',{}).get('Posts',[]) or []
cd=[p for p in posts if '成都' in p.get('LocationName','')]
for p in cd:
    print(json.dumps(p, ensure_ascii=False))
" 2>/dev/null | tee -a "$OUT" | wc -l | tr -d ' ')
  
  total=$((total + count))
  echo "page${page}: +${count} cd, total=${total}"
  
  # 检查还有没有更多页
  has_more=$(echo "$body" | python3 -c "
import sys,json
d=json.load(sys.stdin)
posts=d.get('Data',{}).get('Posts',[]) or []
print('yes' if len(posts)==50 else 'no')
" 2>/dev/null)
  
  if [ "$has_more" != "yes" ]; then
    echo "page${page}: less than 50 posts, done"
    break
  fi
  
  page=$((page + 1))
  sleep 1  # 限速
done

echo ""
echo "Total chengdu posts: $(wc -l < "$OUT")"
echo "Written to: $OUT"
