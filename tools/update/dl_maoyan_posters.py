#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""下载猫眼海报（meituan/pipi）并转 webp"""
import json, os, time, urllib.request
from PIL import Image

need = json.load(open('/tmp/need_posters.json'))
PD = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) + '/posters'
TMP = '/tmp/new_posters2'
os.makedirs(TMP, exist_ok=True)
UA_MOBILE = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1'
UA_DESK = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0 Safari/537.36'

ok = fail = skip = 0
for base, url in need:
    dst = os.path.join(PD, base)
    if os.path.exists(dst) and os.path.getsize(dst) > 500:
        skip += 1; continue
    # 选 UA 和 Referer
    ua = UA_MOBILE if 'pipi' in url else UA_DESK
    data = None
    for t in range(3):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': ua, 'Referer': 'https://show.maoyan.com/'})
            with urllib.request.urlopen(req, timeout=25) as r:
                data = r.read()
            if data and len(data) > 500:
                break
        except Exception:
            time.sleep(1.5 * (t + 1))
    if not data or len(data) <= 500:
        fail += 1; continue
    try:
        im = Image.open(__import__('io').BytesIO(data)).convert('RGB')
        if im.width > 400:
            h = int(im.height * 400 / im.width)
            im = im.resize((400, h), Image.LANCZOS)
        im.save(dst, 'WEBP', quality=82, method=4)
        ok += 1
    except Exception as e:
        fail += 1
        print(f"  转换失败 {base}: {e}")
    if (ok + fail) % 30 == 0:
        print(f"  进度 成功{ok} 失败{fail}", flush=True)
    time.sleep(0.1)

print(f"\n完成: 成功 {ok} | 失败 {fail} | 跳过 {skip}", flush=True)
