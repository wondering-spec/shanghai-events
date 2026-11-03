#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""解析豆瓣抓取结果 → 结构化 JSON"""
import os, re, json, html

SRC = '/tmp/db_crawl'
OUT = '/tmp/db_parsed.json'

# 分类 slug → 中文名（用于打标签）
SLUG_NAME = {
    'exhibition': '展览', 'drama': '戏剧', 'music': '音乐', 'kids': '亲子', 'comedy': '喜剧',
    '1001': '小型现场', '1002': '音乐会', '1003': '演唱会', '1004': '音乐节',
    '1101': '话剧', '1102': '音乐剧', '1103': '舞剧', '1104': '歌剧', '1105': '戏曲', '1106': '其他戏剧',
    '2201': '脱口秀', '2202': '相声',
}


def parse_page(h):
    """解析一页列表，返回条目列表"""
    out = []
    blocks = re.split(r'<li class="list-entry"', h)[1:]
    for li in blocks:
        m = re.search(r'/event/(\d+)/', li)
        if not m:
            continue
        eid = m.group(1)
        t = re.search(r'<span itemprop="summary">([^<]*)</span>', li)
        if not t:
            continue
        title = html.unescape(t.group(1)).strip()
        sd = re.search(r'itemprop="startDate" datetime="([^"]*)"', li)
        ed = re.search(r'itemprop="endDate" datetime="([^"]*)"', li)
        lat = re.search(r'itemprop="latitude" content="([^"]*)"', li)
        lng = re.search(r'itemprop="longitude" content="([^"]*)"', li)
        loc = re.search(r'<li title="([^"]*)"', li)
        tm = re.search(r'<li class="event-time">(.*?)</li>', li, re.S)
        fee = re.search(r'<li class="fee">.*?<strong>([^<]*)</strong>', li, re.S)
        cnt = dict(re.findall(r'<span>(\d+)人(参加|感兴趣)</span>', li))
        poster = re.search(r'data-lazy="([^"]*)"', li)
        addr_m = re.search(r'itemprop="location" content="([^"]*)"', li)

        time_raw = ''
        if tm:
            time_raw = re.sub(r'<[^>]+>', '', tm.group(1))
            time_raw = html.unescape(re.sub(r'\s+', ' ', time_raw)).strip()

        out.append({
            'id': eid,
            'title': title,
            'start': sd.group(1) if sd else None,
            'end': ed.group(1) if ed else None,
            'lat': lat.group(1) if lat else None,
            'lng': lng.group(1) if lng else None,
            'venue_raw': html.unescape(loc.group(1)).strip() if loc else '',
            'address_raw': html.unescape(addr_m.group(1)).strip() if addr_m else '',
            'date_raw': time_raw,
            'fee': html.unescape(fee.group(1)).strip() if fee else '',
            'join': int(cnt.get('参加', 0)),
            'wish': int(cnt.get('感兴趣', 0)),
            'poster_url': poster.group(1) if poster else '',
        })
    return out


def main():
    files = sorted(os.listdir(SRC))
    print(f"待解析页面: {len(files)}")
    events = {}
    for fn in files:
        if not fn.endswith('.html'):
            continue
        slug = fn[:-5].rsplit('_', 1)[0]
        h = open(os.path.join(SRC, fn), encoding='utf-8', errors='ignore').read()
        rows = parse_page(h)
        for r in rows:
            e = events.get(r['id'])
            if e is None:
                r['cats'] = [slug]
                events[r['id']] = r
            else:
                if slug not in e['cats']:
                    e['cats'].append(slug)
                # 补全缺失字段
                for k in ('start', 'end', 'lat', 'lng', 'venue_raw', 'address_raw', 'date_raw', 'fee', 'poster_url'):
                    if not e.get(k) and r.get(k):
                        e[k] = r[k]
                e['join'] = max(e.get('join', 0), r.get('join', 0))
                e['wish'] = max(e.get('wish', 0), r.get('wish', 0))
    print(f"去重后活动: {len(events)}")
    # 分类覆盖统计
    from collections import Counter
    cc = Counter(s for e in events.values() for s in e['cats'])
    print("\n各分类命中条目数:")
    for s, n in cc.most_common():
        print(f"  {SLUG_NAME.get(s, s):10s} ({s}) {n}")
    no_cat = sum(1 for e in events.values() if not e.get('start'))
    print(f"\n缺时间: {no_cat}")
    json.dump(list(events.values()), open(OUT, 'w'), ensure_ascii=False)
    print(f"已写出 {OUT}")


if __name__ == '__main__':
    main()
