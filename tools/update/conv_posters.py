#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""新海报 jpg → webp，写入 posters/ 目录"""
import os, glob
from PIL import Image

SRC = '/tmp/new_posters'
DST = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) + '/posters'

ok = skip = fail = 0
sizes = []
for fp in sorted(glob.glob(os.path.join(SRC, '*.jpg'))):
    eid = os.path.basename(fp)[:-4]
    out = os.path.join(DST, f'{eid}.webp')
    if os.path.exists(out) and os.path.getsize(out) > 500:
        skip += 1
        continue
    try:
        im = Image.open(fp).convert('RGB')
        # 限制最大宽度 400（原数据普遍 175x260，不需要更大）
        if im.width > 400:
            h = int(im.height * 400 / im.width)
            im = im.resize((400, h), Image.LANCZOS)
        im.save(out, 'WEBP', quality=82, method=4)
        sizes.append(os.path.getsize(out))
        ok += 1
    except Exception as e:
        fail += 1
        print(f"  失败 {eid}: {e}")

print(f"转换完成: 成功 {ok} | 跳过 {skip} | 失败 {fail}")
if sizes:
    print(f"  输出大小: 平均 {sum(sizes)/len(sizes)/1024:.1f} KB, 最大 {max(sizes)/1024:.1f} KB")
