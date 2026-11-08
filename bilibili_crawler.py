import asyncio
import csv
from datetime import datetime, timedelta
from bilibili_api import user, Credential
from typing import List, Dict

# 配置参数 - 可添加多个UP主UID（示例值，替换为你要跟踪的 UP 主 UID）
UP_UIDS = [123456789, 987654321]  # 多个UP主的UID列表
START_DATE = "2025-01-01"  # 开始日期（包含）
END_DATE = "2025-01-14"  # 结束日期（包含）
CSV_FILE = "bilibili_videos.csv"  # 导出的CSV文件名
# 若需访问私密内容，填写Cookie信息（可选）
CREDENTIAL = Credential(
    sessdata="",  # 可选：从浏览器Cookie获取
    bili_jct="",  # 可选
    buvid3=""  # 可选
)


PAGE_SIZE = 30    # 每页条数，对应 get_videos 的 ps 参数
MAX_PAGES = 200   # 翻页上限：接口异常时不至于无限翻


def parse_date(date_str: str) -> datetime:
    """将日期字符串转换为datetime对象"""
    return datetime.strptime(date_str, "%Y-%m-%d")


async def get_up_videos_in_range(uid: int, start_date: str, end_date: str, credential=None) -> List[Dict]:
    """获取指定时间范围内的单个UP主视频"""
    start = parse_date(start_date)
    # END_DATE 标注为「包含当天」，所以要 +1 天并配合左闭右开区间。
    # 原来的写法用 pub_date <= end，而 end 是当天 00:00，等于把结束日整天的投稿全部排除
    # （2026-11-08 修）。
    end = parse_date(end_date) + timedelta(days=1)
    page_num = 1
    all_videos = []
    seen = set()           # 用 bvid 去重：分页边界上偶尔会有同一条视频重复出现
    reached_start = False  # 已翻到早于开始时间的视频，可以停止翻页
    u = user.User(uid=uid, credential=credential)

    try:
        # 获取UP主名称（用于结果展示）
        up_info = await u.get_user_info()
        up_name = up_info["name"]
    except:
        up_name = f"未知（UID：{uid}）"

    while page_num <= MAX_PAGES and not reached_start:
        try:
            # get_videos 必须显式传 pn 才会翻页（签名：pn=1, ps=30, order=PUBDATE）。
            # 原实现只写 get_videos()，每轮都取第一页：轻则永远只拿到首页、
            # 重则首页 30 条全落在时间窗内时永远不触发退出条件，无限循环并重复追加
            # （2026-11-08 修）。
            videos = await u.get_videos(pn=page_num, ps=PAGE_SIZE)
            vlist = (videos.get("list") or {}).get("vlist") or []
            # 检查是否有视频数据
            if not vlist:
                break

            # 筛选时间范围内的视频
            for v in vlist:
                bvid = v.get("bvid")
                if bvid in seen:
                    continue
                seen.add(bvid)

                pub_date = datetime.fromtimestamp(v["created"])
                if start <= pub_date < end:
                    all_videos.append({
                        "up主名称": up_name,
                        "up主UID": uid,
                        "视频标题": v["title"],
                        "视频链接": f"https://www.bilibili.com/video/{bvid}",
                        "发布时间": pub_date.strftime("%Y-%m-%d %H:%M:%S")
                    })
                elif pub_date < start:
                    # 投稿按发布时间倒序排列，遇到早于开始时间的即可停止翻页
                    reached_start = True
                    break

            # 本页不足一页，说明已经到底
            if len(vlist) < PAGE_SIZE:
                break

            page_num += 1

        except Exception as e:
            print(f"获取UP主{up_name}（UID：{uid}）第 {page_num} 页时出错：{str(e)}")
            break

    if page_num > MAX_PAGES and not reached_start:
        print(f"⚠️  UID {uid} 已达最大翻页数 {MAX_PAGES}，结果可能不完整")

    return all_videos


async def main():
    try:
        all_results = []
        print(f"开始抓取{len(UP_UIDS)}个UP主在 {START_DATE} 至 {END_DATE} 期间的视频...\n")

        # 逐个处理每个UP主
        for uid in UP_UIDS:
            print(f"正在处理UP主（UID：{uid}）...")
            videos = await get_up_videos_in_range(
                uid=uid,
                start_date=START_DATE,
                end_date=END_DATE,
                credential=CREDENTIAL
            )
            all_results.extend(videos)
            print(f"已获取UP主（UID：{uid}）的{len(videos)}个视频\n")

        # 导出为CSV
        if all_results:
            with open(CSV_FILE, mode="w", encoding="utf-8-sig", newline="") as f:
                # CSV表头
                fieldnames = ["up主名称", "up主UID", "视频标题", "视频链接", "发布时间"]
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(all_results)

            print(f"所有数据处理完成，共找到 {len(all_results)} 个符合条件的视频")
            print(f"结果已导出至：{CSV_FILE}")
        else:
            print("未找到符合条件的视频")

    except Exception as e:
        print(f"发生错误：{str(e)}")


if __name__ == "__main__":
    asyncio.run(main())
