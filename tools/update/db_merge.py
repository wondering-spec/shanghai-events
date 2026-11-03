#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""豆瓣新数据 + 老数据 合并 → 生成新 __EVENTS__（先分析，--write 才写回）"""
import os, re, json, sys, math, unicodedata, datetime

SITE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
IDX = os.path.join(SITE, 'index.html')
# 自动取当天，避免硬编码日期导致定时任务过期过滤失效
TODAY = datetime.date.today().isoformat()

# ============ 噪声过滤 ============
# 商贸/行业展会（非文化艺术）
TRADE_INDUSTRY = (r'跨境|电商|外贸|货运|物流|供应链|半导体|射频|天线|微波|钢丝绳|吊索具|安防|化工|'
                  r'医药化工|余热|智能家居|消费电子|家电|物联网|移民|康养|城市轨道|轨道交通|'
                  r'流体机械|阀门|液冷|智算|工业智算|金属|钢铁|稀有金属|食品|露营|汽车|机械|'
                  r'建材|家居|母婴|宠物|农业|五金|照明|包装|印染|纺织|橡塑|焊接|铸造|锻造|'
                  r'传感器|连接器|电源|储能|光伏|风电|环保设备|泵阀|轴承|模具|3D打印|激光|'
                  r'轴承|仪器仪表|实验室|洁净|防静电|工业')
TRADE_WORDS = r'展览会|博览会|交易会|展销会|展会|峰会|论坛|大会|招商|招展|采购会|产业展|邀请函'
# 户外/旅行/团建
TRAVEL = (r'徒步|登山|漂流|溯溪|露营|古镇|赏花|赏秋|赏红枫|赏樱|海岛|1天活动|2天1晚|一日游|'
          r'两日游|自驾|骑行|民宿|温泉|滑雪|玩水|采摘|农家|穿越|古村|土楼|篁岭|沙滩|徒步|'
          r'画中游|郊游|春秋游|短途|跟团|自由行|机票|酒店|度假|1日线|\d日线|品蟹|大闸蟹|'
          r'莲花岛|阳澄湖|赏枫|观鸟|露营|徒步|踏青|赏梅|赏荷|油菜花')
# 运动/社交
SOCIAL = (r'^打球|约打球|羽毛球|篮球|足球|桌游|交友|相亲|聚会|聚餐|探店|跑步|健身|瑜伽|游泳|'
          r'狼人杀|飞盘|保龄球|台球|骑行团|读书会|相亲会')
# 测试/垃圾
JUNK = r'测试|test|demo|分销|样例|示例|占位'


def is_noise(title, venue=''):
    t = title or ''
    if re.search(JUNK, t, re.I):
        return 'junk'
    if re.search(TRADE_WORDS, t) and re.search(TRADE_INDUSTRY, t):
        return 'trade'
    # 纯行业展会（无艺术/文化/设计/创意修饰）
    if re.search(TRADE_WORDS, t) and not re.search(r'艺术|工艺|摄影|绘画|设计|文化|创意|时装|珠宝|动漫|潮玩|IP', t):
        if re.search(r'国际|中国|上海|全球|亚洲|产业|行业|技术|设备|材料|系统|解决方案|装备', t):
            return 'trade2'
    if re.search(TRAVEL, t):
        return 'travel'
    if re.search(SOCIAL, t):
        return 'social'
    return None


# ============ 分类映射 ============
def category_of(cats, title, venue=''):
    """豆瓣分类 slug → 原 7 类体系

    venue 用于纠正 Livehouse 误判：豆瓣把「THE PEARL livehouse 珍珠剧场」这类场地
    的演出同时归到 drama，若只看 slug 会把致敬音乐会/摇滚现场全判成话剧。
    """
    s = set(cats)
    t = title or ''
    v = venue or ''

    if 'exhibition' in s:
        return '艺术展览'
    if '1102' in s or '音乐剧' in t:
        return '音乐剧'
    if 'kids' in s:
        return '亲子演出'
    if 'comedy' in s or '2201' in s or '2202' in s:
        return '喜剧'
    # 强音乐信号拦截：放在戏剧子类与 drama 之前，纠正 Livehouse 音乐演出被判成话剧
    # 注意「致敬」必须绑定演出类型词，否则「致敬阿加莎悬疑剧」会被误判成演唱会
    if re.search(r'演唱会|巡回|巡演|巡唱|歌友会|音乐节|'
                 r'致敬音乐会|致敬演唱会|致敬演出|TRIBUTE\s*CONCERT|TRIBUTE\s*SHOW|'
                 r'摇滚|乐队|民谣|说唱|嘻哈|电音|\bDJ\b|'
                 r'livehouse|Live\s*House', t + ' ' + v, re.I):
        return '演唱会'
    if re.search(r'音乐会|交响|钢琴|小提琴|大提琴|弦乐|室内乐|合唱|声乐|独奏|爵士|'
                 r'古琴|琵琶|二胡|古筝|民乐', t):
        return '古典音乐会'
    if '1003' in s or '1004' in s or re.search(r'演唱会|巡回|巡演|歌友会|音乐节', t):
        return '演唱会'
    if '1001' in s:
        return '古典音乐会'
    if '1002' in s:
        return '古典音乐会'
    if s & {'1101', '1103', '1104', '1105', '1106'}:
        return '话剧/戏剧'
    if 'drama' in s:
        return '话剧/戏剧'
    if 'music' in s:
        # 音乐父类兜底
        if re.search(r'演唱会|巡回|巡演|音乐节|乐队|摇滚|民谣|说唱|嘻哈|Livehouse|live', t, re.I):
            return '演唱会'
        return '古典音乐会'
    return None


