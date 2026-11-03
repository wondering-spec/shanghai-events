#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把合并后的数据写回 index.html"""
import os, re, json, datetime, sys

IDX = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) + '/index.html'
POSTERS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) + '/posters'

final = json.load(open('/tmp/merged_events.json'))
raw = open(IDX, encoding='utf-8').read()
i = raw.find('window.__EVENTS__'); j = raw.find('=', i)+1; k = raw.find('</script>', j)
old = json.loads(raw[j:k].strip().rstrip(';').strip())

# 校验海报落地，缺失的清空
have = set(os.listdir(POSTERS))
missing = 0
for e in final:
    p = e.get('poster') or ''
    fn = os.path.basename(p) if p else ''
    if not fn or fn not in have:
        if e.get('poster'):
            missing += 1
        e['poster'] = ''
    elif os.path.getsize(os.path.join(POSTERS, fn)) < 500:
        e['poster'] = ''
        missing += 1
print(f"海报缺失/清空: {missing}")

# 排序：推荐的排前面（保持页面自己的排序逻辑，这里只保证稳定）
final.sort(key=lambda e: (str(e.get('start_date') or '9999'), str(e.get('id'))))

now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
new = {
    'updated_at': now,
    'source': '豆瓣同城·上海 + 猫眼演出(格瓦拉)',
    'source_stats': {
        'douban': sum(1 for e in final if e.get('source') == 'douban'),
        'maoyan': sum(1 for e in final if e.get('source') == 'maoyan'),
        'douban+maoyan': sum(1 for e in final if e.get('source') == 'douban+maoyan'),
        'total': len(final),
    },
    'user_points': old.get('user_points'),
    'count': len(final),
    'events': final,
}

block = json.dumps(new, ensure_ascii=False, separators=(',', ':'))
raw2 = raw[:j] + block + raw[k:]

# 备份
bak = IDX + '.bak-update-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
open(bak, 'w', encoding='utf-8').write(raw)
open(IDX, 'w', encoding='utf-8').write(raw2)

print(f"写回完成: {len(old['events'])} → {len(final)} 条")
print(f"  updated_at: {old.get('updated_at')} → {now}")
print(f"  source_stats: {new['source_stats']}")
print(f"  文件大小: {len(raw)/1048576:.2f} MB → {len(raw2)/1048576:.2f} MB")
print(f"  备份: {os.path.basename(bak)}")
