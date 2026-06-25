# Archived Scripts

These scripts have been **superseded by the unified collection framework** (`src/scraping/` + `scripts/run_spider.py`).

| Script | Reason for Archival | Superseded By |
|--------|-------------------|---------------|
| `collect_chengdu_dom.py` | Direct xb.cjs calls, no framework integration | `run_spider.py --source job51_xbrowser --city 成都` |
| `collect_multicity.py` | Direct xb.cjs calls, hardcoded logic | `run_spider.py --source job51_xbrowser --cities ...` |
| `collect_simple.py` | Sync XHR approach (defeated by WAF), direct xb.cjs | `run_spider.py --source job51_xbrowser` |
| `collect_chengdu_zhaopin.py` | Zhilian recruitment, ~5% hit rate, low practical value | N/A (source is low-yield) |
| `collect_near_zhonghe.py` | One-off customized collection, v1 (replaced by v2) | `collect_near_zhonghe_v2.py` |
| `collect_simple.sh` | Shell wrapper for collect_simple.py | N/A |
| `generate_sample_data.py` | Old mock sample generator (CSV-based) | `generate_mock_jsonl.py` |

## Still Active

- `collect_near_zhonghe_v2.py` — One-off customized collection for Zhonghe area, kept for reference
- All other scripts in `scripts/` — Are part of the current pipeline