# ============ 标签规则 ============
TAG_RULES = [
    (['音乐剧'], '音乐剧'),
    (['话剧'], '话剧'),
    (['舞剧', '舞蹈', '芭蕾'], '舞剧/舞蹈'),
    (['歌剧'], '歌剧'),
    (['脱口秀', '单口', '开放麦', '喜剧大会'], '脱口秀'),
    (['相声', '快板', '评书'], '喜剧/搞笑'),
    (['喜剧', '搞笑', '幽默', '开心麻花', '爆笑', '滑稽'], '喜剧/搞笑'),
    (['爵士', 'jazz', 'JZ'], '爵士'),
    (['钢琴', 'piano'], '钢琴'),
    (['小提琴', '大提琴', '弦乐四重奏', '弦乐'], '小提琴'),
    (['古琴', '琵琶', '二胡', '古筝', '民乐', '国风', '京剧', '昆曲', '越剧', '沪剧', '评弹', '戏曲', '民族'],
     '国风/民乐'),
    (['合唱', '声乐', '男高音', '女高音', '独唱', '颂'], '声乐/合唱'),
    (['交响', '爱乐', '协奏', '奏鸣', '室内乐', '莫扎特', '贝多芬', '巴赫', '柴可夫斯基', '肖邦',
      '拉赫玛尼诺夫', '德彪西', '勃拉姆斯'], '古典'),
    (['沉浸', 'VR', 'XR', 'MR', '互动', '密室', '全感', '剧本'], '沉浸式'),
    (['悬疑', '惊悚', '推理', '谋杀', '恐怖'], '悬疑/惊悚'),
    (['数字', 'AI', '光影', '新媒体', '投影', '全息', '数字艺术'], '数字/AI艺术'),
    (['绘画', '油画', '雕塑', '水墨', '版画', '素描', '工笔', '插画'], '绘画/雕塑'),
    (['当代艺术', '装置', '先锋'], '当代艺术'),
    (['摄影', '胶片', '影像'], '摄影'),
    (['设计', '建筑'], '设计/建筑'),
    (['文物', '考古', '遗产', '汉墓', '青铜', '瓷器', '古籍', '抄写', '印刷', '文艺复兴', '历史'],
     '文物/历史'),
    (['儿童', '亲子', '小朋友', '童话', '绘本', '动画', '萌', '宝宝'], '儿童/亲子'),
    (['爱乐乐团', '交响乐团', '国家大剧院', '大师', '名家', '首席', '国际乐团'], '大师/名团'),
]
CAT_TAG_FALLBACK = {
    '音乐剧': '音乐剧', '话剧/戏剧': '话剧', '亲子演出': '儿童/亲子',
    '喜剧': '喜剧/搞笑', '古典音乐会': '古典', '艺术展览': '当代艺术', '演唱会': '声乐/合唱',
}


def build_tags(cats, title, category):
    s = set(cats); t = title or ''
    tags = []
    # 1) 豆瓣子类
    sub_map = {'1101': '话剧', '1102': '音乐剧', '1103': '舞剧/舞蹈', '1104': '歌剧', '1105': '国风/民乐',
               '2201': '脱口秀', '2202': '喜剧/搞笑', '1002': '古典'}
    for k, v in sub_map.items():
        if k in s and v not in tags:
            # 分类已判为音乐/演唱会时，豆瓣「话剧」子类标签不再适用
            # （珍珠剧场这类 Livehouse 常被豆瓣挂到 1101）
            if k == '1101' and category != '话剧/戏剧':
                continue
            tags.append(v)
    # 2) 标题规则
    for kws, tag in TAG_RULES:
        if tag in tags:
            continue
        for kw in kws:
            if kw.lower() in t.lower():
                tags.append(tag)
                break
    # 3) 兜底
    if not tags and category in CAT_TAG_FALLBACK:
        tags.append(CAT_TAG_FALLBACK[category])
    return tags[:5]


