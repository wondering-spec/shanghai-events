#!/bin/bash
# 上海文娱速递 —— 快速更新（只刷新猫眼 + 场馆官网，约 3 分钟）
#
# 用法：bash tools/update/quick.sh
#
# 猫眼两天能新上架几十场，每周一次全量更新会让新演出最多晚 7 天出现。
# 这个脚本跳过最慢的豆瓣抓取，其余步骤和 update.sh 一致：
#   猫眼抓取 → 解析 → 合并 → 海报 → 终局去重 → 场馆官网 → 策展
# 豆瓣条目原样保留，等每周一的全量更新再刷新。
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -x "$HOME/.workbuddy/binaries/python/envs/default/bin/python" ]; then
  PY="$HOME/.workbuddy/binaries/python/envs/default/bin/python"
else
  PY=/usr/local/bin/python3
fi

step() { echo "──── ▶ $1"; }

step "1/7 抓取猫眼演出"
"$PY" "$HERE/maoyan_crawl.py" || echo "!! 猫眼抓取失败"
step "2/7 解析猫眼数据"
[ -f /tmp/maoyan_data.json ] && { "$PY" "$HERE/maoyan_parse.py" || echo "!! 猫眼解析失败"; }
step "3/7 合并猫眼数据并写回"
[ -f /tmp/maoyan_parsed.json ] && { "$PY" "$HERE/maoyan_merge.py" || echo "!! 猫眼合并失败"; }
step "4/7 下载猫眼海报"
[ -f /tmp/need_posters.json ] && { "$PY" "$HERE/dl_maoyan_posters.py" || echo "!! 猫眼海报部分失败"; }
step "5/7 终局去重"
"$PY" "$HERE/dedupe_final.py" || echo "!! 去重失败"
step "6/7 抓取旗舰场馆官网"
"$PY" "$HERE/venue_crawl.py" || echo "!! 场馆官网抓取失败（沿用上次数据）"
step "7/7 策展"
"$PY" "$HERE/curate.py" || echo "!! 策展失败"
