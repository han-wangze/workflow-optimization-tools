import pandas as pd
import numpy as np
import os
import re
from pathlib import Path

# 本文件所在目录，所有路径都相对它定位
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ---------- 使用前只需改这两个路径 ----------
INPUT_FOLDER = os.path.join(BASE_DIR, 'data', 'questionnaires')
OUTPUT_FOLDER = os.path.join(BASE_DIR, 'output')

# ---------- 内置配置 ----------
# 调整后的标准列顺序
STANDARD_COLUMNS = [
    '样本用户属性', '样本量', '整体下载意愿', '尖叫度-愿意下载',
    '游玩时长_一个月以上占比', '游玩时长_半年以上占比',
    '男性用户_下载意愿', '男性用户_尖叫度-下载',
    '女性用户_下载意愿', '女性用户_尖叫度-下载',
    '愿意下载原因占比_题材', '愿意下载原因占比_美术', '愿意下载原因占比_玩法',
    '不愿意下载原因占比_题材', '不愿意下载原因占比_美术', '不愿意下载原因占比_玩法'
]

# 游玩时长选项定义
PLAY_DURATION_OPTIONS = {
    '仅试玩几次': ['仅试玩几次'],
    '数小时': ['数小时'],
    '一周以内': ['一周以内'],
    '几周到一个月': ['几周到一个月'],
    '1-3个月': ['1-3个月'],
    '4-6个月': ['4-6个月'],
    '6个月以上': ['6个月以上'],
    '无法评价': ['无法评价'],
    '未选择': ['', '-', '无']
}

# 汇总分类定义
DURATION_SUMMARY = {
    '一个月以上': ['1-3个月', '4-6个月', '6个月以上'],
    '半年以上': ['6个月以上']
}

# 已填写字段的正向匹配值（可根据实际字段值调整）
FILLED_FIELD_POSITIVE_VALUES = ['是', '已填写', '填写', '完成']

# 游玩时长列的识别规则：固定题号前缀 + 当期测试的题材 / 概念关键词
# （问卷题号与题材措辞每轮会变，按当期问卷调整这两个常量即可）
DURATION_COL_PREFIX = '1使用频次'
DURATION_COL_THEME_KEYWORDS = ['概念A', '概念B', '概念C']

# ---------- 核心统计函数 ----------
def safe_string_convert(value):
    """安全转换任意类型为字符串，处理NaN/None等特殊值"""
    if pd.isna(value) or value is None:
        return ''
    elif isinstance(value, (int, float)):
        return str(value)
    else:
        return str(value).strip()

def auto_detect_play_duration_column(df_columns):
    """适配超长列名的游玩时长列识别"""
    for col in df_columns:
        if DURATION_COL_PREFIX in col and any(k in col for k in DURATION_COL_THEME_KEYWORDS):
            return col
    for col in df_columns:
        if (col.startswith('1') or col.startswith('2')) and len(col) > 50 and '：' in col:
            return col
    print("   警告：未识别到游玩时长列，请检查列名匹配")
    return None

def auto_detect_filled_column(df_columns):
    """自动识别“已填写”字段列名"""
    filled_keywords = ['已填写', '填写状态', '是否填写', '完成状态']
    for col in df_columns:
        col_clean = safe_string_convert(col)
        for keyword in filled_keywords:
            if keyword in col_clean:
                return col
    print("   警告：未识别到“已填写”字段列，请检查列名包含“已填写/填写状态/是否填写”等关键词")
    return None