# ============ 场馆分级 ============
S_VENUES = ["上海东方艺术中心", "上海久事美术馆", "上海保利大剧院", "上海共舞台", "上海博物馆",
            "上海国际舞蹈中心", "上海大剧院", "上海展览中心", "上海市历史博物馆", "上海当代艺术博物馆",
            "上海文化广场", "上海民生现代美术馆", "上海油罐艺术中心", "上海西岸大剧院", "上海话剧艺术中心",
            "中华艺术宫", "中国大戏院", "临港演艺中心", "久事·上海商城剧院", "九棵树（上海）未来艺术中心",
            "交通银行前滩31演艺中心", "兰心大戏院", "凯迪拉克·上海音乐厅", "北外滩友邦大剧院",
            "大零号湾文化艺术中心", "天蟾逸夫舞台", "宛平剧院", "宝龙美术馆", "捷豹上海交响音乐厅",
            "浦东美术馆", "美琪大戏院", "茉莉花剧场", "西岸美术馆", "长江剧场", "黄浦剧场",
            "上海交响乐团音乐厅", "上音歌剧院", "东方艺术中心", "上海音乐厅", "艺海剧院", "云峰剧院",
            "人民大舞台", "上海大世界", "星空间", "FANCL艺术中心", "余德耀美术馆", "龙美术馆",
            "震旦博物馆", "喜玛拉雅美术馆", "明当代美术馆", "OCAT上海馆", "昊美术馆", "复星艺术中心",
            "UCCA Edge", "上海自然博物馆", "上海科技馆", "刘海粟美术馆", "程十发美术馆"]
B_KEYS = ['广场', '商场', '购物中心', '大悦城', '商业中心', '商业广场', 'SK大厦', '中心店', '店',
          '集市', '街区', '乐园', '俱乐部', '生活馆', '空间', 'L空间', '中心', '大厦', '城']
S_KEYS = ['大剧院', '音乐厅', '美术馆', '博物馆', '艺术中心', '文化中心', '艺术馆', '大戏院',
          '剧院', '演艺中心', '交响音乐厅', '剧场', '舞台', '展览中心', '文化广场']


def venue_grade_of(venue):
    v = (venue or '').replace('演出现场', '').strip()
    for s in S_VENUES:
        if s in v:
            return 'S'
    if any(k in v for k in ['音乐厅', '大剧院', '美术馆', '博物馆', '艺术馆', '大戏院', '演艺中心',
                            '交响音乐厅', '艺术中心', '文化中心', '展览中心', '舞台']):
        return 'S'
    if any(k in v for k in ['LIVE', 'Live', 'live', 'Livehouse', 'MAO', '育音堂', '瓦肆', '摩登天空',
                            'LAB', 'HERTZ', '小剧场', '空间', '剧场', '剧院']):
        # 小剧场 / livehouse → A
        for bk in B_KEYS:
            if bk in v:
                return 'B'
        return 'A'
    for bk in B_KEYS:
        if bk in v:
            return 'B'
    return 'A'


LEVEL_TEXT = {'S': '大型专业场馆', 'A': '中型剧场', 'B': '商场/商业空间'}


def canon_of(venue):
    """场馆规范名：从 venue 串里取场馆名部分"""
    v = venue or ''
    v = re.sub(r'^上海\s*', '', v)
    v = re.sub(r'^[\u4e00-\u9fa5]{2,4}区\s*', '', v)
    v = re.sub(r'\s+', ' ', v).strip()
    # 场馆名一般是第一段（地址前）
    m = re.match(r'^(.{2,28}?)(?=\s|$)', v)
    name = m.group(1) if m else v
    return name.strip()


def district_of(venue):
    m = re.search(r'上海\s*([\u4e00-\u9fa5]{2,4}区)', venue or '')
    return m.group(1) if m else ''


def parse_fee(txt):
    t = (txt or '').strip()
    if not t:
        return '', None, None, False
    if '免费' in t:
        return '免费', 0.0, 0.0, True
    nums = re.findall(r'\d+(?:\.\d+)?', t)
    if not nums:
        return t, None, None, False
    if len(nums) >= 2 and re.search(r'\d\s*[-~～到至]\s*\d', t):
        lo, hi = float(nums[0]), float(nums[-1])
        return f'{fmt(lo)}-{fmt(hi)}', lo, hi, False
    lo = float(nums[0])
    if lo == 0:
        return '免费', 0.0, 0.0, True
    return f'{fmt(lo)}元起', lo, None, False


