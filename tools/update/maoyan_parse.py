#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""猫眼原始抓取 → 标准化条目（供 maoyan_merge.py 消费）

输入: /tmp/maoyan_data.json  (maoyan_crawl.py 产出)
输出: /tmp/maoyan_parsed.json

注意：maoyan_merge.py 读的是 maoyan_parsed.json，而 maoyan_crawl.py 只产出
maoyan_data.json，这一层转换原本缺失，是定时更新跑挂的原因之一。
"""
import json, re, datetime

SRC = '/tmp/maoyan_data.json'
OUT = '/tmp/maoyan_parsed.json'

# cornerDisplayName → 站内 7 类
CORNER_MAP = {
    '音乐会': '古典音乐会',
    '休闲展览': '艺术展览',
    '亲子演出': '亲子演出',
    '脱口秀': '喜剧',
    '相声': '喜剧',
    '戏曲艺术': '话剧/戏剧',
    '舞蹈芭蕾': '话剧/戏剧',
    '沉浸剧场': '话剧/戏剧',
    '演唱会': '演唱会',
    '音乐节': '演唱会',
    # Livehouse 巡演按演唱会归类（老大明确要求）
    'Livehouse': '演唱会',
    '话剧音乐剧': None,   # 需按标题细分
    '其他': None,         # 需按标题兜底
}


def title_category(t):
    """标题硬分类，用于 cornerDisplayName 无法直接映射时的兜底"""
    t = t or ''
    if re.search(r'双展|联展|巡回展|特展|大展|精品展|个展|巡展|艺术展|影像展|画展|雕塑展|'
                 r'摄影展|文物展|沉浸展|VR展|XR展|光影展|博览会|双年展|首展', t):
        return '艺术展览'
    if re.search(r'越剧|京剧|昆曲|昆剧|沪剧|评弹|豫剧|黄梅戏|粤剧|锡剧|甬剧|川剧|秦腔|'
                 r'评剧|梆子|折子戏|戏曲', t):
        return '话剧/戏剧'
    if '音乐剧' in t:
        return '音乐剧'
    if re.search(r'演唱会|巡回|巡演|巡唱|音乐节', t):
        return '演唱会'
    if re.search(r'音乐会|交响|独奏|钢琴|小提琴|大提琴|合唱|声乐|歌剧|打击乐|管弦|爱乐|'
                 r'古琴|琵琶|二胡|古筝', t):
        return '古典音乐会'
    if re.search(r'脱口秀|相声|单口|开放麦', t):
        return '喜剧'
    if re.search(r'儿童剧|亲子|小朋友|童话|绘本|木偶剧', t):
        return '亲子演出'
    if re.search(r'话剧|舞剧|歌剧|舞台剧|杂技|魔术|芭蕾|默剧|独角戏', t):
        return '话剧/戏剧'
    # 宽口径：沉浸式/环境式戏剧、悬疑推理剧（猫眼「话剧音乐剧」栏大量此类）
    if re.search(r'戏剧|悬疑|推理|惊悚|恐怖|沉浸|环境式|互动剧|放映', t):
        return '话剧/戏剧'
    if re.search(r'展|展览|博物馆|美术馆', t):
        return '艺术展览'
    return None


# 噪声：VR 密室 / 射击游戏体验，非演出非展览
# 注意「密室游戏/闯关/逃脱」才算噪声；「密室体验」常出现在沉浸式悬疑话剧标题里，不能误杀
NOISE = re.compile(r'VR|XR|密室游戏|密室闯关|密室逃脱|射击游戏|剧情游戏|模拟经营|沉浸体验LBE')


def is_noise(title, venue):
    t = f'{title or ""} {venue or ""}'
    return bool(NOISE.search(t))


def venue_category(venue):
    """场馆兜底分类（猫眼「其他」栏靠标题判不出来时用）"""
    v = venue or ''
    if re.search(r'博物馆|美术馆|艺术馆|画廊', v):
        return '艺术展览'
    if re.search(r'剧场|剧院|演艺|戏剧|音乐厅', v):
        return '话剧/戏剧'
    return None


def parse_dates(show_time_range):
    """解析 showTimeRange → (start_date, end_date)，格式 YYYY-MM-DD 或 None

    支持形态：
      2026.11.20 - 11.22      同年跨月
      2026.11.10 - 2027.03.01 跨年
      2026.10.30 / 10.31      多场次
      2026.11.15 19:00 周日   单场含时间
    """
    if not show_time_range:
        return None, None
    s = show_time_range.replace('年', '.').replace('月', '.').replace('日', ' ')
    full = re.findall(r'(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})', s)
    if full:
        y, m, d = full[0]
        start = f'{int(y):04d}-{int(m):02d}-{int(d):02d}'
        if len(full) >= 2:
            y2, m2, d2 = full[-1]
            end = f'{int(y2):04d}-{int(m2):02d}-{int(d2):02d}'
        else:
            # 第二段只有 MM.DD，年份继承（月份回退则视为跨年）
            tail = re.findall(r'(?<!\d)(\d{1,2})[.\-/](\d{1,2})(?!\d)', s)
            end = start
            if len(tail) >= 2:
                mm, dd = tail[-1]
                yy = int(y)
                if int(mm) < int(m):
                    yy += 1
                end = f'{yy:04d}-{int(mm):02d}-{int(dd):02d}'
        return start, end
    # 无年份的纯 MM.DD
    bare = re.findall(r'(\d{1,2})[.\-/](\d{1,2})', s)
    if bare:
        y = datetime.date.today().year
        m, d = bare[0]
        m2, d2 = bare[-1]
        start = f'{y:04d}-{int(m):02d}-{int(d):02d}'
        end = f'{y:04d}-{int(m2):02d}-{int(d2):02d}'
        return start, end
    return None, None


def parse_price(price_range, lowest_price):
    """priceRange '488-1688' → (min, max, text)"""
    text = (price_range or '').strip()
    lo = hi = None
    m = re.findall(r'(\d+(?:\.\d+)?)', text)
    if m:
        vals = [float(x) for x in m]
        lo, hi = min(vals), max(vals)
    elif lowest_price:
        lo = float(lowest_price)
    return lo, hi, text


def main():
    raw = json.load(open(SRC, encoding='utf-8'))
    out, no_cat, no_date, noise = [], 0, 0, 0

    for x in raw:
        pid = x.get('performanceId')
        if not pid:
            continue
        title = (x.get('name') or '').strip()
        if not title:
            continue
        venue_raw = (x.get('shopName') or '').strip()

        # 噪声过滤：VR 密室 / 游戏体验
        if is_noise(title, venue_raw):
            noise += 1
            continue

        corner = x.get('cornerDisplayName') or ''
        if corner == '话剧音乐剧':
            # 猫眼已归到话剧音乐剧栏，标题没「音乐剧」二字就按戏剧收，避免误杀
            cat = title_category(title) or '话剧/戏剧'
        elif corner == '其他':
            cat = (title_category(title) or venue_category(venue_raw)
                   or venue_category(x.get('address') or '') or '话剧/戏剧')
        else:
            cat = CORNER_MAP.get(corner) or title_category(title)
        if not cat:
            no_cat += 1
            continue

        start_date, end_date = parse_dates(x.get('showTimeRange'))
        if not start_date:
            no_date += 1
            continue

        lo, hi, ptext = parse_price(x.get('priceRange'), x.get('lowestPrice'))
        url = f'https://show.maoyan.com/detail/{pid}'

        out.append({
            'id': f'mv-{pid}',
            'mv_id': pid,
            'title': title,
            'venue': (x.get('shopName') or '').strip(),
            'address': (x.get('address') or '').strip(),
            'city_name': x.get('cityName') or '上海',
            'lat': float(x['lat']) if x.get('lat') else None,
            'lng': float(x['lng']) if x.get('lng') else None,
            'start_date': start_date,
            'end_date': end_date or start_date,
            'date_raw': x.get('showTimeRange') or '',
            'category': cat,
            'raw_category': corner,
            'source': 'maoyan',
            'poster_url': x.get('posterUrl') or '',
            'price_min': lo,
            'price_max': hi,
            'price_text': ptext,
            'is_free': bool(lo is not None and lo == 0),
            'url': url,
            'followers': x.get('intendedNum') or 0,
        })

    json.dump(out, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False)
    from collections import Counter
    print(f'原始 {len(raw)} → 有效 {len(out)} 条')
    print(f'  丢弃：噪声 {noise} | 无分类 {no_cat} | 无日期 {no_date}')
    print('分类分布:', dict(Counter(e["category"] for e in out).most_common()))
    print(f'已写出 {OUT}')


if __name__ == '__main__':
    main()
