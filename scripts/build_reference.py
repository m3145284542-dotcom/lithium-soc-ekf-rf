"""固定容量规则并构造八条动态工况的参考 SOC；不训练或调整模型。"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/reference'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest_path = OUT / 'manifest.json'
    if manifest_path.exists():
        old = json.loads(manifest_path.read_text(encoding='utf-8'))
        old['status'] = 'candidate'
        manifest_path.write_text(json.dumps(old, ensure_ascii=False, indent=2), encoding='utf-8')
    parent = ROOT / 'data/processed/manifest.json'
    clean_manifest = json.loads(parent.read_text(encoding='utf-8'))
    assert clean_manifest['status'] == 'canonical'
    files = {Path(r['path']).name: r for r in clean_manifest['files']}

    def load(name):
        path = ROOT / files[name]['path']
        assert sha(path) == files[name]['sha256'], f'{name}: 清洗数据已变化，请先重新清洗'
        return pd.read_csv(path)

    # 规则来自项目预定用途：551为主容量，552只做独立核对，不能按动态末端或测试误差改容量。
    capacities = []
    for name in ['551_Cap_1C.csv', '552_Cap_1C.csv']:
        d = load(name)
        discharge = d[d.status.eq('DCH')]
        assert len(discharge) and d.segment_id.nunique() == 1 and d.counter_reset.sum() == 0
        assert discharge.current_a.between(2.9, 3.1).all()
        assert discharge.voltage_v.iloc[-1] < 2.81
        capacity = float(d.capacity_raw_ah.iloc[0] - discharge.capacity_raw_ah.iloc[-1])
        integrated = float(d.segment_net_discharge_ah.iloc[-1])
        capacities.append({'file': name, 'capacity_ah': capacity,
                           'integrated_ah': integrated, 'integration_minus_counter_ah': integrated - capacity,
                           'baseline_source_row': int(d.source_row.iloc[0]),
                           'discharge_end_source_row': int(discharge.source_row.iloc[-1]),
                           'cutoff_voltage_v': float(discharge.voltage_v.iloc[-1]),
                           'role': 'reference' if name.startswith('551') else 'check_only'})
    q_ref = capacities[0]['capacity_ah']
    pd.DataFrame(capacities).to_csv(OUT / 'capacity_check.csv', index=False)

    charge_names = clean_manifest['splits']['charge_context']
    charges = {name: load(name) for name in charge_names}
    # 首末日期精度均为秒；不使用午夜仅有日期的中间样本进行跨文件匹配。
    matches, summaries, records = [], [], []
    for role in ['train', 'validation', 'test']:
        for name in clean_manifest['splits'][role]:
            d = load(name)
            assert d.timestamp_precision.iloc[0] == 'second'
            start = pd.Timestamp(d.timestamp.iloc[0])
            preceding = [(pd.Timestamp(c.timestamp.iloc[-1]), n, c) for n, c in charges.items()
                         if c.timestamp_precision.iloc[-1] == 'second' and pd.Timestamp(c.timestamp.iloc[-1]) <= start]
            charge_end, charge_name, c = max(preceding, key=lambda entry: entry[0])
            charged = c[c.status.eq('CHA') & c.current_a.lt(-.001)]
            assert len(charged), f'{charge_name}: 无充电证据'
            end_charging = charged.iloc[-1]
            charge_stop = pd.Timestamp(end_charging.timestamp)
            rest = c[(c.program_time_s > end_charging.program_time_s)]
            gap_s = (start - charge_end).total_seconds()
            rest_s = (charge_end - charge_stop).total_seconds()
            # 作者协议：4.2V/50mA截止；允许CSV约1mV及约1mA量化裕量。
            supported = (0 <= gap_s <= 5 and abs(end_charging.voltage_v - 4.2) < .005
                         and .001 < -end_charging.current_a <= .051
                         and rest_s >= 3600 and len(rest) > 0 and rest.current_a.abs().max() <= .001
                         and abs(d.capacity_raw_ah.iloc[0]) <= .0001)
            assert supported, f'{name}: 满电初值证据不足，不能自动生成参考SOC'
            assert d.segment_id.nunique() == 1 and d.counter_reset.sum() == 0
            assert d.time_s.diff().dropna().gt(0).all()
            # 同程序的绝对Prog Time辅助检查跨文件先后关系；所有动态与对应充电编号相同。
            assert name[:3] == charge_name[:3] and 0 < d.program_time_s.iloc[0] - c.program_time_s.iloc[-1] <= 5
            matches.append({'dynamic_file': name, 'charge_file': charge_name,
                            'dynamic_start': str(start), 'charge_end': str(charge_end),
                            'gap_s': gap_s, 'program_gap_s': float(d.program_time_s.iloc[0] - c.program_time_s.iloc[-1]),
                            'charge_last_active_source_row': int(end_charging.source_row),
                            'charge_last_active_time': str(charge_stop),
                            'charge_last_active_voltage_v': float(end_charging.voltage_v),
                            'charge_last_active_current_a': float(end_charging.current_a),
                            'rest_s': rest_s, 'rest_end_voltage_v': float(c.voltage_v.iloc[-1]),
                            'dynamic_first_voltage_v': float(d.voltage_v.iloc[0]),
                            'dynamic_first_capacity_ah': float(d.capacity_raw_ah.iloc[0]),
                            'initial_soc_assumption': 1.0, 'supported_by_protocol_and_records': bool(supported)})
            net = -(d.capacity_raw_ah - d.capacity_raw_ah.iloc[0])
            soc = 1 - net / q_ref
            integrated_soc = 1 - d.segment_net_discharge_ah / q_ref
            # 本批8条均连续，容量没有归零；累计容量作为仪器基准，电流积分仅作交叉检查。
            diff_pp = (soc - integrated_soc).abs() * 100
            assert np.isfinite(soc).all() and soc.between(-.001, 1.001).all()
            assert diff_pp.max() < 1, f'{name}: 计数器与积分不一致，需要检查'
            result = d[['source_row', 'timestamp_raw', 'timestamp', 'timestamp_precision',
                        'time_s', 'dt_s', 'segment_id', 'voltage_v', 'current_a', 'temperature_degC']].copy()
            result['net_discharge_ah'] = net
            result['soc_ref'] = soc
            result['soc_ref_pct'] = soc * 100
            result['soc_integral_check'] = integrated_soc
            target = OUT / name
            result.to_csv(target, index=False, float_format='%.9f')
            saved = pd.read_csv(target)
            np.testing.assert_allclose(saved.soc_ref, 1 - saved.net_discharge_ah / q_ref, atol=1e-9)
            summaries.append({'file': name, 'role': role, 'rows': len(d),
                              'duration_s': float(d.time_s.iloc[-1]),
                              'initial_soc_pct': float(soc.iloc[0] * 100),
                              'end_soc_pct': float(soc.iloc[-1] * 100),
                              'min_soc_pct': float(soc.min() * 100), 'max_soc_pct': float(soc.max() * 100),
                              'net_discharge_ah': float(net.iloc[-1]),
                              'max_integral_difference_pp': float(diff_pp.max())})
            records.append({'path': target.relative_to(ROOT).as_posix(), 'sha256': sha(target),
                            'role': role, 'rows': len(d), 'parent_path': files[name]['path'],
                            'parent_sha256': files[name]['sha256'], 'charge_context_file': charge_name})
            print(f'OK {name}: {len(result)} rows, end SOC {soc.iloc[-1]*100:.4f}%', flush=True)
    pd.DataFrame(matches).to_csv(OUT / 'charge_matches.csv', index=False)
    pd.DataFrame(summaries).to_csv(OUT / 'reference_summary.csv', index=False)
    policy = {'schema_version': 1, 'capacity_reference_ah': q_ref,
              'capacity_reference_file': capacities[0]['file'],
              'capacity_rule': '预先指定551_Cap_1C完整DCH段末容量相对文件开头的净放电量；552只作核对',
              'capacity_check_ah': capacities[1]['capacity_ah'],
              'initial_soc': 1.0,
              'initial_soc_rule': '紧邻充电达到4.2V/50mA截止且约61分钟静置，首个动态采样按满电近似；不是独立测量真值',
              'soc_formula': '1 - (capacity_raw_ah[0] - capacity_raw_ah[t]) / capacity_reference_ah',
              'first_sample_offset': '将首个采样作为相对积分起点；Mixed4首计数器-0.00005Ah被扣除，约0.0018个百分点',
              'clipping': False, 'forced_terminal_soc': False,
              'model_input_columns': ['voltage_v', 'current_a', 'temperature_degC'],
              'time_columns': ['time_s', 'dt_s', 'segment_id'],
              'evaluation_only_columns': ['net_discharge_ah', 'soc_ref', 'soc_ref_pct', 'soc_integral_check'],
              'selection_boundary': '不使用任何动态测试SOC误差选择容量或初值；所有动态记录共用主容量'}
    policy_path = OUT / 'reference_policy.json'
    policy_path.write_text(json.dumps(policy, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    metadata = {'schema_version': 1, 'stage': '2b_reference_soc', 'status': 'canonical',
                'producer': 'scripts/build_reference.py', 'producer_sha256': sha(Path(__file__)),
                'created_at': datetime.now(timezone.utc).isoformat(),
                'parent_manifest': parent.relative_to(ROOT).as_posix(), 'parent_manifest_sha256': sha(parent),
                'protocol_readme_sha256': sha(ROOT / 'data/raw/LG_HG2_25degC/original_README.txt'),
                'reference_policy': policy_path.relative_to(ROOT).as_posix(), 'reference_policy_sha256': sha(policy_path),
                'splits': {role: clean_manifest['splits'][role] for role in ['train', 'validation', 'test']},
                'modeling_data_manifest': 'data/processed/manifest.json',
                'scope': '八条动态记录的输入和计算参考SOC；模型参数尚未辨识',
                'acceptance': '上游哈希匹配；充电对应关系及截止条件通过；连续时间/无容量归零；参考SOC复读公式通过；积分交叉差小于1个百分点',
                'files': records,
                'supporting_files': [{'path': p.relative_to(ROOT).as_posix(), 'sha256': sha(p)}
                                     for p in [OUT/'charge_matches.csv', OUT/'capacity_check.csv', OUT/'reference_summary.csv', policy_path]]}
    manifest_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    delta = (capacities[1]['capacity_ah'] / q_ref - 1) * 100
    lines = ['# 参考 SOC 与数据准备完成说明', '',
             f'主参考容量固定为 **{q_ref:.5f} Ah**，来自 551_Cap_1C 完整1C放电的容量计数器。',
             f'552_Cap_1C 的核对容量为 {capacities[1]["capacity_ah"]:.5f} Ah，相对主容量差 {delta:.3f}%。552未用于重新校准主容量。', '',
             '## 参考值定义', '',
             '`SOC_ref(t) = 1 − [Capacity(0) − Capacity(t)] / Q_ref`，范围按0～1保存，另提供百分数列。',
             'Capacity为原始有符号安时计数器，放电减小、充电增大；再生充电时SOC允许回升。初始SOC按首个采样满电近似，不强制末端归零，不裁剪参考值。',
             '仪器累计容量作为主要参考；保留按原始采样间隔梯形电流积分的交叉检查结果。它们来源于同一电流测量系统，并非独立真值验证。',
             '首样本计数器被作为相对零点。Mixed4首值为-0.00005Ah，忽略的采样前放电对应约0.0018个百分点。', '',
             '## 起点满电依据', '',
             '作者说明每次测试后按1C充电至4.2V、50mA截止，并在22℃以上充电。下列匹配同时使用实际日期时间和同一程序的Prog Time，未按文件编号猜测。',
             '8条动态记录之前均观察到充电末端约4.19979V、48.53mA及约61分钟静置，随后1～2秒开始动态记录；由此采用满电初始值近似。',
             '| 动态文件 | 前序充电文件 | 间隔/s | 充电后静置/s | 静置末端/V |',
             '|---|---|---:|---:|---:|']
    lines += [f"| {r['dynamic_file']} | {r['charge_file']} | {r['gap_s']:.0f} | {r['rest_s']:.0f} | {r['rest_end_voltage_v']:.5f} |" for r in matches]
    lines += ['', '## 动态数据结果', '', '| 文件 | 划分 | 行数 | 末端SOC/% | 最大积分交叉差/百分点 |', '|---|---|---:|---:|---:|']
    lines += [f"| {r['file']} | {r['role']} | {r['rows']} | {r['end_soc_pct']:.4f} | {r['max_integral_difference_pp']:.4f} |" for r in summaries]
    lines += ['', '## 容量与误差边界', '',
              '完整放电容量从文件首个静置零计数器算至最后DCH样本，不能从首个DCH采样直接相减，否则漏掉首次采样前约10秒的放电量。1C放电终止电压约2.79993V，随后为静置。',
              '两次1C测试的梯形积分略小于仪器计数器，差约0.0041Ah；稀疏采样、步骤边界的积分近似等会造成差异。本项目使用仪器计数器容量，详细数值见capacity_check.csv。',
              '固定主容量后，Mixed1–2末端约5%，Mixed3–8约6.17%；不按每条记录末端重新缩放。两次容量测试的差异会使参考SOC存在约1个百分点量级的容量归一化不确定性，不据此将参考曲线称为精确真值。',
              f"初始满电近似叠加再生充电后，参考值最高为 {max(r['max_soc_pct'] for r in summaries):.5f}%，略超100%的原值保留，不人为压平；后续评价应说明该初始假设和计数器误差边界。",
              '只在本电芯、25℃环境、已有工况范围使用；同一电芯不同记录留出不代表跨电芯泛化。', '',
              '## 下游入口与复现', '',
              '- `python scripts/build_reference.py`：校验清洗数据后生成本目录CSV、规则和清单。',
              '- 动态数据正式入口：`data/reference/manifest.json`；OCV/HPPC建模仍使用清洗清单中的指定文件。',
              '- 随机森林仅使用测量值及EKF派生特征，不使用参考SOC、累计容量、积分SOC或累计运行时间作为预测特征。',
              '- 输入与参考SOC示例图：`outputs/figures/Mixed1_inputs_reference.png`；曲线为计算参考，无算法结果。',
              '- 初始状态、容量、参考SOC和输入曲线完成后即可进入一阶RC模型与EKF阶段。', '']
    (OUT / '数据准备报告.md').write_text('\n'.join(lines), encoding='utf-8')
    print(f'COMPLETE: Q_ref={q_ref:.5f} Ah; {len(records)} dynamic records')


if __name__ == '__main__':
    main()