def fmt(x):
    return str(int(x)) if x == int(x) else f'{x:g}'


# ============ 地铁最近站 ============
def load_metro(raw):
    i = raw.find('window.__METRO__')
    if i < 0:
        return None
    j = raw.find('{', i)
    depth = 0
    for x in range(j, len(raw)):
        if raw[x] == '{':
            depth += 1
        elif raw[x] == '}':
            depth -= 1
            if depth == 0:
                return json.loads(raw[j:x+1])
    return None


def hdist(a, b, c, d):
    R = 6371.0
    dp = math.radians(c-a); dl = math.radians(d-b)
    x = math.sin(dp/2)**2 + math.cos(math.radians(a))*math.cos(math.radians(c))*math.sin(dl/2)**2
    return 2*R*math.asin(math.sqrt(x))


def nearest_metro(metro, lat, lng, maxkm=2.5):
    if lat is None or lng is None or not metro:
        return '', []
    best = []
    for line, sts in metro['lines'].items():
        for st in sts:
            nm, sla, slo = st[0], st[1], st[2]
            d = hdist(lat, lng, sla, slo)
            if d <= maxkm:
                best.append((d, nm, line))
    if not best:
        return '', []
    best.sort()
    nm = best[0][1]
    lines = sorted(set(l for _, n, l in best if n == nm))
    # 同名站可能多线路
    return nm, lines


