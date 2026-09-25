import asyncio
import csv
from datetime import datetime
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


def parse_date(date_str: str) -> datetime:
    """将日期字符串转换为datetime对象"""
    return datetime.strptime(date_str, "%Y-%m-%d")


async def get_up_videos_in_range(uid: int, start_date: str, end_date: str, credential=None) -> List[Dict]:
    """获取指定时间范围内的单个UP主视频"""
    start = parse_date(start_date)
    end = parse_date(end_date)
    page_num = 1
    all_videos = []
    u = user.User(uid=uid, credential=credential)

    try:
        # 获取UP主名称（用于结果展示）
        up_info = await u.get_user_info()
        up_name = up_info["name"]
    except:
        up_name = f"未知（UID：{uid}）"

    while True:
        try:
            # 最新版本API中get_videos无需参数，通过内部分页机制获取
            videos = await u.get_videos()
            # 检查是否有视频数据
            if not videos.get("list", {}).get("vlist"):
                break

            # 筛选时间范围内的视频
            for v in videos["list"]["vlist"]:
                pub_date = datetime.fromtimestamp(v["created"])
                if start <= pub_date <= end:
                    all_videos.append({
                        "up主名称": up_name,
                        "up主UID": uid,
                        "视频标题": v["title"],
                        "视频链接": f"https://www.bilibili.com/video/{v['bvid']}",
                        "发布时间": pub_date.strftime("%Y-%m-%d %H:%M:%S")
                    })
                elif pub_date < start:
                    # 视频按发布时间倒序排列，早于开始时间可提前退出
                    page_num = -1
                    break

            if page_num == -1:
                break

            # 检查是否有下一页（通过是否还有视频判断）
            if len(videos["list"]["vlist"]) < 30:  # 每页最多30条
                break

            page_num += 1

        except Exception as e:
            print(f"获取UP主{up_name}（UID：{uid}）的视频时出错：{str(e)}")
            break

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