def calculate_statistics(df_clean, category_name, category_col):
    """核心统计函数：基于“已填写”字段判断分母"""
    metrics = {'样本用户属性': category_name}

    try:
        # 1. 基础数据预处理
        df_clean[category_col] = df_clean[category_col].apply(safe_string_convert)
        hobby_users = df_clean[df_clean[category_col] == '有出于爱好体验过'].copy()

        df_clean['是否愿意'] = df_clean['是否愿意'].apply(safe_string_convert)
        df_clean['1试玩意愿'] = df_clean['1试玩意愿'].apply(safe_string_convert)

        willing_no_choice = df_clean[
            (df_clean['是否愿意'] == '愿意') &
            (df_clean['1试玩意愿'].isin(['', '-']))
            ].copy()

        sample_users = pd.concat([hobby_users, willing_no_choice]).drop_duplicates(subset=['序号'])
        metrics['样本量'] = len(sample_users)

        # 2. 整体下载意愿
        hobby_willing = hobby_users[hobby_users['1试玩意愿'] == '愿意试玩']
        if metrics['样本量'] > 0:
            overall_willingness = len(hobby_willing) / metrics['样本量']
            metrics['整体下载意愿'] = f'{overall_willingness:.0%}'
        else:
            metrics['整体下载意愿'] = '0%'

        # 3. 尖叫度-愿意下载
        df_clean['1尖叫度'] = df_clean['1尖叫度'].apply(safe_string_convert)
        valid_scream = hobby_willing[hobby_willing['1尖叫度'] != '-']['1尖叫度']

        scream_values = []
        for val in valid_scream:
            try:
                scream_values.append(float(val))
            except (ValueError, TypeError):
                continue

        if len(scream_values) > 0:
            metrics['尖叫度-愿意下载'] = f'{np.mean(scream_values):.2f}'
        else:
            metrics['尖叫度-愿意下载'] = '0.00'

        # 4. 游玩时长统计（核心修正：基于“已填写”字段判断分母）
        duration_col = auto_detect_play_duration_column(df_clean.columns)
        filled_col = auto_detect_filled_column(df_clean.columns)  # 识别“已填写”字段
        metrics['游玩时长_一个月以上占比'] = '0%'
        metrics['游玩时长_半年以上占比'] = '0%'

        if duration_col and duration_col in df_clean.columns and filled_col and filled_col in df_clean.columns:
            # 安全转换字段
            df_clean[duration_col] = df_clean[duration_col].apply(safe_string_convert)
            df_clean[filled_col] = df_clean[filled_col].apply(safe_string_convert)

            # 筛选：仅保留“已填写”字段为正向值的样本（分母）
            filled_users = df_clean[df_clean[filled_col].isin(FILLED_FIELD_POSITIVE_VALUES)].copy()
            total_filled = len(filled_users)  # 分母 = 已填写样本数

            if total_filled > 0:
                # 提取已填写样本的游玩时长数据
                duration_data = filled_users[duration_col].tolist()
                one_month_plus_count = 0
                six_month_plus_count = 0

                for val in duration_data:
                    # 匹配游玩时长选项
                    matched_option = None
                    for option_name, option_values in PLAY_DURATION_OPTIONS.items():
                        if val in option_values:
                            matched_option = option_name
                            break

                    # 统计目标分类
                    if matched_option in DURATION_SUMMARY['一个月以上']:
                        one_month_plus_count += 1
                    if matched_option in DURATION_SUMMARY['半年以上']:
                        six_month_plus_count += 1

                # 计算占比（分母=已填写样本数）
                metrics['游玩时长_一个月以上占比'] = f'{one_month_plus_count / total_filled:.0%}'
                metrics['游玩时长_半年以上占比'] = f'{six_month_plus_count / total_filled:.0%}'
        elif not filled_col:
            print(f"   ⚠️  {category_name} 未识别到“已填写”字段，游玩时长占比按0%统计")

        # 5. 男性用户指标
        df_clean['性别'] = df_clean['性别'].apply(safe_string_convert)
        male_hobby = hobby_users[hobby_users['性别'] == '男']
        male_willing_no_choice = willing_no_choice[willing_no_choice['性别'] == '男']
        male_sample_size = len(pd.concat([male_hobby, male_willing_no_choice]).drop_duplicates(subset=['序号']))
        male_hobby_willing = male_hobby[male_hobby['1试玩意愿'] == '愿意试玩']

        metrics['男性用户_下载意愿'] = f'{len(male_hobby_willing) / male_sample_size:.0%}' if male_sample_size > 0 else '0%'

        male_scream = male_hobby_willing[male_hobby_willing['1尖叫度'] != '-']['1尖叫度']
        male_scream_values = []
        for val in male_scream:
            try:
                male_scream_values.append(float(val))
            except (ValueError, TypeError):
                continue
        metrics['男性用户_尖叫度-下载'] = f'{np.mean(male_scream_values):.2f}' if len(male_scream_values) > 0 else '0.00'

        # 6. 女性用户指标
        female_hobby = hobby_users[hobby_users['性别'] == '女']
        female_willing_no_choice = willing_no_choice[willing_no_choice['性别'] == '女']
        female_sample_size = len(pd.concat([female_hobby, female_willing_no_choice]).drop_duplicates(subset=['序号']))
        female_hobby_willing = female_hobby[female_hobby['1试玩意愿'] == '愿意试玩']

        metrics['女性用户_下载意愿'] = f'{len(female_hobby_willing) / female_sample_size:.0%}' if female_sample_size > 0 else '0%'

        female_scream = female_hobby_willing[female_hobby_willing['1尖叫度'] != '-']['1尖叫度']
        female_scream_values = []
        for val in female_scream:
            try:
                female_scream_values.append(float(val))
            except (ValueError, TypeError):
                continue
        metrics['女性用户_尖叫度-下载'] = f'{np.mean(female_scream_values):.2f}' if len(female_scream_values) > 0 else '0.00'

        # 7. 愿意下载原因占比
        df_clean['1下载原因'] = df_clean['1下载原因'].apply(safe_string_convert)
        willing_total = len(hobby_willing)
        for reason in ['题材', '美术', '玩法']:
            count = len(hobby_willing[hobby_willing['1下载原因'].str.contains(reason)])
            metrics[f'愿意下载原因占比_{reason}'] = f'{count / willing_total:.0%}' if willing_total > 0 else '0%'

        # 8. 不愿意下载原因占比
        df_clean['1不下载原因'] = df_clean['1不下载原因'].apply(safe_string_convert)
        hobby_unwilling = hobby_users[hobby_users['1试玩意愿'] == '不愿意试玩']
        unwilling_total = len(hobby_unwilling)
        for reason in ['题材', '美术', '玩法']:
            count = len(hobby_unwilling[hobby_unwilling['1不下载原因'].str.contains(reason)])
            metrics[f'不愿意下载原因占比_{reason}'] = f'{count / unwilling_total:.0%}' if unwilling_total > 0 else '0%'

    except Exception as e:
        print(f"   ⚠️  {category_name} 统计出错: {str(e)[:50]}")
        # 填充默认值
        default_cols = ['整体下载意愿', '尖叫度-愿意下载', '游玩时长_一个月以上占比', '游玩时长_半年以上占比',
                        '男性用户_下载意愿', '男性用户_尖叫度-下载', '女性用户_下载意愿', '女性用户_尖叫度-下载']
        for col in default_cols:
            if col not in metrics:
                metrics[col] = '0%' if '占比' in col or '意愿' in col else '0.00'

        reason_cols = ['题材', '美术', '玩法']
        for reason in reason_cols:
            if f'愿意下载原因占比_{reason}' not in metrics:
                metrics[f'愿意下载原因占比_{reason}'] = '0%'
            if f'不愿意下载原因占比_{reason}' not in metrics:
                metrics[f'不愿意下载原因占比_{reason}'] = '0%'

    return metrics

