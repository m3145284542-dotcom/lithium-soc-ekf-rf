"""清洗全部原始数据；保留来源行号、异常明细和原始容量计数器。"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from profile_raw import ROOT, read_raw, seconds

OUT = ROOT / 'data/processed/LG_HG2_25degC'
AUDIT = ROOT / 'data/processed/audit'
MANIFEST = ROOT / 'data/processed/manifest.json'
NUMERIC = ['Voltage', 'Current', 'Temperature', 'Capacity']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def clean(item):
    path = ROOT / item['path']
    if sha(path) != item['sha256']:
        raise ValueError(f'{path.name}: 原始数据哈希改变')
    raw = read_raw(path)
    df = raw.copy()
    df['source_row'] = np.arange(1, len(df) + 1)  # 表头、单位行之后的数据行号。
    duplicates = raw.duplicated()
    rejected = [df.loc[duplicates].assign(reason='exact_duplicate')]
    df = df.loc[~duplicates].copy()
    df[NUMERIC] = df[NUMERIC].apply(pd.to_numeric, errors='coerce')
    df['program_time_s'] = seconds(df['Prog Time'])
    df['timestamp'] = pd.to_datetime(df['Time Stamp'], format='%m/%d/%Y %I:%M:%S %p', errors='coerce')
    date_only = df['Time Stamp'].str.fullmatch(r'\d{1,2}/\d{1,2}/\d{4}')
    df.loc[date_only, 'timestamp'] = pd.to_datetime(df.loc[date_only, 'Time Stamp'], format='%m/%d/%Y', errors='coerce')
    df['timestamp_precision'] = np.where(date_only, 'date_only', 'second')
    df.loc[df.timestamp.isna(), 'timestamp_precision'] = 'unparsed'
    invalid = (~np.isfinite(df[NUMERIC + ['program_time_s']]).all(axis=1)
               | (df.Voltage <= 0))
    rejected.append(df.loc[invalid].assign(reason='invalid_measurement'))
    df = df.loc[~invalid].copy()
    if df.program_time_s.diff().lt(0).any():
        raise ValueError(f'{path.name}: 程序时间倒退，需要人工确认，未自动重排')
    # 同时刻记录可能是步骤切换，保留最后记录；被替换值全部保存在 audit。
    tied = df.program_time_s.duplicated(keep='last')
    conflict_times = set(df.loc[tied, 'program_time_s'])
    conflicts = df[df.program_time_s.isin(conflict_times)].copy()
    if len(conflicts):
        conflicts['kept'] = ~conflicts.program_time_s.duplicated(keep='last')
        conflicts.to_csv(AUDIT / f'{path.stem}_time_conflicts.csv', index=False)
    rejected.append(df.loc[tied].assign(reason='same_time_keep_last'))
    df = df.loc[~tied].reset_index(drop=True)
    elapsed = df.program_time_s - df.program_time_s.iloc[0]
    dt = elapsed.diff().fillna(0)
    # 本数据常见采样为 0.1 / 10 / 60 秒，超过 300 秒不视为普通采样。
    gap = dt.gt(300)
    skipped = df.source_row.diff().gt(1) & df.source_row.shift().notna()
    # 仅无效测量造成的行缺口中断积分；删除重复行不产生新段。
    invalid_rows = set(rejected[1]['source_row'])
    invalid_between = pd.Series(False, index=df.index)
    for k in df.index[skipped]:
        invalid_between.iloc[k] = any(int(df.source_row.iloc[k - 1]) < r < int(df.source_row.iloc[k]) for r in invalid_rows)
    boundary = gap | invalid_between
    segment = boundary.cumsum()
    current = -df.Current
    interval_ah = (current.shift() + current) * 0.5 * dt / 3600
    interval_ah.iloc[0] = 0
    interval_ah.loc[boundary] = 0
    counter_reset = (df.Capacity.diff().abs().gt(.02)
                     & df.Capacity.abs().lt(.0001)
                     & df.Capacity.shift().abs().gt(.02))
    counter_segment = counter_reset.cumsum()
    result = pd.DataFrame({
        'source_row': df.source_row, 'timestamp_raw': df['Time Stamp'],
        'timestamp': df.timestamp, 'timestamp_precision': df.timestamp_precision,
        'program_time_s': df.program_time_s, 'time_s': elapsed, 'dt_s': dt,
        'segment_id': segment, 'gap_before': gap.astype(int),
        'invalid_before': invalid_between.astype(int),
        'voltage_v': df.Voltage, 'current_a': current,
        'temperature_degC': df.Temperature,
        'capacity_raw_ah': df.Capacity,
        'net_discharge_counter_ah': -df.Capacity,
        'counter_reset': counter_reset.astype(int), 'counter_segment_id': counter_segment,
        'segment_net_discharge_ah': interval_ah.groupby(segment).cumsum(),
        'step': df.Step, 'status': df.Status,
    })
    assert len(result) and np.isfinite(result.select_dtypes('number')).all().all()
    assert result.time_s.diff().dropna().gt(0).all()
    target = OUT / path.name
    result.to_csv(target, index=False, float_format='%.9f')
    removed = pd.concat(rejected, ignore_index=True)
    removed.to_csv(AUDIT / f'{path.stem}_removed.csv', index=False)
    # 用同一个积分规则核对清洗前后净电量，不把差异误称为容量计数器精度。
    raw_t = seconds(raw['Prog Time'])
    raw_dt = raw_t.diff().fillna(0)
    raw_i = -pd.to_numeric(raw.Current)
    raw_intervals = (raw_i.shift() + raw_i) * .5 * raw_dt / 3600
    raw_intervals.iloc[0] = 0
    raw_valid = np.isfinite(raw[NUMERIC].apply(pd.to_numeric, errors='coerce')).all(axis=1) & raw.Voltage.gt(0)
    raw_intervals.loc[raw_dt.gt(300) | ~raw_valid | ~raw_valid.shift(fill_value=True)] = 0
    stats = {
        'source_file': path.name, 'role': item['role'], 'input_rows': len(raw),
        'output_rows': len(result), 'exact_duplicates_removed': int(duplicates.sum()),
        'invalid_removed': int(invalid.sum()), 'time_conflicts_removed': int(tied.sum()),
        'long_gaps': int(gap.sum()), 'segments': int(segment.max() + 1),
        'counter_resets': int(counter_reset.sum()),
        'date_only_timestamps': int(df.timestamp_precision.eq('date_only').sum()),
        'unparsed_timestamps': int(df.timestamp_precision.eq('unparsed').sum()),
        'duration_s': float(elapsed.iloc[-1]), 'median_dt_s': float(dt.iloc[1:].median()),
        'max_dt_s': float(dt.max()),
        'raw_integrated_net_ah': float(raw_intervals.sum()),
        'clean_integrated_net_ah': float(interval_ah.sum()),
        'integration_change_ah': float(interval_ah.sum() - raw_intervals.sum()),
    }
    # 检查写出的文件，而不仅是内存对象。
    saved = pd.read_csv(target)
    assert len(saved) == len(result) and saved.time_s.diff().dropna().gt(0).all()
    if abs(stats['integration_change_ah']) > .001:
        raise ValueError(f'{path.name}: 清洗前后积分差超过 0.001 Ah，需检查')
    print(f"OK {path.name}: {len(raw)} -> {len(result)}", flush=True)
    return {**stats, 'path': target.relative_to(ROOT).as_posix(), 'sha256': sha(target),
            'parent_path': item['path'], 'parent_sha256': item['sha256'],
            'audit_path': (AUDIT / f'{path.stem}_removed.csv').relative_to(ROOT).as_posix()}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    AUDIT.mkdir(parents=True, exist_ok=True)
    # 失败时不会留下仍声称 canonical 的旧清单。
    if MANIFEST.exists():
        previous = json.loads(MANIFEST.read_text(encoding='utf-8'))
        previous['status'] = 'candidate'
        MANIFEST.write_text(json.dumps(previous, ensure_ascii=False, indent=2), encoding='utf-8')
    source_path = ROOT / 'data/dataset_manifest.json'
    source = json.loads(source_path.read_text(encoding='utf-8'))
    assert source['status'] == 'canonical'
    records = [clean(item) for item in source['files']]
    report = pd.DataFrame(records).drop(columns=['sha256', 'parent_sha256'])
    report.to_csv(ROOT / 'data/processed/quality_summary.csv', index=False)
    manifest = {'schema_version': 1, 'stage': '2a_cleaning', 'status': 'canonical',
                'producer': 'scripts/clean_data.py',
                'created_at': datetime.now(timezone.utc).isoformat(),
                'parent_manifest': source_path.relative_to(ROOT).as_posix(),
                'parent_manifest_sha256': sha(source_path), 'splits': source['splits'],
                'acceptance': '原始哈希一致；输出复读行数及严格递增时间通过；积分变化不超过0.001Ah',
                'scope': '清洗及单位标准化，非参考SOC数据；建模/训练/验证/测试用途沿用阶段1',
                'current_convention': '放电为正、充电为负：current_a = -原始Current',
                'gap_threshold_s': 300, 'soc_reference_available': False,
                'columns': { 'source_row': '原始数据行号，从1开始（不含说明、表头与单位行）',
                    'timestamp': '原始设备当地时间，不附加或推断时区',
                    'timestamp_raw': '原始Time Stamp文本',
                    'timestamp_precision': 'second/date_only/unparsed；date_only仅有日期，timestamp中00:00:00为占位，不用于时间差',
                    'program_time_s': '原始Prog Time换算秒，允许超过24小时',
                    'time_s': '相对首个保留采样的秒数', 'dt_s': '与前一行时间差，首行0，跨段仍保留真实差值',
                    'segment_id': '遇长间断或被剔除的无效测量后递增，从0开始',
                    'gap_before': '当前点之前时间差大于300秒',
                    'invalid_before': '当前点之前存在剔除的无效测量',
                    'voltage_v': '电压 V', 'current_a': '电流 A，放电为正',
                    'temperature_degC': '电池表面温度 ℃，不是固定环境温度',
                    'capacity_raw_ah': '原始有符号容量计数器 Ah，未拼接归零',
                    'net_discharge_counter_ah': '原始容量取负，不是从文件起点累计的容量',
                    'counter_reset': '计数器跳变>0.02Ah且归零到绝对值<0.0001Ah的标记',
                    'counter_segment_id': '按计数器归零分段，从0开始',
                    'segment_net_discharge_ah': '各时间段内梯形电流积分Ah，跨段不积分；不是SOC',
                    'step': '原始步骤编号', 'status': '原始状态'}, 'files': records}
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    totals = report.select_dtypes('number').sum()
    lines = ['# 数据清洗报告', '', f"处理 {len(records)} 个文件：{int(totals.input_rows):,} 行 → {int(totals.output_rows):,} 行。",
             f"删除完全重复行 {int(totals.exact_duplicates_removed)} 行；同一程序时刻冲突删除 {int(totals.time_conflicts_removed)} 行；无效测量删除 {int(totals.invalid_removed)} 行。",
             f"标记长间断 {int(totals.long_gaps)} 处、容量计数器归零 {int(totals.counter_resets)} 处。关键数值未采用插值或均值填充。", '',
             '## 处理规则', '',
             '- 移除说明、空字符、单位行和多余空列；保留来源行号。',
             '- 按 Prog Time 的小时、分、秒换算，支持超过24小时，不使用秒级时间戳去重。',
             '- 完全重复行保留首条；程序时刻相同但内容不同保留最后一条，冲突全部值与保留标记见 audit/*_time_conflicts.csv。',
             '- 非有限数值或电压≤0的行剔除并归档；程序时间解析失败则停止。不凭通用阈值删除脉冲电流、再生充电或轻微超过4.2V的实测电压。',
             '- 原始时间戳单独保留。仅含日期的午夜记录保留，timestamp_precision标记date_only；日期解析后的00:00:00仅是占位，时间差始终来自Prog Time。',
             '- 统一放电电流为正。原始容量单独保留，并提供取负版本；计数器归零只标记，不自动拼接。',
             '- 保留原始非均匀采样，不降采样、不平滑。大于300秒的间隔标记并分段（本批普通采样最大约60秒）；无效测量也形成段边界。后续积分/窗口/滤波应遵循 segment_id。',
             '- 每段单独梯形积分，从首个保留点的0开始，不跨间断补电量，不把分段积分当作已完整重建的全程电量。',
             '', '## 逐文件结果', '',
             '| 文件 | 原始行 | 清洗行 | 完全重复 | 同时刻冲突 | 无效 | 长间断 | 计数器归零 |',
             '|---|---:|---:|---:|---:|---:|---:|---:|']
    for r in records:
        lines.append(f"| {r['source_file']} | {r['input_rows']} | {r['output_rows']} | {r['exact_duplicates_removed']} | {r['time_conflicts_removed']} | {r['invalid_removed']} | {r['long_gaps']} | {r['counter_resets']} |")
    max_change = report.integration_change_ah.abs().max()
    lines += ['', '## 验证与使用边界', '',
              f"仅含日期的时间戳共 {int(totals.date_only_timestamps)} 行，无法解析的时间戳共 {int(totals.unparsed_timestamps)} 行。",
              f'所有输出已复读，时间严格递增；相同梯形积分规则下，清洗前后净电量差最大 {max_change:.9f} Ah（长间断及无效测量区间均排除）。',
              '所有原始文件经哈希核对，固定训练/验证/测试划分保持不变。未根据测试集调整模型或拟合参数。',
              '清洗数据正式入口：`data/processed/manifest.json`；原始数据入口仍为 `data/dataset_manifest.json`。',
              '本清洗阶段不含参考SOC；不能直接把计数器或分段积分列当作SOC标签。参考SOC由scripts/build_reference.py单独生成，其完成情况、规则与证据见data/reference/数据准备报告.md。', '']
    (ROOT / 'data/processed/清洗报告.md').write_text('\n'.join(lines), encoding='utf-8')
    print('COMPLETE', int(totals.output_rows), 'rows; max integration change:', max_change)


if __name__ == '__main__':
    main()
