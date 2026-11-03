# 数据更新工具

把「上海文娱速递」的活动数据刷新到最新。数据源：豆瓣同城·上海（演出/展览类）+ 保留未过期的猫眼条目。

## 一键流程（推荐）

```bash
cd shanghai-events   # 项目根目录
bash tools/update/update.sh
```

脚本会自动跑完全部 11 步并输出统计：清缓存 → 豆瓣抓取 → 解析 → 合并 → 豆瓣海报 → 写回 → 猫眼抓取 → 解析 → 猫眼合并写回 → 猫眼海报 → 终局去重。

## 手动分步流程

```bash
cd tools/update
# 0. 清缓存（必做！db_crawl 有断点续抓，不清就抓不到新数据）
rm -rf /tmp/db_crawl
# 1. 抓取豆瓣（约 5-15 分钟，带断点续抓）
python3 db_crawl.py
# 2. 解析为结构化数据
python3 db_parse.py
# 3. 合并新旧（分析模式，先看统计）
python3 db_merge.py
# 3b. 确认没问题后写回数据块
python3 db_merge.py --write
# 4. 下载新海报（豆瓣图，需带 Referer）
python3 dl_posters.py
# 5. 转 webp（需要 Pillow）
python3 conv_posters.py
# 6. 写回 index.html（自动备份）
python3 db_writeback.py
# 7. 猫眼：抓取 → 解析 → 合并写回 → 下载海报
python3 maoyan_crawl.py
python3 maoyan_parse.py
python3 maoyan_merge.py
python3 dl_maoyan_posters.py
# 8. 终局去重（同标题多门店/多源卡片合并成一张）
python3 dedupe_final.py
```

## 豆瓣抓取时长上限

`db_crawl.py` 默认最多抓 20 分钟（环境变量 `DB_CRAWL_MAX_MIN` 可改），连续 8 页失败也直接收工。
提前收工时会写 `/tmp/db_crawl/_PARTIAL`，`db_merge.py` 看到它就保留上周未过期的豆瓣条目，
所以豆瓣不稳只会让这周少刷新一部分，不会让总条数骤降。
（2026-11-03 首次自动运行时豆瓣大量 SSL 断连，抓取拖了 2 个多小时，因此加了这个上限。）

## 依赖

- Python 3（`db_merge.py` / `db_writeback.py` 用标准库；`conv_posters.py` / `dl_maoyan_posters.py` 需要 Pillow）
- `db_merge.py` 里 `TODAY` 已改为 `datetime.date.today()`，不再需要手改日期

## 已知坑（踩过的都记在这）

1. **`db_crawl.py` 断点续抓**：缓存落在 `/tmp/db_crawl`，已存在的页直接跳过。
   不清缓存就「抓完了但一条新数据都没有」。macOS 还会定期清 /tmp，所以中间产物
   （`/tmp/db_parsed.json`、`/tmp/maoyan_*.json`）不能长期依赖，每次更新重跑。
2. **`db_merge.py` 的 `TODAY` 曾硬编码**：写死日期会让过期过滤失效。已改为当天。
3. **猫眼缺解析层**：`maoyan_crawl.py` 产出 `maoyan_data.json`，但 `maoyan_merge.py`
   读的是 `maoyan_parsed.json`。缺的这层由 `maoyan_parse.py` 补上。
4. **猫眼海报清单**：`dl_maoyan_posters.py` 读 `/tmp/need_posters.json`，该文件由
   `maoyan_merge.py` 末尾生成。
5. **分类兜底**：猫眼 `cornerDisplayName` 为「话剧音乐剧」「其他」时标题常判不出分类，
   `maoyan_parse.py` 里做了兜底，避免整批误杀（曾一次误杀 63 条沉浸式悬疑剧）。
   噪声正则只杀「密室游戏/闯关/逃脱」，不杀「密室体验」（后者常是沉浸式话剧）。

## 说明

- 分类映射：豆瓣 slug → 原 7 类（展览/音乐剧/话剧戏剧/古典音乐会/演唱会/喜剧/亲子演出），见 `category_of()`
- 噪声过滤：`is_noise()` 过滤商贸展会/户外旅行/运动社交/测试数据
- 通勤是前端按坐标实时算的，新数据只要有 lat/lng 即可
- 猫眼目前只保留老数据未过期条目（猫眼列表分页需逆向 XHR，未实现全量抓取）

## 猫眼数据源（2026-10-18 打通）

猫眼演出列表接口（翻页）：
```
https://m.dianping.com/myshow/ajax/performances/0;st=0;p={页};s=100;tft=0?cityId=10&sellChannel=7
```
- `cityId=10` = 上海（`cityId=1` 会混入全国，勿用）
- `s=100` 每页上限 100 条；返回 `{code:200, data:[{performanceId,name,shopName,lat,lng,address,posterUrl,showTimeRange,priceRange,cornerDisplayName,...}]}`
- 需要 `Referer: https://show.maoyan.com/list/0` + 移动端 UA
- 分类映射见 `maoyan_merge.py` 的 `maoyan_category()`（cornerDisplayName → 7 类）
- 海报：meituan 图可直接下；**pipi 图必须带 `?imageMogr2` 参数 + 移动 UA + Referer** 否则 400

流程：`maoyan_crawl.py`（抓全量 → `/tmp/maoyan_data.json`）→ `maoyan_parse.py`（标准化 → `/tmp/maoyan_parsed.json`）→ `maoyan_merge.py`（跨源去重 + 写回 index.html + 生成 `/tmp/need_posters.json`）→ `dl_maoyan_posters.py`（下载海报转 webp，需 Pillow）

## 策展层（2026-11-03 加入，第 12 步 `curate.py`）

解决三个问题：小规模演出太多、分类不准、美术馆展览和大型演唱会缺失。

- **场馆白名单** `data/venues.json`：只有名单里的场馆能上站（S=旗舰大型，A=专业中型/美术馆/知名 Livehouse）。
  名单外的整体剔除；`noise.title` 正则再剔除白名单场馆里的 DIY/VR/烛光/开放麦/通票等。
  每次运行后 `logs/curate-YYYYMMDD.txt` 会列出「未进白名单的场馆」，正规场馆手动加进来即可。
- **9 类归类**：艺术展览 / 古典/器乐 / 演唱会/Livehouse / 音乐剧 / 话剧 / 舞蹈/芭蕾 / 戏曲 / 喜剧/脱口秀 / 亲子。
  标题强信号 > 场馆类型 > 平台分类；拿不准的写进 `data/review_queue.json`，
  复核结论写进 `data/labels.json`（`{"<id>": {"category": "...", "note": "..."}}` 或 `{"drop": true}`），优先级最高。
- **策展清单**：`data/exhibitions.json`（美术馆/博物馆特展）、`data/big_shows.json`（大场馆演出，主要补大麦独家）。
  每周由定时任务联网核实后更新；与平台条目重名的只给平台条目补「官方信息」链接。
- 大麦网页对自动化弹滑块验证码，不抓取；只在详情页给大麦搜索入口。

试跑不写回：`python3 tools/update/curate.py --dry`