# ---------- 辅助函数 ----------
def auto_detect_game_categories(df_columns):
    game_category_mapping = {}
    category_keywords = [
        r'问题.*玩过.*游戏',
        r'品类.*偏好',
        r'游戏.*类型',
        r'玩过.*类.*游戏'
    ]

    for col in df_columns:
        for keyword in category_keywords:
            if re.search(keyword, col, re.IGNORECASE):
                category_name = extract_category_name(col)
                if category_name:
                    game_category_mapping[category_name] = col
                else:
                    game_category_mapping[col] = col
                break

    if not game_category_mapping:
        print("   警告：未自动识别到游戏品类问题，使用默认映射")
        game_category_mapping = {
            '示例品类A': '1问题:<p>请问您是否出于个人爱好玩过 &nbsp;示例品类A&nbsp; 游戏？（单选）</p>',
            '示例品类B': '2问题:<p>请问您是否出于个人爱好玩过 &nbsp;示例品类B&nbsp; 游戏？（单选）</p>',
            '示例品类C': '3问题:<p>请问您是否出于个人爱好玩过 &nbsp;示例品类C&nbsp; 游戏？（单选）</p>',
        }

    return game_category_mapping

def extract_category_name(column_name):
    match = re.search(r'&nbsp;(.*?)&nbsp;', column_name)
    if match:
        return match.group(1)
    match = re.search(r'玩过.*?(.*?)(?:游戏|类)', column_name)
    if match:
        return match.group(1).strip()
    match = re.search(r'\d+问题[：:]\s*(.*?)(?:</p>|$)', column_name)
    if match:
        return match.group(1).strip()
    return None

