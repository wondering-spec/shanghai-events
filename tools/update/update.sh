#!/bin/bash
# 上海文娱速递 —— 数据一键更新
#
# 用法：bash tools/update/update.sh
#
# 流程：清缓存 → 豆瓣抓取 → 解析 → 合并 → 豆瓣海报 → 写回
#       → 猫眼抓取 → 解析 → 合并 → 猫眼海报 → 终局去重 → 场馆官网 → 策展
#
# 注意：db_crawl.py 有断点续抓（/tmp/db_crawl 缓存），不清理就抓不到任何新数据，
#       所以第一步必须清缓存 —— 这是定时更新长期「没变化」的根因之一。
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SITE="$(cd "$HERE/../.." && pwd)"

# 优先用受管 venv（Pillow 已装），否则回落系统 python
if [ -x $HOME/.workbuddy/binaries/python/envs/default/bin/python ]; then
  PY=$HOME/.workbuddy/binaries/python/envs/default/bin/python
else
  PY=/usr/local/bin/python3
fi

echo "项目: $SITE"
echo "解释器: $PY"
echo "开始时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo

step() {
  echo "────────────────────────────────────────"
  echo "▶ $1"
  echo "────────────────────────────────────────"
}

# 1. 清豆瓣抓取缓存（关键）
step "1/13 清理豆瓣抓取缓存"
rm -rf /tmp/db_crawl
echo "已清空 /tmp/db_crawl"

# 2. 豆瓣抓取
step "2/13 抓取豆瓣同城·上海"
"$PY" "$HERE/db_crawl.py" || echo "!! 豆瓣抓取异常，继续后续步骤"

# 3. 解析
step "3/13 解析豆瓣数据"
if [ ! -d /tmp/db_crawl ] || [ -z "$(ls -A /tmp/db_crawl 2>/dev/null)" ]; then
  echo "!! 豆瓣无数据，跳过豆瓣链路"
else
  "$PY" "$HERE/db_parse.py" || echo "!! 解析失败"
fi

# 4. 合并（写回 merged_events.json）
step "4/13 合并豆瓣新旧数据"
if [ -f /tmp/db_parsed.json ]; then
  "$PY" "$HERE/db_merge.py" --write || echo "!! 合并失败"
else
  echo "!! 无 /tmp/db_parsed.json，跳过"
fi

# 5. 豆瓣海报
step "5/13 下载豆瓣新海报"
if [ -f /tmp/merged_events.json ]; then
  "$PY" "$HERE/dl_posters.py" || echo "!! 海报下载部分失败（不影响主流程）"
  "$PY" "$HERE/conv_posters.py" || echo "!! webp 转换失败"
else
  echo "!! 无 merged_events.json，跳过"
fi

# 6. 写回 index.html
step "6/13 写回 index.html（豆瓣部分）"
if [ -f /tmp/merged_events.json ]; then
  "$PY" "$HERE/db_writeback.py" || echo "!! 写回失败"
else
  echo "!! 无 merged_events.json，跳过"
fi

# 7. 猫眼抓取
step "7/13 抓取猫眼演出"
"$PY" "$HERE/maoyan_crawl.py" || echo "!! 猫眼抓取失败"

# 8. 猫眼解析（data.json → parsed.json）
step "8/13 解析猫眼数据"
if [ -f /tmp/maoyan_data.json ]; then
  "$PY" "$HERE/maoyan_parse.py" || echo "!! 猫眼解析失败"
else
  echo "!! 无 maoyan_data.json，跳过"
fi

# 9. 猫眼合并写回
step "9/13 合并猫眼数据并写回"
if [ -f /tmp/maoyan_parsed.json ]; then
  "$PY" "$HERE/maoyan_merge.py" || echo "!! 猫眼合并失败"
else
  echo "!! 无 maoyan_parsed.json，跳过"
fi

# 10. 猫眼海报
step "10/13 下载猫眼海报"
if [ -f /tmp/need_posters.json ]; then
  "$PY" "$HERE/dl_maoyan_posters.py" || echo "!! 猫眼海报部分失败"
else
  echo "!! 无 need_posters.json，跳过"
fi

# 11. 终局去重（同标题多门店/多源卡片合并）
step "11/13 终局去重"
"$PY" "$HERE/dedupe_final.py" || echo "!! 去重失败"

# 12. 旗舰场馆官网（大剧院 / 上交 / 东艺）→ data/official_shows.json；某家失败沿用上次数据
step "12/13 抓取旗舰场馆官网"
"$PY" "$HERE/venue_crawl.py" || echo "!! 场馆官网抓取失败（沿用上次数据）"

# 13. 策展：场馆白名单过滤 + 9 类归类 + 合并美术馆展览/大型演出/官网清单（data/*.json）
step "13/13 策展（白名单 / 归类 / 合并清单）"
"$PY" "$HERE/curate.py" || echo "!! 策展失败"

# 汇报
step "更新完成 · 统计"
"$PY" - "$SITE" <<'PYEOF'
import json, sys, os
from collections import Counter
site = sys.argv[1]
raw = open(os.path.join(site, 'index.html'), encoding='utf-8').read()
i = raw.find('window.__EVENTS__')
if i < 0:
    print('!! index.html 里找不到 __EVENTS__ 数据块')
    sys.exit(0)
j = raw.find('=', i) + 1
k = raw.find('</script>', j)
d = json.loads(raw[j:k].strip().rstrip(';').strip())
evs = d['events']
print(f"总条数: {len(evs)}")
print(f"更新时间: {d.get('updated_at')}")
print("\n分类统计:")
for c, n in Counter(e.get('category') for e in evs).most_common():
    print(f"  {c}: {n}")
print("\n来源分布:")
ss = d.get('source_stats') or {}
if ss:
    for key in ('douban', 'maoyan', 'douban+maoyan', 'total'):
        if key in ss:
            print(f"  {key}: {ss[key]}")
else:
    for s, n in Counter(e.get('source') for e in evs).most_common():
        print(f"  {s}: {n}")
have = sum(1 for e in evs if e.get('poster'))
print(f"\n海报覆盖: {have}/{len(evs)} ({have * 100 // max(len(evs), 1)}%)")
PYEOF

echo
echo "结束时间: $(date '+%Y-%m-%d %H:%M:%S')"
