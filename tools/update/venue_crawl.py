#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""旗舰场馆官网抓取 → data/official_shows.json

补的是「场馆自己卖票、平台上没有」的场次，也给平台已有的场次补官方链接。
每个场馆一个 fetch_* 函数，返回统一结构的列表；某家失败不影响其他家（保留它上次的数据）。

  上海大剧院       thvendor 平台 querySchedulesByDate（GET，需 cmpappkey 头）
  上海交响乐团音乐厅 thvendor 平台 homeProgramList（POST，需 cmpappkey 头，带海报）
  上音歌剧院       thvendor 平台 getHotProgramList（POST，需 cmpappkey 头，带海报和票价）
  上海东方艺术中心   platform-backend dongyi-products/{年}/{月}（需 Channel/Theater 头）
  上海文化广场      shcstheatre.com 节目列表页 HTML（服务端渲染，带海报/票价/日期）
                   注意 shculturesquare.com 不是官网（域名已被博彩站占用）

接口都是官网页面自己在用的公开接口，每周只请求十几次。
用法：python3 venue_crawl.py
"""
import os, re, json, time, datetime, urllib.request, urllib.parse
from collections import defaultdict

SITE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(SITE, 'data', 'official_shows.json')
UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120.0 Safari/537.36')
DAYS_AHEAD = 120


def get_json(url, headers, data=None, tries=3):
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers={'User-Agent': UA, 'Accept': 'application/json', **headers})
    for t in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.load(r)
        except OSError:   # SSL 断连 / 超时：官网偶发，稍等重试
            if t == tries - 1:
                raise
            time.sleep(3 * (t + 1))


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


def thvendor_programs(api, headers, form, venue, url_of, end):
    """thvendor 平台（大剧院/上交/上音共用的票务系统）的节目列表接口，翻页取全"""
    out, page = [], 1
    while True:
        d = get_json(api, headers, {**form, 'pageNo': page, 'pageSize': 100})
        if not d.get('success'):
            raise RuntimeError(d.get('msg'))
        data = d.get('data') or []
        # 上交返回 {page, resultList} 分页结构，上音返回的直接就是列表
        res = data if isinstance(data, list) else (data.get('resultList') or [])
        for x in res:
            sd, ed = (x.get('startTime') or '')[:10], (x.get('endTime') or '')[:10]
            pmin, pmax = x.get('minPrice'), x.get('maxPrice')
            out.append({
                'oid': f'{venue}:{x["id"]}',
                'title': x.get('fullCnName') or x.get('cnName'),
                'venue': venue,
                'start_date': sd, 'end_date': ed or sd, 'start_time': (x.get('startTime') or '')[11:16] or None,
                'sessions': 1, 'platform_category': x.get('category'),
                'price_min': pmin,
                'price_text': (f'{pmin:g}-{pmax:g}元' if pmin and pmax and pmax != pmin else (f'{pmin:g}元' if pmin else '')),
                'url': url_of(x['id']),
                'poster_url': x.get('verticalPoster') or x.get('horizontalPoster'),
            })
        if isinstance(data, list) or page * 100 >= data['page']['rowTotal'] or not res:
            break
        page += 1
    return [o for o in out if o['start_date'] and o['start_date'] <= end.isoformat()]


def fetch_shso(today, end):
    H = {'Referer': 'https://www.shsymphony.cn/symphonypc/index.html', 'cmpappkey': 'shsymphonyPC', 'lang': 'zh-CN'}
    return thvendor_programs('https://www.shsymphony.cn/thvendor/symphony/program/homeProgramList.xhtml', H,
                             {'showSite': 'pcHome'}, '上海交响乐团音乐厅',
                             lambda k: 'https://www.shsymphony.cn/symphonypc/index.html', end)


def fetch_syoh(today, end):
    H = {'Referer': 'https://www.syoperahouse.com/sytheatre/index.html', 'cmpappkey': 'syoperahouseh5'}
    return thvendor_programs('https://www.syoperahouse.com/thvendor/ticket/program/getHotProgramList.xhtml', H,
                             {'showSite': 'pchome'}, '上音歌剧院',
                             lambda k: f'https://www.syoperahouse.com/sytheatre/index.html#/ticket/detail/{k}', end)


def fetch_shcs(today, end):
    req = urllib.request.Request('https://www.shcstheatre.com/Program/programList.aspx', headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=25) as r:
        html = r.read().decode('utf-8', 'ignore')
    out = []
    # 每个节目一个块：海报 → 标题链接 → 类型/地点/日期/时间/价格
    for blk in re.split(r"<div class='col-md-12[^']*'>", html)[1:]:
        m = re.search(r"ProgramDetails\.aspx\?[^']*?id=(\d+)'>([^<]+)</a></h2>", blk)
        if not m:
            continue
        pid, title = m.group(1), m.group(2).strip()
        field = lambda name: (re.search(name + r"[^：]*：(?:</span><span[^>]*>)?([^<]+)", blk) or [None, ''])[1].strip()
        dates = re.findall(r'(\d{4})\.(\d{1,2})\.(\d{1,2})', field('日期 Date'))
        if not dates:
            continue
        iso = lambda t: f'{t[0]}-{int(t[1]):02d}-{int(t[2]):02d}'
        place = field('地点 Venue').replace('&nbsp;', ' ')
        price = field('价格 Price')
        pm = re.match(r'(\d+)', price)
        poster = re.search(r"<img src='(https://pic\.shcstheatre\.com/[^']+)'", blk)
        out.append({
            'oid': f'上海文化广场:{pid}', 'title': title,
            'venue': '上海文化广场' + (' ' + place.replace('上海文化广场', '').strip() if place else ''),
            'start_date': iso(dates[0]), 'end_date': iso(dates[-1]),
            'start_time': (field('时间 Time').split(',')[0] or None), 'sessions': 1,
            'platform_category': field('类型 Category').replace('&nbsp;', ' ').split(' ')[0],
            'price_min': float(pm.group(1)) if pm else None, 'price_text': price,
            'url': f'https://www.shcstheatre.com/Program/ProgramDetails.aspx?headtype=YanChu&ARTICLE_ID={pid}&id={pid}',
            'poster_url': poster.group(1) if poster else None,
        })
    if not out:
        raise RuntimeError('节目列表页没解析出任何节目，页面结构可能变了')
    return [o for o in out if o['start_date'] <= end.isoformat()]


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


FETCHERS = [('上海大剧院', fetch_sgt), ('上海交响乐团音乐厅', fetch_shso), ('上音歌剧院', fetch_syoh),
            ('上海东方艺术中心', fetch_shoac), ('上海文化广场', fetch_shcs)]


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
            items = [x for x in old if x['oid'].startswith(venue + ':') and (x['end_date'] or x['start_date']) >= today.isoformat()]
            print(f'!! {venue} 抓取失败（{type(e).__name__}: {e}），沿用上次的 {len(items)} 条')
        result += items
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(result, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'共 {len(result)} 条 → {os.path.relpath(OUT, SITE)}')


if __name__ == '__main__':
    main()