# ---------- 批量处理主流程 ----------
def batch_process():
    Path(OUTPUT_FOLDER).mkdir(exist_ok=True)
    excel_files = [f for f in os.listdir(INPUT_FOLDER) if f.endswith('.xlsx') and not f.startswith('~$')]

    if not excel_files:
        print(f"⚠️  错误：在文件夹 {INPUT_FOLDER} 中未找到Excel文件！")
        return

    print(f"📁 找到 {len(excel_files)} 个待处理文件：")
    for i, file_name in enumerate(excel_files, 1):
        print(f"   {i}. {file_name}")

    batch_summary = []
    for file_idx, file_name in enumerate(excel_files, 1):
        file_path = os.path.join(INPUT_FOLDER, file_name)
        file_prefix = file_name.replace('.xlsx', '')

        print(f"\n" + "=" * 80)
        print(f"【{file_idx}/{len(excel_files)}】正在处理：{file_name}")

        try:
            excel_file = pd.ExcelFile(file_path)
            if 'Sheet1' in excel_file.sheet_names:
                df = excel_file.parse('Sheet1')
            else:
                df = excel_file.parse(0)

            # 数据清理
            df['序号'] = df['序号'].apply(safe_string_convert)
            df_clean = df[
                (df['序号'] != '结果汇总') &
                (df['序号'].str.isdigit())
                ].reset_index(drop=True)
            print(f"   数据处理完成：原始 {len(df)} 行 → 有效 {len(df_clean)} 行")

            # 识别“已填写”字段并输出
            filled_col = auto_detect_filled_column(df_clean.columns)
            if filled_col:
                print(f"   识别到“已填写”字段：{filled_col}")
                # 输出已填写样本数统计
                df_clean[filled_col] = df_clean[filled_col].apply(safe_string_convert)
                filled_count = len(df_clean[df_clean[filled_col].isin(FILLED_FIELD_POSITIVE_VALUES)])
                total_count = len(df_clean)
                print(f"   已填写样本数：{filled_count} / 总样本数：{total_count}")
            else:
                print(f"   未识别到“已填写”字段，游玩时长统计将按0%输出")

            game_category_mapping = auto_detect_game_categories(df_clean.columns)
            print(f"   自动识别到 {len(game_category_mapping)} 个游戏品类：")
            for category_name, column_name in game_category_mapping.items():
                print(f"     - {category_name}: {column_name[:50]}...")

            # 识别游玩时长列
            duration_col = auto_detect_play_duration_column(df_clean.columns)
            if duration_col:
                print(f"   识别到游玩时长列：{duration_col[:50]}...")
            else:
                print(f"   未识别到游玩时长列，游玩时长统计将显示0%")

            # 统计每个游戏品类
            category_results = []
            for category_name, category_col in game_category_mapping.items():
                print(f"   正在统计：{category_name}")
                metrics = calculate_statistics(df_clean, category_name, category_col)
                category_results.append(metrics)

            # 整理结果
            result_df = pd.DataFrame(category_results)
            for col in STANDARD_COLUMNS:
                if col not in result_df.columns:
                    if '占比' in col or '意愿' in col:
                        result_df[col] = '0%'
                    elif '尖叫度' in col:
                        result_df[col] = '0.00'
                    else:
                        result_df[col] = 0
            final_result_df = result_df[STANDARD_COLUMNS].copy()

            # 保存结果
            output_file_path = os.path.join(OUTPUT_FOLDER, f'{file_prefix}_统计结果.xlsx')
            with pd.ExcelWriter(output_file_path, engine='openpyxl') as writer:
                final_result_df.to_excel(writer, sheet_name='统计结果', index=False)
                df_clean.to_excel(writer, sheet_name='原始数据', index=False)

            print(f"   ✅ 保存成功：{os.path.basename(output_file_path)}")

            # 记录汇总
            for _, row in final_result_df.iterrows():
                summary_row = {
                    '处理顺序': file_idx,
                    '文件名': file_prefix,
                    '游戏品类': row['样本用户属性'],
                    '样本量': row['样本量'],
                    '整体下载意愿': row['整体下载意愿'],
                    '尖叫度-愿意下载': row['尖叫度-愿意下载'],
                    '游玩时长_一个月以上占比': row['游玩时长_一个月以上占比'],
                    '游玩时长_半年以上占比': row['游玩时长_半年以上占比'],
                    '男性用户_下载意愿': row['男性用户_下载意愿'],
                    '男性用户_尖叫度-下载': row['男性用户_尖叫度-下载'],
                    '女性用户_下载意愿': row['女性用户_下载意愿'],
                    '女性用户_尖叫度-下载': row['女性用户_尖叫度-下载'],
                    '愿意下载原因占比_题材': row['愿意下载原因占比_题材'],
                    '愿意下载原因占比_美术': row['愿意下载原因占比_美术'],
                    '愿意下载原因占比_玩法': row['愿意下载原因占比_玩法'],
                    '不愿意下载原因占比_题材': row['不愿意下载原因占比_题材'],
                    '不愿意下载原因占比_美术': row['不愿意下载原因占比_美术'],
                    '不愿意下载原因占比_玩法': row['不愿意下载原因占比_玩法'],
                    '统计状态': '成功'
                }
                batch_summary.append(summary_row)

        except Exception as e:
            error_msg = str(e)[:50]
            print(f"   ❌ 处理失败：{error_msg}...")
            fail_row = {
                '处理顺序': file_idx,
                '文件名': file_prefix,
                '游戏品类': '无',
                '样本量': '',
                '整体下载意愿': '',
                '尖叫度-愿意下载': '',
                '游玩时长_一个月以上占比': '',
                '游玩时长_半年以上占比': '',
                '男性用户_下载意愿': '',
                '男性用户_尖叫度-下载': '',
                '女性用户_下载意愿': '',
                '女性用户_尖叫度-下载': '',
                '愿意下载原因占比_题材': '',
                '愿意下载原因占比_美术': '',
                '愿意下载原因占比_玩法': '',
                '不愿意下载原因占比_题材': '',
                '不愿意下载原因占比_美术': '',
                '不愿意下载原因占比_玩法': '',
                '统计状态': f'失败：{error_msg}'
            }
            batch_summary.append(fail_row)

    # 生成汇总表
    summary_df = pd.DataFrame(batch_summary)
    summary_file_path = os.path.join(OUTPUT_FOLDER, '批量处理汇总表.xlsx')
    summary_df.to_excel(summary_file_path, index=False)

    # 输出报告
    print(f"\n" + "=" * 80)
    print(f"📊 批量处理完成！")
    print(f"=" * 80)
    print(f"📁 结果存放位置：{OUTPUT_FOLDER}")
    print(f"📋 生成文件清单：")
    print(f"   1. 单个文件结果：每个原文件对应1个统计结果文件（含统计数据+原始数据）")
    print(f"   2. 批量汇总表：批量处理汇总表.xlsx（所有文件结果对比）")
    print(f"\n📈 处理统计：")
    print(f"   📋 输出列顺序：样本用户属性 → 样本量 → 整体下载意愿 → 尖叫度-愿意下载 → 游玩时长_一个月以上占比 → 游玩时长_半年以上占比 → 其他列")
    print(f"   📊 游玩时长统计规则：")
    print(f"      - 分母：“已填写”字段标记为{FILLED_FIELD_POSITIVE_VALUES}的样本总数")
    print(f"      - 一个月以上：包含1-3个月、4-6个月、6个月以上")
    print(f"      - 半年以上：仅包含6个月以上")
    print(f"      - 已填写样本包含：有效选择、无法评价、未选择（只要“已填写”字段为正向值）")
    success_count = len([x for x in batch_summary if x['统计状态'] == '成功'])
    fail_count = len(batch_summary) - success_count
    print(f"   ✅ 成功统计：{success_count} 个品类")
    print(f"   ❌ 失败统计：{fail_count} 个品类")

if __name__ == "__main__":
    try:
        batch_process()
    except Exception as global_error:
        print(f"\n" + "=" * 80)
        print(f"❌ 批量处理启动失败：{str(global_error)}")
        print(f"💡 常见解决办法：")
        print(f"   1. 检查 INPUT_FOLDER 和 OUTPUT_FOLDER 路径是否正确")
        print(f"   2. 确保安装了必要依赖：pip install pandas openpyxl numpy")
        print(f"   3. 关闭所有正在打开的Excel文件")
        print(f"   4. 确保Excel中包含“已填写”字段，且值为{FILLED_FIELD_POSITIVE_VALUES}中的一种")
