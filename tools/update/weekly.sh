#!/bin/bash
# 上海文娱速递 —— 每周自动更新 + 发布到 GitHub Pages
#
# 用法：bash tools/update/weekly.sh          全量（豆瓣 + 猫眼 + 官网，约 30 分钟）
#      bash tools/update/weekly.sh --quick  快速（猫眼 + 官网，约 3 分钟，适合周中补新上架）
#
# 流程：update.sh 全量更新 → 质量检查（不通过就回滚、不发布）→ git commit → git push
# 日志：logs/weekly-YYYYMMDD.log
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SITE="$(cd "$HERE/../.." && pwd)"
cd "$SITE"
mkdir -p logs
LOG="logs/weekly-$(date +%Y%m%d).log"
exec > >(tee -a "$LOG") 2>&1

echo "== 每周更新开始 $(date '+%Y-%m-%d %H:%M:%S')"
cp index.html /tmp/se_index_before_weekly.html

MODE=full; [ "${1:-}" = "--quick" ] && MODE=quick
if [ "$MODE" = quick ]; then bash "$HERE/quick.sh"; else bash "$HERE/update.sh"; fi

# 质量检查：条数不能骤降、无过期活动、家庭位置不能出现精确地址
python3 -I - "$SITE/index.html" /tmp/se_index_before_weekly.html <<'PYEOF'
import json, sys, datetime
def load(p):
    t = open(p, encoding='utf-8').read()
    i = t.find('window.__EVENTS__'); j = t.find('=', i) + 1
    return t, json.JSONDecoder().raw_decode(t[j:].lstrip())[0]
t, d = load(sys.argv[1])
_, old = load(sys.argv[2])
n, n_old = len(d['events']), len(old['events'])
today = str(datetime.date.today())
expired = sum(1 for e in d['events'] if (e.get('end_date') or e.get('start_date') or '9') < today)
problems = []
if n < 400: problems.append(f'条数过少: {n}')
if n < n_old * 0.6: problems.append(f'条数骤降: {n_old} → {n}')
if expired: problems.append(f'有 {expired} 条过期活动')
# 敏感词放在不入库的 .private/leak_words.txt，避免检查脚本本身把它们公开
import os
lp = os.path.join(os.path.dirname(sys.argv[1]), '.private', 'leak_words.txt')
leaks = [w.strip() for w in open(lp, encoding='utf-8')] if os.path.exists(lp) else []
if not leaks: problems.append('缺少 .private/leak_words.txt，无法做隐私检查')
for leak in filter(None, leaks):
    if leak in t: problems.append('出现精确家庭地址关键词')
print(f'检查: {n_old} → {n} 条, 过期 {expired}')
if problems:
    print('!! 检查未通过: ' + '; '.join(problems)); sys.exit(1)
PYEOF
if [ $? -ne 0 ]; then
  echo "!! 回滚 index.html，本周不发布"
  cp /tmp/se_index_before_weekly.html index.html
  exit 1
fi

# 只保留最近 30 天的 .bak 备份
find . -maxdepth 1 -name 'index.html.bak-*' -mtime +30 -delete

git add -A index.html posters tools data
if git diff --cached --quiet; then
  echo "== 无变化，不提交"
else
  git commit -q -m "数据更新 $(date '+%Y-%m-%d')$([ "$MODE" = quick ] && echo '（快速）')"
  git push -q origin main && echo "== 已推送到 GitHub" || { echo "!! 推送失败"; exit 1; }
fi
echo "== 结束 $(date '+%Y-%m-%d %H:%M:%S')"
