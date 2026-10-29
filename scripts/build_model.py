"""第三阶段：指定建模数据辨识一阶RC，并在训练/验证记录上运行EKF。"""
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import curve_fit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.battery import BatteryModel
from src.ekf import estimate

OUT = ROOT / 'outputs/model'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def load_checked(manifest, name):
    item = next(r for r in manifest['files'] if Path(r['path']).name == name)
    path = ROOT / item['path']
    if sha(path) != item['sha256']:
        raise ValueError(f'{name}: 上游数据变化，请重建上游阶段')
    return pd.read_csv(path), {'path': item['path'], 'sha256': item['sha256']}


def fit_ocv(d, capacity):
    # 保持与动态参考相同容量轴；不把低倍率末端强行定为0。
    discharge = d[d.status.eq('DCH') & d.current_a.gt(.1)].copy()
    discharge['soc'] = 1 + discharge.capacity_raw_ah / capacity
    valid = discharge[discharge.soc.between(0, 1)].sort_values('soc')
    # 2个百分点SOC分箱，中位数抑制量化噪声；两端由邻近放电点线性插值/外推。
    valid['bin'] = np.floor(valid.soc * 50).astype(int)
    knots = valid.groupby('bin')[['soc', 'voltage_v']].median()
    s, v = knots.soc.to_numpy(), knots.voltage_v.to_numpy()
    s = np.r_[0., s, 1.]
    v0 = np.interp(0., discharge.soc.iloc[::-1], discharge.voltage_v.iloc[::-1])
    # 首个采样SOC略小于1，线性外推不足0.1个百分点。
    top = discharge.sort_values('soc').iloc[-2:]
    v1 = top.voltage_v.iloc[-1] + (1 - top.soc.iloc[-1]) * np.diff(top.voltage_v)[0] / np.diff(top.soc)[0]
    v = np.r_[v0, v, v1]
    # 单调包络使EKF测量雅可比不因小量化噪声反向。
    v = np.maximum.accumulate(v)
    table = pd.DataFrame({'soc': s, 'ocv_v': v})
    return table, {'discharge_rows': len(discharge), 'in_range_rows': len(valid),
                   'below_zero_soc_rows_excluded': int((discharge.soc < 0).sum()),
                   'raw_soc_min': float(discharge.soc.min()), 'raw_soc_max': float(discharge.soc.max()),
                   'method': '仅C/20放电段；固定主容量；0.02 SOC分箱中位数；单调PCHIP',
                   'limitation': '低倍率带载电压近似OCV；未消除滞回、倍率容量差与温度影响'}


