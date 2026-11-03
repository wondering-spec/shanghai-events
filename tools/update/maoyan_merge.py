#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""合并：现有数据(豆瓣) + 新猫眼全量 → 去重写回"""
import json, re, datetime, os
from collections import defaultdict
from itertools import combinations

IDX = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) + '/index.html'
PUNC = r'[【】\[\]（）()「」《》""\'\'\s·、,，.。!！?？~～—\-－_:：|｜／/@＠#＃&＆+＋*＊]'

def nz(s): return re.sub(PUNC, '', (s or '')).lower()
def nv(v):
    v = re.sub(r'^上海\s*[\u4e00-\u9fa5]{1,4}区\s*', '', (v or '').strip())
    v = re.sub(r'^上海\s+', '', v)
    return re.sub(PUNC, '', v).lower()
def addr_fp(v):
    m = re.search(r'([\u4e00-\u9fa5]{2,8}(?:路|街|道|大道|弄|坊))\s*([\dA-Za-z\-—~至到]+号?)', v)
    if m: return (m.group(1), m.group(2))
    m2 = re.search(r'([\u4e00-\u9fa5]{2,8}(?:路|街|道|大道|弄|坊))', v)
    return (m2.group(1), '') if m2 else ('', '')
def lcs(a, b):
    if not a or not b: return ""
    m = [[0]*(len(b)+1) for _ in range(len(a)+1)]; best=(0,0)
    for x in range(1,len(a)+1):
        for y in range(1,len(b)+1):
            if a[x-1]==b[y-1]:
                m[x][y]=m[x-1][y-1]+1
                if m[x][y]>best[0]: best=(m[x][y],x)
    return a[best[1]-best[0]:best[1]]
def same_venue(a, b):
    va, vb = nv(a.get('venue')), nv(b.get('venue'))
    if not va or not vb: return False
    if va == vb: return True
    fa, fb = addr_fp(va), addr_fp(vb)
    if fa[0] and fb[0]:
        if fa[0] != fb[0]: return False
        if fa[1] and fb[1] and fa[1] != fb[1]: return False
        return True
    return len(lcs(va, vb)) >= 6

# 标题硬分类（补猫眼无分类 + 修正展览栏）
def title_category(t):
    t = t or ''
    if re.search(r'双展|联展|巡回展|特展|大展|精品展|个展|巡展|艺术展|影像展|画展|雕塑展|摄影展|文物展|沉浸展|VR展|XR展|光影展|博览会|双年展|首展', t):
        return '艺术展览'
    if re.search(r'越剧|京剧|昆曲|昆剧|沪剧|评弹|豫剧|黄梅戏|粤剧|锡剧|甬剧|川剧|秦腔|评剧|梆子|折子戏|戏曲', t): return '话剧/戏剧'
    if '音乐剧' in t: return '音乐剧'
    if re.search(r'演唱会|巡回|巡演|巡唱|音乐节', t): return '演唱会'
    if re.search(r'音乐会|交响|独奏|钢琴|小提琴|大提琴|合唱|声乐|歌剧|打击乐|管弦|爱乐|古琴|琵琶|二胡|古筝', t): return '古典音乐会'
    if re.search(r'脱口秀|相声|单口|开放麦', t): return '喜剧'
    if re.search(r'儿童剧|亲子|小朋友|童话|绘本|木偶剧', t): return '亲子演出'
    if re.search(r'话剧|舞剧|歌剧|舞台剧|杂技|魔术|芭蕾|默剧|独角戏', t): return '话剧/戏剧'
    if re.search(r'展|展览|博物馆|美术馆', t): return '艺术展览'
    return None

