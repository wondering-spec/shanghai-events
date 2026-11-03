#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""终局策展：决定「什么能上网站」+「归到哪一类」

在 dedupe_final.py 之后运行，幂等（每周重跑结果一致）。

1. 场馆白名单（data/venues.json）：不在名单里的场馆整体剔除 —— 小剧场、商场快闪、画室等
2. 噪声黑名单：白名单场馆里的 DIY / VR / 烛光 / 开放麦 / 通票 等也剔除
3. 9 类归类：标题强信号 > 平台分类 > 场馆类型；拿不准的写进 data/review_queue.json
4. 人工/Claude 复核结果 data/labels.json 优先级最高（{id: {"category": ..., "drop": bool, "note": ...}}）
5. 合并策展清单 data/exhibitions.json（美术馆展览）、data/big_shows.json（大型演出）
   和 data/official_shows.json（旗舰场馆官网，由 venue_crawl.py 生成）

用法：python3 curate.py [--dry]
"""
import json, re, os, sys, hashlib, datetime
from collections import Counter, defaultdict

SITE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
IDX = os.path.join(SITE, 'index.html')
DATA = os.path.join(SITE, 'data')
LOGS = os.path.join(SITE, 'logs')

EXH, CLS, POP, MUS, DRA, DAN, OPE, COM, KID = (
    '艺术展览', '古典/器乐', '演唱会/Livehouse', '音乐剧', '话剧', '舞蹈/芭蕾', '戏曲', '喜剧/脱口秀', '亲子')
CATEGORIES = [EXH, CLS, POP, MUS, DRA, DAN, OPE, COM, KID]

# 标题强信号，按优先级排列：前面的更具体，命中即可定类
STRONG = [
    (KID, r'亲子|儿童|少儿|宝宝|童话|木偶|绘本|合家欢|家庭场|杂技|马戏|遛娃'),
    (OPE, r'越剧|京剧|昆曲|昆剧|沪剧|评弹|弹词|黄梅戏|豫剧|淮剧|川剧|粤剧|婺剧|乱弹|滑稽|独脚戏|秦腔|评剧|戏曲|锡剧|甬剧|折子戏|巾生'),
    (DAN, r'芭蕾|舞剧|舞蹈|现代舞|弗拉明戈|弗拉门戈|踢踏|舞团|街舞'),
    (MUS, r'音乐剧(?!.{0,6}(音乐会|演唱会|金曲|选段))'),
    (COM, r'脱口秀|相声|单口|漫才|魔术|Magic|即兴喜剧|喜剧专场'),
    (DRA, r'话剧|舞台剧|推理|悬疑剧|悬念剧场|独角戏|默剧|国家剧院现场|NT ?Live|高清放映|戏剧(?!节)|阿加莎|(经典|爱情|百老汇|英式|法国|新|王牌)喜剧'),
    (CLS, r'交响|协奏|奏鸣|独奏|室内乐|重奏|管弦|爱乐|钢琴|小提琴|大提琴|中提琴|长笛|单簧管|双簧管|圆号|小号|古琴|琵琶|二胡|古筝|民乐|歌剧|合唱|声乐|艺术歌曲|贝多芬|莫扎特|巴赫|肖邦|马勒|勃拉姆斯|柴可夫斯基|德彪西|拉威尔|舒伯特|舒曼|拉赫玛尼诺夫'),
    (POP, r'演唱会|live ?house|乐队|音乐节|爵士|说唱|嘻哈|摇滚|民谣|电音|DJ|tribute|致敬'),
    (EXH, r'特展|大展|个展|回顾展|双年展|艺术展|作品展|文物展|摄影展'),
]
WEAK = [
    (CLS, r'音乐会|乐团'),
    (POP, r'巡演|专场|巡回|LIVE|live'),
    (DRA, r'剧场|剧'),
    (EXH, r'展'),
]
# 有些强信号组合本身就说明归类有歧义（如「爵士钢琴」），交给复核
AMBIGUOUS_PAIRS = {frozenset([CLS, POP]), frozenset([DRA, COM])}

MAOYAN_CORNER = {
    '音乐会': {CLS}, '话剧音乐剧': {DRA, MUS}, 'Livehouse': {POP}, '休闲展览': {EXH}, '脱口秀': {COM},
    '亲子演出': {KID}, '戏曲艺术': {OPE}, '舞蹈芭蕾': {DAN}, '演唱会': {POP}, '沉浸剧场': {DRA},
    '相声': {COM}, '音乐节': {POP},
}
DOUBAN_SLUG = {
    'exhibition': {EXH}, 'drama': {DRA, MUS, DAN, OPE}, 'music': {CLS, POP}, 'kids': {KID}, 'comedy': {COM},
    '1001': {POP}, '1002': {CLS}, '1003': {POP}, '1004': {POP}, '1101': {DRA}, '1102': {MUS},
    '1103': {DAN}, '1104': {CLS}, '1105': {OPE}, '2201': {COM}, '2202': {COM},
}
# 旧 7 类 → 新 9 类（只作最弱的兜底；新类名映射到自身，保证幂等）
OLD_CAT = {'艺术展览': {EXH}, '古典音乐会': {CLS}, '演唱会': {POP}, '音乐剧': {MUS}, '话剧/戏剧': {DRA, DAN, OPE},
           '喜剧': {COM}, '亲子演出': {KID}, **{c: {c} for c in CATEGORIES}}
VENUE_PRIOR = {'museum': EXH, 'expo': EXH, 'livehouse': POP}


def load_json(name, default):
    p = os.path.join(DATA, name)
    if not os.path.exists(p):
        return default
    return json.load(open(p, encoding='utf-8'))


def nz(s):
    return re.sub(r'[\W_]+', '', (s or '')).lower()


def nk(s):
    """跨来源比对标题用：统一常见简称后再归一化"""
    return nz((s or '').replace('上海交响乐团', '上交'))


class VenueIndex:
    def __init__(self, cfg):
        self.venues = cfg['venues']
        self.pats = sorted(((p, v) for v in self.venues for p in v['patterns']), key=lambda x: -len(x[0]))
        self.by_name = {v['name']: v for v in self.venues}

    def match(self, *texts):
        hay = ' '.join(t for t in texts if t)
        for p, v in self.pats:
            if p in hay:
                return v
        return None


def classify(e, venue):
    """返回 (类别, 是否确定, 依据)"""
    title = e.get('title') or ''
    strong = [c for c, rx in STRONG if re.search(rx, title, re.I)]
    src = set()
    if e.get('raw_category') in MAOYAN_CORNER:
        src |= MAOYAN_CORNER[e['raw_category']]
    elif e.get('raw_category') in OLD_CAT:   # 豆瓣条目的 raw_category 是旧 7 类
        src |= OLD_CAT[e['raw_category']]
    for s in e.get('raw_cats') or []:
        src |= DOUBAN_SLUG.get(str(s), set())
    vprior = VENUE_PRIOR.get(venue['type']) if venue else None
    vtype = venue['type'] if venue else ''

    if strong:
        pick = strong[0]
        # 场馆类型能消解的歧义：Livehouse 里的「三重奏」是爵士，音乐厅里的「音乐节」是古典
        if vtype == 'livehouse' and pick == CLS:
            return POP, True, 'Livehouse 场馆'
        if vtype == 'concert_hall' and pick == CLS:
            return CLS, True, '标题+音乐厅'
        if src == {KID} and pick in (DRA, MUS, DAN):
            return KID, True, '平台标为亲子'
        if len(strong) > 1 and frozenset(strong[:2]) in AMBIGUOUS_PAIRS:
            return pick, False, f'标题同时像{strong[0]}和{strong[1]}'
        # 只有平台给出「唯一明确」的分类且与标题矛盾才复核；旧 7 类、豆瓣大类本来就粗，不足以否定标题
        if len(src) == 1 and pick not in src and pick != KID and not e.get('raw_category') in OLD_CAT:
            return pick, False, f'标题像{pick}，平台分类是{"/".join(sorted(src))}'
        return pick, True, '标题'
    if vprior:
        return vprior, True, '场馆类型'
    if len(src) == 1:
        return next(iter(src)), True, '平台分类'
    weak = [c for c, rx in WEAK if re.search(rx, title)]
    cand = [c for c in weak if not src or c in src]
    if cand:
        return cand[0], len(src) > 0, '标题弱信号' + ('+平台分类' if src else '')
    if src:
        return sorted(src, key=CATEGORIES.index)[0], False, '平台分类有多个可能'
    old = OLD_CAT.get(e.get('category'))
    if old:
        return sorted(old, key=CATEGORIES.index)[0], False, '仅旧分类'
    return DRA, False, '无任何信号'


def curated_event(item, kind, venue):
    vid = hashlib.md5((item.get('oid') or (item['title'] + item['venue'])).encode()).hexdigest()[:10]
    sd, ed = item.get('start_date'), item.get('end_date')
    date_raw = f"{sd} ~ {ed}" if ed and ed != sd else (sd or '')
    if (item.get('sessions') or 0) > 1:
        date_raw += f"（共 {item['sessions']} 场）"
    if not ed and kind == 'ex':
        date_raw = f"{sd} 起（闭展日期待官方公布）"
    return {
        'id': f'{kind}-{vid}', 'title': item['title'],
        'category': EXH if kind == 'ex' else item.get('category', POP),
        'venue': venue['name'] if venue else item['venue'], 'address': '',
        'lat': venue.get('lat') if venue else None, 'lng': venue.get('lng') if venue else None,
        'start_date': sd, 'end_date': ed or ('2027-12-31' if kind == 'ex' else sd),
        'start_time': item.get('start_time') or '', 'date_raw': date_raw,
        'price_text': item.get('price_text') or '',
        # 「价格未核实」在清单里记作 price_min=0 且非免费，不能当成 0 元参与价格筛选
        'price_min': item.get('price_min') if (item.get('price_min') or item.get('is_free')) else None,
        'price_max': None, 'is_free': bool(item.get('is_free')), 'followers': 0,
        'url': item.get('url'), 'source': 'official', 'tags': item.get('tags') or [],
        'tickets': {'search_kw': item['title'], 'official': item.get('url')},
        'note': item.get('note') or '', 'ticketing': item.get('ticketing') or '',
        'poster': item.get('poster_url') or '',
    }


def main():
    dry = '--dry' in sys.argv
    today = datetime.date.today().isoformat()
    cfg = load_json('venues.json', None)
    vidx = VenueIndex(cfg)
    noise = [re.compile(rx, re.I) for rx in cfg['noise']['title']]
    labels = load_json('labels.json', {})

    raw = open(IDX, encoding='utf-8').read()
    i = raw.find('window.__EVENTS__'); j = raw.find('=', i) + 1; k = raw.find('</script>', j)
    d = json.loads(raw[j:k].strip().rstrip(';').strip())
    evs = [e for e in d['events'] if e.get('source') != 'official']   # 策展条目每次重建
    n_in = len(evs)

    kept, dropped, review = [], defaultdict(list), []
    unmatched = Counter()
    for e in evs:
        lab = labels.get(str(e['id']), {})
        if lab.get('drop'):
            dropped['复核剔除'].append(e); continue
        v = vidx.match(e.get('venue'), e.get('address'), e.get('venue_canon'))
        if not v and not lab.get('category'):
            unmatched[e.get('venue_canon') or e.get('venue')] += 1
            dropped['场馆不在白名单'].append(e); continue
        hit = next((rx.pattern for rx in noise if rx.search(e.get('title') or '')), None)
        if hit and not lab.get('category'):
            dropped['噪声关键词'].append(e); continue
        if lab.get('category') in CATEGORIES:
            cat, sure, why = lab['category'], True, '复核标注'
        else:
            cat, sure, why = classify(e, v)
        e['category'] = cat
        if v:
            e['venue_grade'] = v['tier']
            e['venue_level'] = cfg['types'][v['type']]
            e['venue_canon'] = v['name']
        if not sure:
            review.append({'id': e['id'], 'title': e['title'], 'venue': e.get('venue_canon'),
                           'raw_category': e.get('raw_category'), 'guess': cat, 'why': why})
        kept.append(e)

    # 策展清单
    added, merged_official = Counter(), 0
    title_ix = {nk(e['title']): e for e in kept}
    for fname, kind in (('exhibitions.json', 'ex'), ('big_shows.json', 'bs'), ('official_shows.json', 'os')):
        for item in load_json(fname, []):
            if kind == 'os' and any(rx.search(item['title']) for rx in noise):
                added['官网噪声剔除'] += 1
                continue
            if (item.get('end_date') or item.get('start_date') or '9999') < today:
                continue
            if not item.get('start_date'):   # 开幕日期未公布的先不上站，等清单补全
                added['待定日期(未上站)'] += 1
                continue
            v = vidx.match(item.get('venue'))
            ce = curated_event(item, kind, v)
            # 主标题：去掉括号里的英文名、破折号/冒号后的副标题（平台标题常只写主标题或换了副标题）
            # 官网标题常带「丨上海交响乐团音乐季」这类后缀
            full = re.split(r'[丨｜|]', re.sub(r'[（(][^）)]*[）)]', '', item['title']))[0]
            cores = [c for c in {nk(full), nk(re.split(r'——|：|:', full)[0])} if len(c) >= 5]
            dup = title_ix.get(nk(item['title'])) or next(
                (x for t, x in title_ix.items() if any(c in t or t in c for c in cores)
                 and x.get('venue_canon') == (v['name'] if v else ce['venue'])), None)
            if dup:   # 平台上已经有：只补官方链接
                dup.setdefault('tickets', {})['official'] = item.get('url')
                merged_official += 1
                continue
            if kind == 'os':   # 官网条目没有可靠分类，和平台条目走同一套归类 + 复核
                lab = labels.get(ce['id'], {})
                if lab.get('drop'):
                    added['官网复核剔除'] += 1
                    continue
                if lab.get('category') in CATEGORIES:
                    ce['category'] = lab['category']
                else:
                    ce['category'], sure, why = classify({'title': item['title']}, v)
                    if not sure:
                        review.append({'id': ce['id'], 'title': item['title'], 'venue': ce['venue'],
                                       'raw_category': item.get('platform_category'), 'guess': ce['category'], 'why': why})
                title_ix[nk(item['title'])] = ce   # 同一官网清单内也去重
            if v:
                ce['venue_grade'], ce['venue_level'] = v['tier'], cfg['types'][v['type']]
                ce['venue_canon'] = v['name']
            else:
                ce['venue_grade'], ce['venue_level'] = 'A', '其他场馆'
            if ce['lat'] is None:   # 用同场馆已有活动的坐标
                same = [x for x in kept if x.get('venue_canon') == ce['venue'] and x.get('lat')]
                if same:
                    ce['lat'], ce['lng'] = same[0]['lat'], same[0]['lng']
            kept.append(ce); added[fname] += 1

    # 报告
    os.makedirs(LOGS, exist_ok=True)
    rep = [f'策展 {datetime.datetime.now():%Y-%m-%d %H:%M}', f'输入 {n_in} 条 → 保留 {len(kept)} 条']
    for r, xs in dropped.items():
        rep.append(f'剔除[{r}] {len(xs)} 条')
    rep.append(f'策展清单新增 {dict(added)}，与平台重复只补链接 {merged_official} 条')
    rep.append(f'待复核 {len(review)} 条 → data/review_queue.json')
    rep.append('分类: ' + str(dict(Counter(e['category'] for e in kept).most_common())))
    rep.append('级别: ' + str(dict(Counter(e.get('venue_grade') for e in kept).most_common())))
    rep.append('\n未进白名单的场馆（出现次数多的可考虑加入 venues.json）:')
    rep += [f'  {n:3d}  {name}' for name, n in unmatched.most_common(40)]
    for r, xs in dropped.items():
        if r == '场馆不在白名单':
            continue
        rep.append(f'\n[{r}] 样本:')
        rep += [f'  {x["title"][:40]} | {x.get("venue_canon")}' for x in xs[:30]]
    report = '\n'.join(rep)
    print(report)
    if dry:
        return

    json.dump(review, open(os.path.join(DATA, 'review_queue.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    open(os.path.join(LOGS, f'curate-{datetime.date.today():%Y%m%d}.txt'), 'w', encoding='utf-8').write(report)
    d['events'] = kept
    d['count'] = len(kept)
    d['categories'] = CATEGORIES
    src = Counter(e.get('source') for e in kept)
    d['source_stats'] = {**{s: src[s] for s in ('douban', 'maoyan', 'douban+maoyan', 'official')}, 'total': len(kept)}
    d['source'] = '猫眼演出 + 豆瓣同城·上海 + 美术馆/场馆官方信息'
    bak = IDX + '.bak-curate-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    open(bak, 'w', encoding='utf-8').write(raw)
    block = json.dumps(d, ensure_ascii=False, separators=(',', ':'))
    open(IDX, 'w', encoding='utf-8').write(raw[:j] + block + raw[k:])
    print(f'已写回 index.html（备份 {os.path.basename(bak)}）')


if __name__ == '__main__':
    main()
