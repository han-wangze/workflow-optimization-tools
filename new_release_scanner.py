"""Sensor Tower 免费榜新品扫描。

读入某期免费榜导出的 csv，筛出当年新上线且名次变化显著的产品，
与累积的已扫描产品去重表比对后输出本周新增，并把新增产品回写去重表。
"""
import pandas as pd
import glob
import os
from datetime import datetime

# 本文件所在目录，所有路径都相对它定位
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 输入新品扫描csv文件的路径（根据实际环境调整）
work_dir = os.path.join(BASE_DIR, "data", "export")
# 已扫描产品去重表的路径（累积记录历次已收录的产品名，需含 app name 列）
uploaded_excel_path = os.path.join(BASE_DIR, "data", "scanned_apps.xlsx")
# 更新后的去重Excel输出路径（指定具体文件名，而非文件夹）
updated_excel_filename = "scanned_apps_updated.xlsx"
updated_excel_path = os.path.join(work_dir, updated_excel_filename)

print(f"工作目录: {work_dir}")
print(f"原始去重Excel路径: {uploaded_excel_path}")
print(f"更新后去重Excel输出路径: {updated_excel_path}")


class SimpleAppleStoreProcessor:

    def __init__(self, work_directory, uploaded_excel_path, updated_excel_path):
        self.work_directory = work_directory
        self.processed_files = []
        self.uploaded_excel_path = uploaded_excel_path  # 原始去重Excel路径
        self.updated_excel_path = updated_excel_path  # 更新后去重Excel输出路径
        # 初始化时加载并清理原始去重Excel（含空记录处理）
        self.cleaned_excluded_df = self._load_and_clean_excluded_excel()
        # 提取清理后的游戏名称集合（用于去重匹配）
        self.excluded_game_names = set(self.cleaned_excluded_df['app name'].unique())

    # ---------- 去重表的加载与清洗 ----------
    def _load_and_clean_excluded_excel(self):
        """
        加载原始去重Excel，删除行间空记录（空的“app name”行），返回清理后的数据框（仅保留app name列）
        """
        try:
            # 读取原始Excel，仅保留“app name”列
            raw_excluded_df = pd.read_excel(self.uploaded_excel_path, sheet_name=0, usecols=['app name'])
            print(f"\n1. 原始去重Excel加载完成，共 {len(raw_excluded_df)} 条记录")

            # 清理空记录：
            raw_excluded_df['app name'] = raw_excluded_df['app name'].astype(str).str.strip()  # 统一格式
            cleaned_df = raw_excluded_df[raw_excluded_df['app name'] != ''].copy()  # 删除空行

            print(f"2. 空记录清理完成：原始 {len(raw_excluded_df)} 条 -> 清理后 {len(cleaned_df)} 条")
            return cleaned_df

        except KeyError:
            print(f"❌ 原始去重Excel中未找到'app name'列，请检查文件格式")
            # 仅返回app name列的空数据框
            return pd.DataFrame(columns=['app name'])
        except Exception as e:
            print(f"❌ 加载原始去重Excel失败: {str(e)}")
            return pd.DataFrame(columns=['app name'])

    def detect_format_and_extract(self, df):
        """检测导出表格的格式并提取所需字段"""
        columns = df.columns.tolist()

        if 'Downloads' in columns and 'Revenue ($)' in columns:
            required_columns = [
                'Country', 'Chart', 'Date', 'Ranking', 'App ID', 'App name',
                'App URL', 'Release date', 'App ranking change', 'Downloads', 'Revenue ($)'
            ]

        elif 'iPhone downloads' in columns and 'iPhone revenue ($)' in columns:
            column_mapping = {
                'iPhone downloads': 'Downloads',
                'iPhone revenue ($)': 'Revenue ($)'
            }
            df = df.rename(columns=column_mapping)
            required_columns = [
                'Country', 'Chart', 'Date', 'Ranking', 'App ID', 'App name',
                'App URL', 'Release date', 'App ranking change', 'Downloads', 'Revenue ($)'
            ]

        else:
            print("未知表格格式，跳过处理")
            return pd.DataFrame()

        available_columns = [col for col in required_columns if col in df.columns]
        extracted_df = df[available_columns].copy()
        return extracted_df

    def apply_filters(self, df):
        """应用筛选条件（免费榜 / 目标年上线 / 名次变化显著）"""

        def remove_tz(dt_series):
            dt_series = pd.to_datetime(dt_series, errors='coerce')
            if dt_series.dt.tz is not None:
                dt_series = dt_series.dt.tz_localize(None)
            return dt_series

        df['Release date'] = remove_tz(df['Release date'])
        if 'Date' in df.columns:
            df['Date'] = remove_tz(df['Date'])

        # 日期格式处理 - 仅保留日期部分
        df['Release date'] = df['Release date'].dt.date
        if 'Date' in df.columns:
            df['Date'] = df['Date'].dt.date

        # 筛选条件（筛选新游戏）
        chart_condition = df['Chart'].isin(['topfreeapplications', 'topselling_free'])
        year_condition = df['Release date'].apply(lambda x: x.year == 2025 if pd.notna(x) else False)
        is_new_app = df['App ranking change'].astype(str).str.contains('new', case=False, na=False)
        ranking_vals = pd.to_numeric(df['Ranking'], errors='coerce').fillna(0)
        change_vals = pd.to_numeric(df['App ranking change'], errors='coerce').fillna(0)
        numeric_condition = (ranking_vals + change_vals) > 100
        new_entry_condition = is_new_app | numeric_condition

        filtered_df = df[chart_condition & year_condition & new_entry_condition].copy()
        print(f"筛选结果: {len(df)} -> {len(filtered_df)} 条新游戏记录")
        return filtered_df

    def process_single_file(self, file_path):
        """处理单个 csv 文件"""
        print(f"处理文件: {os.path.basename(file_path)}")

        try:
            df = pd.read_csv(file_path, sep='\t', encoding='utf-16', engine='python')
            extracted_df = self.detect_format_and_extract(df)

            if extracted_df.empty:
                print("无法识别表格格式或没有所需字段")
                return pd.DataFrame()

            filtered_df = self.apply_filters(extracted_df)

            if not filtered_df.empty:
                filtered_df['source_file'] = os.path.basename(file_path)
                return filtered_df
            else:
                print("没有符合条件的新游戏数据")
                return pd.DataFrame()

        except Exception as e:
            print(f"处理文件时出错: {str(e)}")
            return pd.DataFrame()

    def process_files(self):
        """处理工作目录下的全部 csv 文件"""
        file_pattern = os.path.join(self.work_directory, "*.csv")
        excel_files = glob.glob(file_pattern)

        print(f"在目录 {self.work_directory} 中找到 {len(excel_files)} 个csv文件")

        if not excel_files:
            print("未找到任何csv文件")
            return None

        all_processed_data = []

        for i, file_path in enumerate(excel_files, 1):
            print(f"\n进度: {i}/{len(excel_files)}")
            processed_data = self.process_single_file(file_path)

            if not processed_data.empty:
                all_processed_data.append(processed_data)
                self.processed_files.append(file_path)

        if all_processed_data:
            merged_df = pd.concat(all_processed_data, ignore_index=True)
            print(f"\n合并完成! 共 {len(merged_df)} 条新游戏记录")
            return merged_df
        else:
            print("所有文件中都没有符合条件的新游戏数据")
            return None

    # ---------- 去重：仅按产品名剔除已收录记录 ----------
    def remove_duplicate_games(self, df):
        """
        剔除与去重表重复的新游戏记录（仅基于游戏名称）
        """
        if len(self.excluded_game_names) == 0 and len(self.cleaned_excluded_df) == 0:
            print("⚠️ 无有效去重数据，跳过去重")
            return df

        # 处理新游戏名称空格（与去重表格式统一）
        df['App name_clean'] = df['App name'].astype(str).str.strip()

        # 筛选：新游戏名称不在去重表中
        duplicate_condition = ~df['App name_clean'].isin(self.excluded_game_names)
        deduplicated_df = df[duplicate_condition].copy()

        # 删除临时清洗列
        deduplicated_df = deduplicated_df.drop(columns=['App name_clean'])

        # 统计去重效果
        removed_count = len(df) - len(deduplicated_df)
        print(f"\n去重结果: 原始 {len(df)} 条新游戏记录 -> 去重后 {len(deduplicated_df)} 条")
        print(f"剔除重复记录数: {removed_count}")
        return deduplicated_df

    # ---------- 去重表的追加与落盘 ----------
    def update_excluded_excel(self, new_games_df):
        """
        1. 从去重后的新游戏记录中提取“App name”
        2. 追加到清理后的去重表中（避免重复追加）
        3. 输出更新后的去重Excel（仅保留app name列）
        """
        if new_games_df.empty:
            print("\n⚠️ 无新游戏记录可追加，去重Excel保持不变")
            # 直接保存清理后的原始去重表
            self.cleaned_excluded_df.to_excel(self.updated_excel_path, index=False, engine='openpyxl')
            print(f"✅ 清理后的原始去重Excel已保存至: {self.updated_excel_path}")
            return

        # 步骤1：提取新游戏的“App name”并统一格式
        new_app_data = new_games_df[['App name']].copy()
        new_app_data['App name'] = new_app_data['App name'].astype(str).str.strip()
        # 重命名列（匹配去重表的列名：app name）
        new_app_data.columns = ['app name']

        # 步骤2：去重追加（避免与现有去重表记录重复）
        combined_df = pd.concat([self.cleaned_excluded_df, new_app_data], ignore_index=True)
        combined_df = combined_df.drop_duplicates(subset=['app name'], keep='first')  # 仅按名称去重

        # 步骤3：保存更新后的去重表（仅含app name列）
        try:
            combined_df.to_excel(self.updated_excel_path, index=False, engine='openpyxl')
            # 统计追加效果
            added_count = len(combined_df) - len(self.cleaned_excluded_df)
            print(f"\n去重Excel更新完成:")
            print(f"- 原始去重表记录数: {len(self.cleaned_excluded_df)}")
            print(f"- 追加新游戏记录数: {added_count}")
            print(f"- 更新后总记录数: {len(combined_df)}")
            print(f"- 更新文件路径: {self.updated_excel_path}")
            return True
        except Exception as e:
            print(f"\n❌ 保存更新后的去重Excel失败: {str(e)}")
            return False

    def save_results(self, df):
        """保存新游戏处理结果（整合去重+更新去重表）"""
        if df is None or df.empty:
            print("没有新游戏数据需要保存")
            # 即使无新游戏，也保存清理后的去重表
            self.update_excluded_excel(pd.DataFrame())
            return False

        # 步骤1：先对新游戏记录去重
        df_deduplicated = self.remove_duplicate_games(df)

        # 步骤2：保存去重后的新游戏结果
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = os.path.join(self.work_directory, f'ST_new_games_{timestamp}.xlsx')

        # 处理日期格式（仅保留日期）
        for col in ['Date', 'Release date']:
            if col in df_deduplicated.columns:
                df_deduplicated[col] = pd.to_datetime(df_deduplicated[col], errors='coerce').dt.strftime(
                    '%Y/%m/%d').fillna('')

        # 保存新游戏结果
        try:
            df_deduplicated.to_excel(output_file, index=False, engine='openpyxl')
            print(f"\n✅ 去重后的新游戏结果已保存至: {output_file}")
        except Exception as e:
            print(f"\n❌ 保存新游戏结果失败: {str(e)}")
            csv_file = output_file.replace('.xlsx', '.csv')
            df_deduplicated.to_csv(csv_file, index=False, encoding='utf-8-sig')
            print(f"📌 已作为备选方案保存为CSV: {csv_file}")

        # 步骤3：更新去重Excel（仅追加app name）
        self.update_excluded_excel(df_deduplicated)
        return True


# ========== 创建实例并执行 ==========
processor = SimpleAppleStoreProcessor(work_dir, uploaded_excel_path, updated_excel_path)
print("处理器实例创建成功")

# 入口：处理全部文件并保存结果（自动触发去重表更新）
print("\n开始处理文件...")
final_new_games = processor.process_files()

if __name__ == "__main__":
    if final_new_games is not None:
        processor.save_results(final_new_games)
    else:
        print("❌ 无新游戏数据可处理")
        # 无新游戏时，仍保存清理后的去重表
        processor.update_excluded_excel(pd.DataFrame())