# 标签（简版）
def build_tags(cat, t):
    t = t or ''; tags = []
    m = {'音乐剧':[(['音乐剧'],'音乐剧')],
         '话剧/戏剧':[(['话剧'],'话剧'),(['舞剧','舞蹈','芭蕾'],'舞剧/舞蹈'),(['戏曲','京剧','越剧','昆曲'],'国风/民乐'),(['悬疑','惊悚','推理'],'悬疑/惊悚'),(['沉浸'],'沉浸式')],
         '古典音乐会':[(['钢琴'],'钢琴'),(['小提琴'],'小提琴'),(['交响'],'古典'),(['爵士'],'爵士'),(['古琴','琵琶','二胡','民乐','国风'],'国风/民乐'),(['合唱','声乐'],'声乐/合唱'),(['歌剧'],'歌剧')],
         '演唱会':[(['摇滚'],'演唱会'),(['民谣'],'演唱会'),(['说唱'],'演唱会'),(['乐队'],'演唱会'),(['爵士'],'爵士')],
         '喜剧':[(['脱口秀'],'脱口秀'),(['相声'],'喜剧/搞笑')],
         '亲子演出':[(['儿童','亲子','童话'],'儿童/亲子')],
         '艺术展览':[(['沉浸','VR','XR','光影'],'沉浸式'),(['绘画','雕塑'],'绘画/雕塑'),(['摄影'],'摄影'),(['数字','AI'],'数字/AI艺术'),(['当代艺术'],'当代艺术'),(['文物','历史'],'文物/历史'),(['设计','建筑'],'设计/建筑')]}
    for kws, tag in m.get(cat, []):
        if any(k in t for k in kws): tags.append(tag)
    if not tags:
        fallback = {'音乐剧':'音乐剧','话剧/戏剧':'话剧','古典音乐会':'古典','演唱会':'声乐/合唱','喜剧':'喜剧/搞笑','亲子演出':'儿童/亲子','艺术展览':'当代艺术'}
        tags.append(fallback.get(cat, cat))
    return tags[:4]