def main():
    write = '--write' in sys.argv
    raw = open(IDX, encoding='utf-8').read()
    i = raw.find('window.__EVENTS__'); j = raw.find('=', i)+1; k = raw.find('</script>', j)
    old_data = json.loads(raw[j:k].strip().rstrip(';').strip())
    old = old_data['events']
    metro = load_metro(raw)
    print(f"老数据 {len(old)} 条 | 地铁线路 {len(metro['lines']) if metro else 0} 条")

    new = json.load(open('/tmp/db_parsed.json'))
    print(f"新抓豆瓣 {len(new)} 条")

    old_by_id = {str(e['id']): e for e in old}
    merged = {}
    stats = {'refresh': 0, 'add': 0, 'skip_nocat': 0, 'skip_geo': 0, 'skip_noise': 0}
    noise_kinds = {}

    for r in new:
        nz = is_noise(r['title'], r.get('venue_raw', ''))
        if nz:
            stats['skip_noise'] += 1
            noise_kinds[nz] = noise_kinds.get(nz, 0) + 1
            continue
        cat = category_of(r['cats'], r['title'], r.get('venue_raw', ''))
        if not cat:
            stats['skip_nocat'] += 1
            continue
        lat = float(r['lat']) if r.get('lat') else None
        lng = float(r['lng']) if r.get('lng') else None
        if lat is None or lng is None:
            stats['skip_geo'] += 1
            continue
        eid = str(r['id'])
        o = old_by_id.get(eid)
        fee_text, pmin, pmax, free = parse_fee(r.get('fee'))
        sd = (r.get('start') or '')[:10]
        ed = (r.get('end') or '')[:10]
        st = (r.get('start') or '')[11:16] or '00:00'
        if o:
            # 刷新可变字段
            e = dict(o)
            e['title'] = r['title']
            e['venue'] = r['venue_raw'] or o.get('venue')
            e['lat'], e['lng'] = lat, lng
            e['start_date'], e['end_date'], e['start_time'] = sd, ed, st
            e['date_raw'] = r.get('date_raw') or o.get('date_raw')
            if fee_text:
                e['price_text'], e['price_min'], e['price_max'], e['is_free'] = fee_text, pmin, pmax, free
            e['followers'] = r.get('wish') or e.get('followers') or 0
            if r.get('poster_url'):
                e['poster_url'] = r['poster_url']
            e['merged_from'] = o.get('merged_from')
            stats['refresh'] += 1
        else:
            e = {'id': eid, 'title': r['title'], 'category': cat, 'raw_category': cat,
                 'venue': r['venue_raw'], 'address': '', 'lat': lat, 'lng': lng,
                 'start_date': sd, 'end_date': ed, 'start_time': st,
                 'date_raw': r.get('date_raw') or '', 'price_text': fee_text,
                 'price_min': pmin, 'price_max': pmax, 'is_free': free,
                 'followers': r.get('wish') or 0,
                 'poster_url': r.get('poster_url') or '',
                 'url': f"https://www.douban.com/event/{eid}/",
                 'source': 'douban', 'city_name': '上海',
                 'tags': build_tags(r['cats'], r['title'], cat),
                 'raw_cats': [c for c in r['cats']],
                 'merged_from': None}
            stats['add'] += 1
        # 场馆分级 / 区域 / 地铁
        vg = venue_grade_of(e.get('venue'))
        e['venue_grade'], e['venue_level'] = vg, LEVEL_TEXT[vg]
        e['venue_canon'] = canon_of(e.get('venue'))
        e['district'] = district_of(e.get('venue')) or e.get('district') or ''
        if vg != 'B':
            nm, lines = nearest_metro(metro, lat, lng)
            e['nearest_metro'], e['metro_lines'] = nm, lines
        else:
            e.setdefault('nearest_metro', ''); e.setdefault('metro_lines', [])
        # 票务入口（沿用生成规则）
        kw = e['title']
        e['tickets'] = {
            'search_kw': kw,
            'damai': 'https://search.damai.cn/search.htm?keyword=' + quote(kw),
            'maoyan': 'https://show.maoyan.com/list/0',
            'bing': 'https://cn.bing.com/search?q=' + quote(kw + ' 上海 购票'),
            'db': e['url'],
            'nav': 'https://uri.amap.com/search?keyword=' + quote(e.get('venue') or '') + '&city=%E4%B8%8A%E6%B5%B7',
        }
        e['poster'] = f"posters/{eid}.webp"
        merged[eid] = e

    # 保留老数据中未过期的猫眼条目（豆瓣没覆盖的）；豆瓣抓取提前收工时，老的豆瓣条目也保留
    partial = os.path.exists('/tmp/db_crawl/_PARTIAL')
    if partial:
        print("豆瓣抓取不完整：未刷新到的老豆瓣条目也保留")
    keep_maoyan = 0
    old_noise = 0
    for e in old:
        eid = str(e['id'])
        if eid in merged:
            continue
        src = (e.get('source') or '')
        if 'maoyan' not in src and not (partial and src == 'douban'):
            continue
        if (e.get('end_date') or '9999') < TODAY:
            continue
        if is_noise(e.get('title'), e.get('venue')):
            old_noise += 1
            continue
        merged[eid] = e
        keep_maoyan += 1

    # 过滤已过期
    final = [e for e in merged.values() if (e.get('end_date') or '9999') >= TODAY]
    expired = len(merged) - len(final)

    print(f"\n统计: 刷新 {stats['refresh']} | 新增 {stats['add']} | 保留猫眼 {keep_maoyan}")
    print(f"  跳过(无法归类) {stats['skip_nocat']} | 跳过(无坐标) {stats['skip_geo']} | 跳过(噪声) {stats['skip_noise']} {noise_kinds}")
    print(f"  老数据中过滤掉的噪声(猫眼) {old_noise}")
    print(f"  合并池 {len(merged)} → 去掉过期 {expired} → 最终 {len(final)}")

    from collections import Counter
    print("\n=== 新旧 category 对比 ===")
    oc = Counter(e.get('category') for e in old)
    nc = Counter(e.get('category') for e in final)
    for c in sorted(set(list(oc)+list(nc))):
        print(f"  {c:10s} {oc.get(c,0):5d} → {nc.get(c,0):5d}")
    print("\n=== 新数据 source ===", Counter(e.get('source') for e in final).most_common())
    print("=== 场馆级别 ===", Counter(e.get('venue_grade') for e in final).most_common())
    print("\n=== 新增样本 ===")
    for e in final[:0]:
        pass
    added = [e for e in final if str(e['id']) not in old_by_id]
    for e in added[:8]:
        print(f"  {e['title'][:40]} | {e['category']} | {e.get('venue')[:30]} | tags={e.get('tags')}")
    print("\n=== tags 分布 ===")
    tc = Counter(t for e in final for t in (e.get('tags') or []))
    print("  ", tc.most_common(12))
    ntg = sum(1 for e in final if not e.get('tags'))
    print(f"  无标签: {ntg} ({ntg/len(final)*100:.0f}%)")
    nm = sum(1 for e in final if e.get('nearest_metro'))
    print(f"  有最近地铁: {nm} ({nm/len(final)*100:.0f}%)")

    json.dump(final, open('/tmp/merged_events.json', 'w'), ensure_ascii=False)

    if not write:
        print("\n[分析模式] 未写回。加 --write 才写入。")
        return


def quote(s):
    from urllib.parse import quote as q
    return q(s or '')


if __name__ == '__main__':
    main()