def fit_rc(d, capacity):
    groups = (d.step.ne(d.step.shift()) | d.status.ne(d.status.shift()) |
              d.segment_id.ne(d.segment_id.shift())).cumsum()
    blocks = [x for _, x in d.groupby(groups, sort=False)]
    rows = []
    def relaxation(t, equilibrium, amplitude, tau):
        return equilibrium - amplitude * np.exp(-t / tau)
    for j, pulse in enumerate(blocks[1:-1], start=1):
        before, rest = blocks[j - 1], blocks[j + 1]
        if pulse.status.iloc[0] != 'DCH' or pulse.current_a.median() < 2:
            continue
        duration = float(rest.time_s.iloc[0] - pulse.time_s.iloc[0])
        row = {'pulse_start_source_row': int(pulse.source_row.iloc[0]),
               'pulse_end_source_row': int(pulse.source_row.iloc[-1]),
               'rest_start_source_row': int(rest.source_row.iloc[0]),
               'soc': float(1 + pulse.capacity_raw_ah.iloc[0] / capacity),
               'current_a': float(pulse.current_a.median()), 'duration_s': duration,
               'accepted': False, 'reason': ''}
        if (not 5 <= duration <= 12 or len(pulse) < 20 or
                pulse.voltage_v.min() <= 2.81 or rest.status.iloc[0] != 'PAU' or
                before.current_a.abs().max() > .01 or rest.current_a.abs().max() > .01 or
                rest.time_s.iloc[-1] - rest.time_s.iloc[0] < 30):
            row['reason'] = '非完整5~12秒脉冲、触及截止电压或静置不足'
            rows.append(row)
            continue
        t = (rest.time_s - rest.time_s.iloc[0]).to_numpy()
        v = rest.voltage_v.to_numpy()
        try:
            pars, _ = curve_fit(relaxation, t, v,
                                p0=[v[-1] + .002, v[-1] - v[0] + .002, 10.],
                                bounds=([v[-1] - .02, .0001, .3], [v[-1] + .2, .8, 100.]),
                                maxfev=5000)
            equilibrium, amplitude, tau = pars
            rmse = float(np.sqrt(np.mean((v - relaxation(t, *pars)) ** 2)))
            i = row['current_a']
            r0 = (v[0] - pulse.voltage_v.iloc[-1]) / i
            # 静置首点较关断晚约0.1s，外推极化幅度至关断时刻。
            delay = float(rest.time_s.iloc[0] - pulse.time_s.iloc[-1])
            r1 = amplitude * np.exp(delay / tau) / (i * (1 - np.exp(-duration / tau)))
            row.update(r0_ohm=float(r0), r1_ohm=float(r1), tau_s=float(tau),
                       c1_f=float(tau / r1), relaxation_rmse_v=rmse,
                       equilibrium_v=float(equilibrium))
            row['accepted'] = bool(.001 < r0 < .1 and .0001 < r1 < .2 and .31 < tau < 99 and rmse < .005)
            row['reason'] = '通过' if row['accepted'] else '物理范围、拟合边界或恢复RMSE未通过'
        except (RuntimeError, ValueError) as exc:
            row['reason'] = type(exc).__name__
        rows.append(row)
    table = pd.DataFrame(rows)
    accepted = table[table.accepted]
    if len(accepted) < 5:
        raise ValueError('有效HPPC脉冲不足')
    values = accepted[['r0_ohm', 'r1_ohm', 'tau_s']].median().to_dict()
    values['c1_f'] = values['tau_s'] / values['r1_ohm']
    return table, values


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    # 若中途失败，旧结果不再被误认作本次正式输出。
    write_json(OUT / 'manifest.json', {'schema_version': 1, 'status': 'candidate',
                                      'producer': 'scripts/build_model.py'})
    parents = {}
    for key, relative in [('processed', 'data/processed/manifest.json'),
                          ('reference', 'data/reference/manifest.json')]:
        path = ROOT / relative
        parents[key] = json.loads(path.read_text(encoding='utf-8'))
        assert parents[key]['status'] == 'canonical'
    assert parents['reference']['parent_manifest_sha256'] == sha(ROOT / 'data/processed/manifest.json')
    policy_path = ROOT / parents['reference']['reference_policy']
    assert sha(policy_path) == parents['reference']['reference_policy_sha256']
    policy = json.loads(policy_path.read_text(encoding='utf-8'))
    q = policy['capacity_reference_ah']
    sources = []
    ocv_data, source = load_checked(parents['processed'], '549_C20DisCh.csv')
    sources.append(source)
    rc_data, source = load_checked(parents['processed'], '549_HPPC.csv')
    sources.append(source)
    ocv, ocv_info = fit_ocv(ocv_data, q)
    pulses, rc = fit_rc(rc_data, q)
    parameters = {'schema_version': 1, 'capacity_ah': q, **rc,
                  'ocv_soc': ocv.soc.tolist(), 'ocv_v': ocv.ocv_v.tolist(),
                  'ocv_method': ocv_info,
                  'rc_method': '有效完整放电脉冲关断跳变R0；静置恢复单指数拟合R1/tau；各参数取中位数',
                  'rc_pulses_accepted': int(pulses.accepted.sum()),
                  'rc_scope': '全SOC固定参数基线；不拟合温度或充放电不对称性'}
    settings = {'initial_soc': 1., 'initial_polarization_v': 0.,
                'initial_std': [.05, .02],
                'process_variance_per_s': [1e-8, 1e-5], 'voltage_std_v': .03,
                'selection': '首版工程预设；未利用动态SOC误差搜索超参数',
                'integration': '相邻电流均值与真实dt；极化状态采用区间常值输入解析递推'}
    write_json(OUT / 'battery_parameters.json', parameters)
    write_json(OUT / 'ekf_config.json', settings)
    ocv.to_csv(OUT / 'ocv_curve.csv', index=False)
    pulses.to_csv(OUT / 'hppc_pulse_fits.csv', index=False)
    model = BatteryModel(parameters)
    metrics, artifacts = [], []
    pred_dir = ROOT / 'outputs/predictions/ekf'
    pred_dir.mkdir(parents=True, exist_ok=True)
    for role in ['train', 'validation']:
        for name in parents['reference']['splits'][role]:
            d, source = load_checked(parents['reference'], name)
            sources.append(source)
            pred = estimate(d[['time_s', 'segment_id', 'current_a', 'voltage_v']], model, settings)
            # 只有滤波结束后才接入评价标签，EKF从未读取参考SOC。
            pred.insert(0, 'source_row', d.source_row)
            pred.insert(1, 'time_s', d.time_s)
            pred['soc_ref'] = d.soc_ref
            pred['error_pp'] = (pred.soc_ekf - d.soc_ref) * 100
            path = pred_dir / name
            pred.to_csv(path, index=False, float_format='%.9g')
            err = pred.error_pp.to_numpy()
            metrics.append({'file': name, 'split': role, 'rows': len(d),
                            'mae_pp': float(np.mean(abs(err))),
                            'rmse_pp': float(np.sqrt(np.mean(err ** 2))),
                            'max_abs_error_pp': float(np.max(abs(err))),
                            'mean_error_pp': float(np.mean(err)),
                            'voltage_prediction_rmse_v': float(np.sqrt(np.mean(pred.voltage_residual_v ** 2))),
                            'update_clip_count': int(((pred.soc_update_unclipped < 0) | (pred.soc_update_unclipped > 1)).sum()),
                            'prediction_clip_count': int(((pred.soc_predict_unclipped < 0) | (pred.soc_predict_unclipped > 1)).sum()),
                            'min_soc_variance': float(pred.soc_variance.min())})
            artifacts.append((path, 'ekf_prediction'))
            print(name, metrics[-1], flush=True)
    results = pd.DataFrame(metrics)
    results.to_csv(OUT / 'ekf_metrics.csv', index=False)
    report = ['# 一阶RC建模与EKF报告', '',
              '状态：第三阶段完成，首版课程基线。随机森林和最终测试尚未执行。', '',
              '## 参数来源', '',
              f'- 主容量：{q:.5f} Ah，沿用参考SOC规则。',
              f'- 近似OCV：C/20放电共{ocv_info["discharge_rows"]}行，使用0~1内{ocv_info["in_range_rows"]}行，生成{len(ocv)}个单调节点。',
              f'- 低倍率放电的容量轴最小值{ocv_info["raw_soc_min"]:.5f}；超出0~1的点不参与拟合，未重新缩放容量。',
              f'- HPPC：候选{len(pulses)}个放电脉冲，接受{int(pulses.accepted.sum())}个。逐脉冲行号、排除原因及恢复拟合误差见 hppc_pulse_fits.csv。',
              f'- R0={rc["r0_ohm"]:.6f} Ω，R1={rc["r1_ohm"]:.6f} Ω，τ={rc["tau_s"]:.3f} s，C1={rc["c1_f"]:.1f} F。', '',
              '## 模型与滤波', '',
              '`SOC[k] = SOC[k-1] - I_mean * dt / (3600 Q)`', '',
              '`Up[k] = exp(-dt/τ) Up[k-1] + R1 (1-exp(-dt/τ)) I_mean`', '',
              '`V[k] = OCV(SOC[k]) - Up[k] - R0 I[k]`', '',
              'EKF状态为[SOC, Up]，测量雅可比为[dOCV/dSOC, -1]，采用Joseph协方差更新。',
              '初始SOC=1，极化电压=0，初始标准差为[0.05, 0.02V]。过程方差和测量噪声见ekf_config.json；均为预设，未根据测试集调参。',
              '真实dt、相邻电流均值用于传播；SOC约束在0~1，记录裁剪前数值及次数；不跨segment传播。', '',
              '## 训练/验证结果', '',
              '全部有效采样从第一点计分，单位为SOC百分点。电压指标是校正前一步预测残差。', '',
              '|记录|用途|MAE|RMSE|最大绝对误差|', '|---|---|---:|---:|---:|']
    for m in metrics:
        report.append(f'|{m["file"]}|{m["split"]}|{m["mae_pp"]:.3f}|{m["rmse_pp"]:.3f}|{m["max_abs_error_pp"]:.3f}|')
    report += ['', '## 边界与下一步', '',
               '参考SOC由容量计数器和满电近似构造，并非独立测量真值。低倍率带载电压近似OCV存在滞回与极化误差；HPPC单指数只描述短时恢复。固定RC参数忽略SOC、电流方向和温度依赖。',
               'HPPC关断首点含约0.1秒恢复，R0是有限采样分辨率下的近似；R1假设脉冲前残余极化较小。',
               '已完成六条训练/验证记录的有限值、方差和SOC范围检查；上游文件哈希保持一致。未运行最终测试Mixed7/8，也未据此宣称测试精度。',
               '下一阶段使用本阶段固定EKF及因果测量特征训练随机森林补偿器，以验证集选择少量方案，最后才评价最终测试集。', '']
    (OUT / '建模报告.md').write_text('\n'.join(report), encoding='utf-8')
    for name, role in [('battery_parameters.json', 'battery_parameters'), ('ekf_config.json', 'ekf_config'),
                       ('ocv_curve.csv', 'ocv_curve'), ('hppc_pulse_fits.csv', 'rc_identification'),
                       ('ekf_metrics.csv', 'metrics'), ('建模报告.md', 'stage_report')]:
        artifacts.append((OUT / name, role))
    for source in sources:
        assert sha(ROOT / source['path']) == source['sha256']
    write_json(OUT / 'manifest.json', {
        'schema_version': 1, 'stage': '3_battery_ekf', 'status': 'canonical',
        'created_at': datetime.now(timezone.utc).isoformat(), 'producer': 'scripts/build_model.py',
        'producer_sources': [{'path': p, 'sha256': sha(ROOT / p)} for p in
                             ['scripts/build_model.py', 'src/battery.py', 'src/ekf.py']],
        'role': '第四阶段随机森林的固定电池参数、EKF配置及训练/验证预测',
        'acceptance': '输入哈希一致；物理参数正值；至少5个有效脉冲；六条记录全采样有限值和非负方差；未使用测试集',
        'parents': [{'path': p, 'sha256': sha(ROOT / p)} for p in
                    ['data/processed/manifest.json', 'data/reference/manifest.json', 'data/reference/reference_policy.json']],
        'input_files': sources, 'executed_splits': ['train', 'validation'],
        'held_out_test': parents['reference']['splits']['test'],
        'files': [{'path': p.relative_to(ROOT).as_posix(), 'role': role, 'sha256': sha(p)} for p, role in artifacts]})
    print('建模阶段完成：outputs/model/manifest.json', flush=True)


if __name__ == '__main__':
    main()