def main():
    raw = open(IDX, encoding='utf-8').read()
    i = raw.find('window.__EVENTS__'); j = raw.find('=', i)+1; k = raw.find('</script>', j)
    d = json.loads(raw[j:k].strip().rstrip(';').strip())
    evs = d['events']
    maoyan = json.load(open('/tmp/maoyan_parsed.json'))
    print(f"现有 {len(evs)} 条 | 新猫眼 {len(maoyan)} 条")

    # 补全猫眼无分类 + 生成 tags/venue 字段
    for e in maoyan:
        if not e['category']:
            e['category'] = title_category(e['title']) or '话剧/戏剧'
        e['tags'] = build_tags(e['category'], e['title'])
        e['venue_grade'] = 'A'
        e['venue_level'] = '中型剧场'
        e['district'] = ''
        e['nearest_metro'] = ''
        e['metro_lines'] = []
        e['venue_canon'] = e['venue']
        e['poster'] = f"posters/mv-{e['mv_id']}.webp"
        e['tickets'] = {
            'search_kw': e['title'],
            'damai': 'https://search.damai.cn/search.htm?keyword=' + e['title'],
            'maoyan': e['url'], 'maoyan_show': e['url'],
            'bing': 'https://cn.bing.com/search?q=' + e['title'] + ' 上海 购票',
            'db': e['url'],
        }

    # 拆分现有：豆瓣(含douban) vs 纯猫眼
    douban = [e for e in evs if 'douban' in (e.get('source') or '')]
    old_maoyan = [e for e in evs if (e.get('source') or '') == 'maoyan']
    print(f"  豆瓣 {len(douban)} | 旧猫眼 {len(old_maoyan)}")

    # 新猫眼按 mv_id 去重后，作为猫眼全集
    new_maoyan_by_id = {}
    for e in maoyan:
        new_maoyan_by_id[str(e['mv_id'])] = e

    # 合并池：豆瓣 + 新猫眼
    pool = list(douban) + list(new_maoyan_by_id.values())
    print(f"  合并池 {len(pool)} 条")

    # 跨源去重（豆瓣 vs 猫眼：同标题+同馆）
    par = list(range(len(pool)))
    def find(x):
        while par[x]!=x: par[x]=par[par[x]]; x=par[x]
        return x
    def uni(a,b):
        ra,rb=find(a),find(b)
        if ra!=rb: par[rb]=ra
    by_title = defaultdict(list)
    for idx, e in enumerate(pool): by_title[nz(e['title'])].append(idx)
    for t, idxs in by_title.items():
        if len(idxs) < 2: continue
        for a, b in combinations(idxs, 2):
            if find(a)==find(b): continue
            if same_venue(pool[a], pool[b]): uni(a, b)
    g = defaultdict(list)
    for idx in range(len(pool)): g[find(idx)].append(idx)

    final = []
    merged = 0
    for root, members in g.items():
        if len(members) == 1:
            final.append(pool[members[0]]); continue
        ms = [pool[x] for x in members]
        # 优先保留豆瓣条目（信息全），否则保留信息最全的
        ms.sort(key=lambda e: ('douban' in (e.get('source') or ''), bool(e.get('poster')), len(e.get('venue') or '')), reverse=True)
        keep = dict(ms[0])
        # 合并字段
        dates = sorted(set(e.get('start_date') for e in ms if e.get('start_date')))
        ends = sorted(set(e.get('end_date') for e in ms if e.get('end_date')))
        if dates: keep['start_date'] = dates[0]
        if ends: keep['end_date'] = ends[-1]
        tags = []
        for e in ms:
            for t in (e.get('tags') or []):
                if t not in tags: tags.append(t)
        keep['tags'] = tags
        srcs = set(e.get('source') for e in ms)
        if 'douban' in srcs and 'maoyan' in srcs: keep['source'] = 'douban+maoyan'
        # 若保留的是豆瓣条目，补上猫眼直链
        if 'douban' in (keep.get('source') or '') and not keep.get('tickets', {}).get('maoyan_show'):
            for e in ms:
                if (e.get('source') or '') == 'maoyan':
                    keep.setdefault('tickets', {})['maoyan_show'] = e.get('url')
                    keep.setdefault('tickets', {})['maoyan'] = e.get('url')
                    keep.setdefault('maoyan_url', e.get('url'))
                    if not keep.get('mv_id'): keep['mv_id'] = e.get('mv_id')
                    break
        keep['merged_from'] = [{'id': e['id'], 'title': e['title']} for e in ms if e['id'] != keep['id']]
        final.append(keep)
        merged += len(members) - 1

    # 过滤：非上海（猫眼城市过滤已保证，豆瓣都是上海）+ 无分类的删掉
    final = [e for e in final if e.get('category')]
    print(f"  去重后 {len(final)} 条（跨源合并 {merged} 条）")

    # 分类再修正（展览栏）
    def reclassify_exhibition(t):
        if re.search(r'双展|联展|巡回展|特展|大展|精品展|个展|巡展|艺术展|影像展|画展|雕塑展|摄影展|文物展|沉浸展|VR展|XR展|光影展|博览会|双年展|首展', t): return None
        if re.search(r'越剧|京剧|昆曲|昆剧|沪剧|评弹|豫剧|黄梅戏|粤剧|锡剧|甬剧|川剧|秦腔|评剧|梆子|折子戏', t): return '话剧/戏剧'
        if '音乐剧' in t: return '音乐剧'
        if re.search(r'演唱会|巡回|巡演|巡唱|音乐节', t): return '演唱会'
        if re.search(r'音乐会|交响|独奏|钢琴|小提琴|大提琴|合唱|声乐|歌剧|打击乐|管弦|爱乐', t): return '古典音乐会'
        if re.search(r'脱口秀|相声', t): return '喜剧'
        if re.search(r'儿童剧|亲子|童话|绘本|木偶剧', t): return '亲子演出'
        if re.search(r'话剧|舞剧|芭蕾|杂技|魔术|默片', t): return '话剧/戏剧'
        return None
    rc = 0
    for e in final:
        if e.get('category') == '艺术展览':
            new = reclassify_exhibition(e.get('title'))
            if new: e['category'] = new; rc += 1
    print(f"  展览栏再修正 {rc} 条")

    d['events'] = final
    d['count'] = len(final)
    d['updated_at'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    from collections import Counter
    d['source_stats'] = {'douban': sum(1 for e in final if e.get('source')=='douban'),
        'maoyan': sum(1 for e in final if e.get('source')=='maoyan'),
        'douban+maoyan': sum(1 for e in final if e.get('source')=='douban+maoyan'), 'total': len(final)}
    print("分类:", dict(Counter(e['category'] for e in final).most_common()))

    block = json.dumps(d, ensure_ascii=False, separators=(',', ':'))
    open(IDX, 'w', encoding='utf-8').write(raw[:j] + block + raw[k:])
    print(f"写回完成: {len(evs)} → {len(final)} 条")

    # 输出待下载猫眼海报清单 → /tmp/need_posters.json（dl_maoyan_posters.py 依赖）
    need = []
    posters_dir = os.path.join(os.path.dirname(IDX), 'posters')
    for e in final:
        p = e.get('poster') or ''
        if not p.startswith('posters/mv-'):
            continue
        fn = p[len('posters/'):]
        fp = os.path.join(posters_dir, fn)
        if os.path.exists(fp) and os.path.getsize(fp) > 500:
            continue
        if e.get('poster_url'):
            need.append((fn, e['poster_url']))
    json.dump(need, open('/tmp/need_posters.json', 'w', encoding='utf-8'), ensure_ascii=False)
    print(f"待下载猫眼海报: {len(need)} 张 → /tmp/need_posters.json")

if __name__ == '__main__':
    main()
