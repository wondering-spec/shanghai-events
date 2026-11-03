#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""猫眼演出全量抓取（列表接口，翻页）"""
import json, time, urllib.request, urllib.error

OUT = '/tmp/maoyan_data.json'
UA = ('Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 '
      '(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1')
REF = 'https://show.maoyan.com/list/0'
PAGE_SIZE = 100

def fetch(page):
    url = (f'https://m.dianping.com/myshow/ajax/performances/0;st=0;p={page};s={PAGE_SIZE};tft=0'
           f'?cityId=10&sellChannel=7')
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Referer': REF})
    for t in range(3):
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.loads(r.read().decode('utf-8'))
        except Exception as e:
            time.sleep(2 * (t + 1))
    return None

def main():
    all_items = []
    page = 1
    while True:
        d = fetch(page)
        if not d or d.get('code') != 200:
            print(f"第 {page} 页失败: {d.get('msg') if d else 'None'}", flush=True)
            break
        data = d.get('data') or []
        if not data:
            break
        all_items.extend(data)
        print(f"第 {page} 页: {len(data)} 条 (累计 {len(all_items)})", flush=True)
        if len(data) < PAGE_SIZE:
            break
        page += 1
        time.sleep(0.4)
    # 去重（按 performanceId）
    seen = {}
    for x in all_items:
        seen[x['performanceId']] = x
    items = list(seen.values())
    print(f"\n完成: 抓取 {len(all_items)} 条，去重后 {len(items)} 条", flush=True)
    json.dump(items, open(OUT, 'w'), ensure_ascii=False)
    print(f"已写出 {OUT}", flush=True)

if __name__ == '__main__':
    main()
