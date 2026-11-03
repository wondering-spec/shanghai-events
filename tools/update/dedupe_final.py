#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""终局去重：同标题的重复卡片合并成一张

背景：跨源合并后仍会留下大量同标题卡片，来源是
  ① 同一活动在豆瓣与猫眼各有条目（id 不同但 start_date 相同）
  ② 同一商家的多门店（千弗画室 虹口店 / 第一百货店 / 张江店）各发一条
用户看到的是一排一模一样的卡片，需要合并。

判定：标题归一化后相同，且满足以下任一：
  A. start_date 相同（明确同一场）
  B. 场馆名最长公共子串 >= 5（同一商家不同门店）

保留策略：优先豆瓣（字段全：地铁/区划/地址）→ 有海报 → 字段最全
"""
import json, re, os, datetime

IDX = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) + '/index.html'
PUNC = r'[【】\[\]（）()「」《》""\'\'\s·、,，.。!！?？~～—\-－_:：|｜／/@＠#＃&＆+＋*＊]'


def nz(s):
    return re.sub(PUNC, '', (s or '')).lower()


def nv(v):
    v = re.sub(r'^上海\s*[\u4e00-\u9fa5]{1,4}区\s*', '', (v or '').strip())
    v = re.sub(r'^上海\s+', '', v)
    return re.sub(PUNC, '', v).lower()


def lcs(a, b):
    """最长公共子串"""
    if not a or not b:
        return ''
    m = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    best = (0, 0)
    for x in range(1, len(a) + 1):
        for y in range(1, len(b) + 1):
            if a[x - 1] == b[y - 1]:
                m[x][y] = m[x - 1][y - 1] + 1
                if m[x][y] > best[0]:
                    best = (m[x][y], x)
    return a[best[1] - best[0]:best[1]]


def score(e):
    """保留优先级：豆瓣 > 有海报 > 字段全"""
    return ('douban' in (e.get('source') or ''),
            bool(e.get('poster')),
            len(e.get('venue') or ''),
            len(e.get('address') or ''))


def main():
    raw = open(IDX, encoding='utf-8').read()
    i = raw.find('window.__EVENTS__')
    j = raw.find('=', i) + 1
    k = raw.find('</script>', j)
    d = json.loads(raw[j:k].strip().rstrip(';').strip())
    evs = d['events']
    print(f'去重前: {len(evs)} 条')

    # 按标题分组
    groups = {}
    for e in evs:
        groups.setdefault(nz(e.get('title')), []).append(e)

    final = []
    merged_groups = 0
    removed = 0

    for key, members in groups.items():
        if len(members) == 1:
            final.append(members[0])
            continue
        # 在组内做并查集：满足 A 或 B 的连边
        n = len(members)
        par = list(range(n))

        def find(x):
            while par[x] != x:
                par[x] = par[par[x]]
                x = par[x]
            return x

        def uni(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                par[rb] = ra

        for a in range(n):
            for b in range(a + 1, n):
                ea, eb = members[a], members[b]
                same_start = (ea.get('start_date') == eb.get('start_date')
                              and ea.get('start_date'))
                va, vb = nv(ea.get('venue')), nv(eb.get('venue'))
                same_venue = bool(va and vb and len(lcs(va, vb)) >= 5)
                if same_start or same_venue:
                    uni(a, b)

        buckets = {}
        for idx in range(n):
            buckets.setdefault(find(idx), []).append(idx)

        for root, idxs in buckets.items():
            if len(idxs) == 1:
                final.append(members[idxs[0]])
                continue
            ms = [members[x] for x in idxs]
            ms.sort(key=score, reverse=True)
            keep = dict(ms[0])
            # 合并日期区间
            dates = sorted(set(e.get('start_date') for e in ms if e.get('start_date')))
            ends = sorted(set(e.get('end_date') for e in ms if e.get('end_date')))
            if dates:
                keep['start_date'] = dates[0]
            if ends:
                keep['end_date'] = ends[-1]
            # 合并标签
            tags = []
            for e in ms:
                for t in (e.get('tags') or []):
                    if t not in tags:
                        tags.append(t)
            keep['tags'] = tags[:5]
            # 合并来源
            srcs = set(e.get('source') for e in ms)
            if 'douban' in srcs and 'maoyan' in srcs:
                keep['source'] = 'douban+maoyan'
            # 补全购票链接
            tk = dict(keep.get('tickets') or {})
            for e in ms:
                for kk in ('maoyan', 'maoyan_show', 'damai'):
                    if not tk.get(kk) and (e.get('tickets') or {}).get(kk):
                        tk[kk] = e['tickets'][kk]
                if not keep.get('mv_id') and e.get('mv_id'):
                    keep['mv_id'] = e['mv_id']
            if tk:
                keep['tickets'] = tk
            keep['merged_from'] = [{'id': e['id'], 'title': e['title']}
                                   for e in ms if e['id'] != keep['id']]
            final.append(keep)
            merged_groups += 1
            removed += len(ms) - 1

    d['events'] = final
    d['count'] = len(final)
    d['updated_at'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    d['source_stats'] = {
        'douban': sum(1 for e in final if e.get('source') == 'douban'),
        'maoyan': sum(1 for e in final if e.get('source') == 'maoyan'),
        'douban+maoyan': sum(1 for e in final if e.get('source') == 'douban+maoyan'),
        'total': len(final),
    }

    # 备份后写回
    bak = IDX + '.bak-dedupe-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    open(bak, 'w', encoding='utf-8').write(raw)
    block = json.dumps(d, ensure_ascii=False, separators=(',', ':'))
    open(IDX, 'w', encoding='utf-8').write(raw[:j] + block + raw[k:])

    from collections import Counter
    print(f'合并 {merged_groups} 组，删掉 {removed} 条')
    print(f'去重后: {len(final)} 条')
    print('分类:', dict(Counter(e.get('category') for e in final).most_common()))
    # 复查
    g2 = Counter(nz(e.get('title')) for e in final)
    dup2 = {k: v for k, v in g2.items() if v > 1}
    print(f'剩余同标题组: {len(dup2)} (涉及 {sum(dup2.values())} 条)')
    for kk, vv in list(dup2.items())[:5]:
        print(f'   x{vv} {kk[:38]}')
    print(f'备份: {os.path.basename(bak)}')


if __name__ == '__main__':
    main()
