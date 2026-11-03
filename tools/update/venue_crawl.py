#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""旗舰场馆官网抓取 → data/official_shows.json

补的是「场馆自己卖票、平台上没有」的场次，也给平台已有的场次补官方链接。
每个场馆一个 fetch_* 函数，返回统一结构的列表；某家失败不影响其他家（保留它上次的数据）。

  上海大剧院       thvendor 平台 querySchedulesByDate（GET，需 cmpappkey 头）
  上海交响乐团音乐厅 thvendor 平台 homeProgramList（POST，需 cmpappkey 头，带海报）
  上海东方艺术中心   platform-backend dongyi-products/{年}/{月}（需 Channel/Theater 头）

接口都是官网页面自己在用的公开接口，每周只请求十几次。
用法：python3 venue_crawl.py
"""
import os, re, json, datetime, urllib.request, urllib.parse
from collections import defaultdict

SITE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(SITE, 'data', 'official_shows.json')
UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120.0 Safari/537.36')
DAYS_AHEAD = 120


def get_json(url, headers, data=None):
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers={'User-Agent': UA, 'Accept': 'application/json', **headers})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.load(r)


def months(start, end):
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def clean_title(t):
    t = re.sub(r'（\d+）$', '', t or '').strip()           # 大剧院内部编号「（122723）」
    return t


def group_sessions(rows, venue, url_of, poster_of=lambda k: None):
    """rows: [(key, title, date, time)] → 每个节目一条，起止日期取所有场次的最早/最晚"""
    g = defaultdict(list)
    titles = {}
    for key, title, date, time in rows:
        g[key].append((date, time))
        titles[key] = title
    out = []
    for key, ss in g.items():
        ss.sort()
        out.append({
            'oid': f'{venue}:{key}', 'title': titles[key], 'venue': venue,
            'start_date': ss[0][0], 'end_date': ss[-1][0], 'start_time': ss[0][1] or None,
            'sessions': len(ss), 'url': url_of(key), 'poster_url': poster_of(key),
        })
    return out


def fetch_sgt(today, end):
    H = {'Referer': 'https://www.shgtheatre.com/shtheatre/index.html', 'cmpappkey': 'grandtheatrepc', 'lang': 'zh-CN'}
    rows = []
    for y, m in months(today, end):
        last = (datetime.date(y + (m == 12), m % 12 + 1, 1) - datetime.timedelta(days=1)).day
        url = ('https://www.shgtheatre.com/thvendor/programcalendar/querySchedulesByDate.xhtml?'
               + urllib.parse.urlencode({'dateFrom': f'{y}-{m:02d}-01', 'dateTo': f'{y}-{m:02d}-{last:02d}',
                                         'showSite': 'pcCalendar'}))
        d = get_json(url, H)
        if not d.get('success'):
            raise RuntimeError(d.get('msg'))
        for x in d.get('data') or []:
            rows.append((x['programId'], clean_title(x.get('fullCnName') or x.get('programName')),
                         x['playDate'], x.get('playTime')))
    return group_sessions(rows, '上海大剧院',
                          lambda k: f'https://www.shgtheatre.com/shtheatre/index.html#/ticket/detail/{k}')


def fetch_shso(today, end):
    H = {'Referer': 'https://www.shsymphony.cn/symphonypc/index.html', 'cmpappkey': 'shsymphonyPC', 'lang': 'zh-CN'}
    out, page = [], 1
    while True:
        d = get_json('https://www.shsymphony.cn/thvendor/symphony/program/homeProgramList.xhtml', H,
                     {'showSite': 'pcHome', 'pageNo': page, 'pageSize': 100})
        if not d.get('success'):
            raise RuntimeError(d.get('msg'))
        res = d['data']['resultList'] or []
        for x in res:
            sd, ed = (x.get('startTime') or '')[:10], (x.get('endTime') or '')[:10]
            out.append({
                'oid': f'上海交响乐团音乐厅:{x["id"]}',
                'title': x.get('fullCnName') or x.get('cnName'),
                'venue': x.get('stadiumName') or '上海交响乐团音乐厅',
                'start_date': sd, 'end_date': ed or sd, 'start_time': (x.get('startTime') or '')[11:16] or None,
                'sessions': 1, 'platform_category': x.get('category'),
                'price_min': x.get('minPrice'),
                'url': 'https://www.shsymphony.cn/symphonypc/index.html',
                'poster_url': x.get('verticalPoster') or x.get('horizontalPoster'),
            })
        if page * 100 >= d['data']['page']['rowTotal'] or not res:
            break
        page += 1
    return [o for o in out if o['start_date'] and o['start_date'] <= end.isoformat()]


def fetch_shoac(today, end):
    H = {'Referer': 'https://www.shoac.com.cn/', 'Channel': 'theatre_pc', 'Theater': '1323', 'Flagship-Store': 'true'}
    rows = []
    for y, m in months(today, end):
        d = get_json(f'https://www.shoac.com.cn/platform-backend/good/theater/dongyi-products/{y}/{m}', H)
        if not d.get('success'):
            raise RuntimeError(d.get('errors'))
        for day in d.get('data') or []:
            for p in day.get('products') or []:
                rows.append((p['productId'], p.get('productNameShort'), day['date'], p.get('showTime')))
    # 东艺详情页用的是另一套 projectId，拿不到，链接给官网首页（首页有按日演出日历）
    return group_sessions(rows, '上海东方艺术中心', lambda k: 'https://www.shoac.com.cn/#/')


FETCHERS = [('上海大剧院', fetch_sgt), ('上海交响乐团音乐厅', fetch_shso), ('上海东方艺术中心', fetch_shoac)]


def main():
    today = datetime.date.today()
    end = today + datetime.timedelta(days=DAYS_AHEAD)
    old = json.load(open(OUT, encoding='utf-8')) if os.path.exists(OUT) else []
    result = []
    for venue, fn in FETCHERS:
        try:
            items = [x for x in fn(today, end) if (x['end_date'] or x['start_date']) >= today.isoformat()]
            print(f'{venue}: {len(items)} 个节目')
        except Exception as e:
            items = [x for x in old if x['venue'] == venue and (x['end_date'] or x['start_date']) >= today.isoformat()]
            print(f'!! {venue} 抓取失败（{type(e).__name__}: {e}），沿用上次的 {len(items)} 条')
        result += items
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(result, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'共 {len(result)} 条 → {os.path.relpath(OUT, SITE)}')


if __name__ == '__main__':
    main()
