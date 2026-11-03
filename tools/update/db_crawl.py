#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""豆瓣同城上海活动抓取（断点续抓 + 限流控制）"""
import os, re, time, random, urllib.request, urllib.error

OUT = '/tmp/db_crawl'
os.makedirs(OUT, exist_ok=True)

UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120.0 Safari/537.36')

# 分类：(豆瓣slug, 中文名, 上限页数)
CATS = [
    ('exhibition', '展览',   30),
    ('drama',      '戏剧',   55),
    ('music',      '音乐',   35),
    ('kids',       '亲子',   16),
    ('comedy',     '喜剧',   15),
    # 音乐子类
    ('1001', '小型现场', 10), ('1002', '音乐会', 20), ('1003', '演唱会', 15), ('1004', '音乐节', 8),
    # 戏剧子类
    ('1101', '话剧', 30), ('1102', '音乐剧', 20), ('1103', '舞剧', 10),
    ('1104', '歌剧', 6), ('1105', '戏曲', 8),
    # 喜剧子类
    ('2201', '脱口秀', 12), ('2202', '相声', 5),
]

def fetch(url, tries=3):
    for t in range(tries):
        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': UA,
                'Accept': 'text/html,application/xhtml+xml',
                'Accept-Language': 'zh-CN,zh;q=0.9',
                'Referer': 'https://www.douban.com/location/shanghai/',
            })
            with urllib.request.urlopen(req, timeout=25) as r:
                return r.read().decode('utf-8', 'ignore')
        except urllib.error.HTTPError as e:
            if e.code in (403, 418, 429):
                wait = 12 * (t + 1)
                print(f"    [限流 {e.code}] 等待 {wait}s", flush=True)
                time.sleep(wait)
            else:
                time.sleep(3)
        except Exception as e:
            print(f"    [错误] {type(e).__name__}: {e}", flush=True)
            time.sleep(4)
    return None

def main():
    total_pages = 0
    for slug, name, maxp in CATS:
        print(f"\n=== {name} (future-{slug}) ===", flush=True)
        empty_streak = 0
        for p in range(maxp):
            start = p * 10
            fp = f'{OUT}/{slug}_{start}.html'
            if os.path.exists(fp) and os.path.getsize(fp) > 3000:
                print(f"  {start:5d} 已存在，跳过", flush=True)
                total_pages += 1
                continue
            url = f'https://www.douban.com/location/shanghai/events/future-{slug}?start={start}'
            h = fetch(url)
            if h is None:
                print(f"  {start:5d} 失败", flush=True)
                continue
            n = h.count('class="list-entry"')
            if n == 0:
                empty_streak += 1
                print(f"  {start:5d} 空页({empty_streak})", flush=True)
                if empty_streak >= 1:
                    break
                continue
            empty_streak = 0
            open(fp, 'w', encoding='utf-8').write(h)
            total_pages += 1
            print(f"  {start:5d} 保存 {n} 条 (累计 {total_pages} 页)", flush=True)
            time.sleep(random.uniform(1.0, 1.6))
    print(f"\n抓取结束，共 {total_pages} 页", flush=True)

if __name__ == '__main__':
    main()
