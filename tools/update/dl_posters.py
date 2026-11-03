#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""下载新增活动海报（豆瓣图，需带 Referer）"""
import os, json, time, urllib.request, urllib.error

PD = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) + '/posters'
OUT = '/tmp/new_posters'
os.makedirs(OUT, exist_ok=True)
UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36'

evs = json.load(open('/tmp/merged_events.json'))
have = set(os.listdir(PD))
todo = []
for e in evs:
    fn = f"{e['id']}.webp"
    fnj = f"{e['id']}.jpg"
    if (fn in have and os.path.getsize(os.path.join(PD, fn)) > 500):
        continue
    if (fnj in have and os.path.getsize(os.path.join(PD, fnj)) > 500):
        continue
    if os.path.exists(os.path.join(OUT, fnj)) and os.path.getsize(os.path.join(OUT, fnj)) > 500:
        continue
    if e.get('poster_url'):
        todo.append((e['id'], e['poster_url']))

print(f"需下载 {len(todo)} 张", flush=True)
ok = fail = 0
for i, (eid, url) in enumerate(todo, 1):
    dst = os.path.join(OUT, f'{eid}.jpg')
    done = False
    for t in range(3):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA, 'Referer': 'https://www.douban.com/'})
            with urllib.request.urlopen(req, timeout=20) as r:
                data = r.read()
            if len(data) > 500:
                open(dst, 'wb').write(data)
                ok += 1; done = True
                break
        except Exception as ex:
            time.sleep(1.5 * (t + 1))
    if not done:
        fail += 1
        print(f"  失败 {eid}", flush=True)
    if i % 25 == 0:
        print(f"  进度 {i}/{len(todo)}  成功{ok} 失败{fail}", flush=True)
    time.sleep(0.15)

print(f"\n完成: 成功 {ok} 失败 {fail}", flush=True)
