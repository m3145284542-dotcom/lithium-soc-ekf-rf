"""第五阶段：固定已训练模型，对留出记录运行三组实验，不训练或调参。"""
import json
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.build_model import sha, write_json
from scripts.train_correction import score
from src.battery import BatteryModel
from src.ekf import estimate
from src.correction import MEASUREMENTS, EKF_COLUMNS, load_forest, predict_corrected

OUT = ROOT / 'outputs/experiments'
SCENARIOS = {
    'normal': {'label': '正常工况', 'initial_soc': 1., 'seed': None},
    'initial_bias': {'label': '初始SOC低估10个百分点', 'initial_soc': .9, 'seed': None},
    'measurement_noise': {'label': '测量噪声', 'initial_soc': 1., 'seed': 20261029},
}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    # 先固定协议并写入，再接触最终测试数据；失败时保留candidate状态。
    paths = ['outputs/model/manifest.json', 'outputs/correction/manifest.json',
             'data/reference/manifest.json']
    parents = [{'path': p, 'sha256': sha(ROOT / p)} for p in paths]
    model_manifest, correction_manifest, reference_manifest = [
        json.loads((ROOT / p).read_text(encoding='utf-8')) for p in paths]
    for m in [model_manifest, correction_manifest, reference_manifest]:
        assert m['status'] == 'canonical'
    for m in [model_manifest, correction_manifest]:
        for item in m['parents'] + m['producer_sources']:
            assert sha(ROOT / item['path']) == item['sha256'], item['path']
    settings_path = 'outputs/model/ekf_config.json'
    settings_item = next(i for i in model_manifest['files'] if i['path'] == settings_path)
    assert sha(ROOT / settings_path) == settings_item['sha256']
    settings = json.loads((ROOT / settings_path).read_text(encoding='utf-8'))
    tests = reference_manifest['splits']['test']
    assert tests == correction_manifest['held_out_test']
    assert not set(tests) & set(reference_manifest['splits']['train'] + reference_manifest['splits']['validation'])
    config = {'schema_version': 1, 'test_files': tests, 'scenarios': SCENARIOS,
              'noise': {'distribution': 'independent zero-mean Gaussian', 'voltage_std_v': .01,
                        'current_std_a': .05, 'record_seed_rule': 'base seed + test file index',
                        'generator': 'numpy.random.default_rng; voltage draws then current draws'},
              'scoring': 'all samples including first voltage update; equal record mean MAE/RMSE',
              'reference': 'unchanged original computed SOC; never regenerated from noisy inputs',
              'model_refit': False, 'parameters_changed_after_test': False,
              'perturbations_combined': False, 'ekf_settings': settings,
              'parents': parents, 'numpy_version': np.__version__,
              'prediction_schema': 'SOC ratios 0..1; signed errors in percentage points; time in seconds'}
    write_json(OUT / 'experiment_config.json', config)
    write_json(OUT / 'manifest.json', {'schema_version': 1, 'status': 'candidate',
                                      'producer': 'scripts/run_experiments.py', 'parents': parents})
    model, forest = BatteryModel.load(ROOT), load_forest(ROOT)
    inputs, artifacts, metrics, details = [], [], [], []
    for index, name in enumerate(tests):
        item = next(x for x in reference_manifest['files'] if x['path'] == f'data/reference/{name}')
        assert sha(ROOT / item['path']) == item['sha256']
        inputs.append({'path': item['path'], 'sha256': item['sha256']})
        d = pd.read_csv(ROOT / item['path'])
        assert len(d) == item['rows']
        for scenario, spec in SCENARIOS.items():
            measurements = d[MEASUREMENTS].copy()
            voltage_noise, current_noise = np.zeros(len(d)), np.zeros(len(d))
            if spec['seed'] is not None:
                rng = np.random.default_rng(spec['seed'] + index)
                voltage_noise = rng.normal(0, .01, len(d))
                current_noise = rng.normal(0, .05, len(d))
                measurements['voltage_v'] += voltage_noise
                measurements['current_a'] += current_noise
            run_settings = deepcopy(settings)
            run_settings['initial_soc'] = spec['initial_soc']
            e = estimate(measurements, model, run_settings)
            e['source_row'], e['time_s'] = measurements.source_row, measurements.time_s
            fused = predict_corrected(measurements, e[EKF_COLUMNS], forest)
            result = pd.concat([measurements.reset_index(drop=True),
                                e.drop(columns=['source_row', 'time_s']), fused], axis=1)
            result['voltage_noise_v'], result['current_noise_a'] = voltage_noise, current_noise
            result['soc_ref'] = d.soc_ref
            result['ekf_error_pp'] = (e.soc_ekf - d.soc_ref) * 100
            result['fused_error_pp'] = (fused.soc_fused - d.soc_ref) * 100
            assert np.isfinite(result.to_numpy()).all()
            assert result.soc_ekf.between(0, 1).all() and result.soc_fused.between(0, 1).all()
            target = OUT / 'predictions' / scenario / name
            target.parent.mkdir(parents=True, exist_ok=True)
            result.to_csv(target, index=False, float_format='%.12g')
            artifacts.append((target, 'test_prediction'))
            for method, values in [('EKF', e.soc_ekf), ('EKF_RF', fused.soc_fused)]:
                error = (values.to_numpy() - d.soc_ref.to_numpy()) * 100
                worst = int(np.argmax(abs(error)))
                row = {'scenario': scenario, 'file': name, 'method': method, 'rows': len(d),
                       **score(d.soc_ref, values), 'first_error_pp': float(error[0]),
                       'max_error_time_s': float(d.time_s.iloc[worst]),
                       'max_error_reference_pct': float(d.soc_ref.iloc[worst] * 100),
                       'output_clip_count': int(((fused.soc_fused_unclipped < 0) |
                                                 (fused.soc_fused_unclipped > 1)).sum()) if method == 'EKF_RF' else 0,
                       'ekf_predict_clip_count': int(((e.soc_predict_unclipped < 0) | (e.soc_predict_unclipped > 1)).sum()),
                       'ekf_update_clip_count': int(((e.soc_update_unclipped < 0) | (e.soc_update_unclipped > 1)).sum())}
                metrics.append(row)
                # 时间段只用于误差定位；全部样本仍参与主指标。
                for period, mask in [('first_60s', d.time_s <= d.time_s.iloc[0] + 60),
                                     ('remaining', d.time_s > d.time_s.iloc[0] + 60)]:
                    if mask.any():
                        details.append({'scenario': scenario, 'file': name, 'method': method,
                                        'period': period, 'rows': int(mask.sum()),
                                        **score(d.soc_ref[mask], values[mask])})
            print(scenario, name, 'RMSE EKF / RF:', metrics[-2]['rmse_pp'], metrics[-1]['rmse_pp'], flush=True)
    scores = pd.DataFrame(metrics)
    summary = scores.groupby(['scenario', 'method'], sort=False).agg(
        records=('file', 'size'), total_samples=('rows', 'sum'),
        mae_pp=('mae_pp', 'mean'), rmse_pp=('rmse_pp', 'mean'),
        worst_max_abs_error_pp=('max_abs_error_pp', 'max')).reset_index()
    scores.to_csv(OUT / 'metrics.csv', index=False)
    summary.to_csv(OUT / 'summary.csv', index=False)
    pd.DataFrame(details).to_csv(OUT / 'time_region_metrics.csv', index=False)
    report = ['# 最终对比实验报告', '', '第五阶段完成。固定第四阶段选出的depth12_leaf50随机森林及原有电池/EKF配置，在Mixed7/8运行三组实验。未重新训练或根据测试误差调整参数。', '',
              '## 协议与评分', '',
              'A正常工况初始SOC=1；B仅初始SOC改为0.9；C初始SOC=1，仅电压/电流分别加入标准差0.01V/0.05A的独立零均值高斯噪声。B、C不叠加。',
              '噪声基准种子20261029，Mixed7/8分别使用20261029/20261030。先生成整条电压噪声，再生成电流噪声；实际扰动随预测CSV保存。噪声强度是预设，不代表仪器精度。',
              '两种方法共用同一次EKF、相同扰动测量和全部评分采样。随机森林的电压、电流、残差、历史特征均来自相应扰动输入。参考SOC始终保持原始计算值。',
              '误差=估计−参考，乘100后单位为SOC百分点。MAE=mean(|误差|)，RMSE=sqrt(mean(误差²))，最大绝对误差=max(|误差|)。主指标从首个电压更新后样本开始，不截掉初始收敛段。',
              '初始SOC=0.9是更新前状态；首个输出已被端电压校正，因此首点误差不必等于−10个百分点。各工况MAE/RMSE按两条记录等权平均，不把平均RMSE称为全采样合并RMSE；汇总最大误差取两条中的最坏值。', '',
              '## 逐记录结果', '', '|实验|记录|方法|MAE|RMSE|最大绝对误差|', '|---|---|---|---:|---:|---:|']
    for m in metrics:
        report.append(f'|{SCENARIOS[m["scenario"]]["label"]}|{m["file"]}|{m["method"]}|{m["mae_pp"]:.3f}|{m["rmse_pp"]:.3f}|{m["max_abs_error_pp"]:.3f}|')
    report += ['', '## 等记录汇总与结论', '']
    for scenario, spec in SCENARIOS.items():
        s = summary[summary.scenario.eq(scenario)].set_index('method')
        a, b = s.loc['EKF'], s.loc['EKF_RF']
        gain = (a.rmse_pp - b.rmse_pp) / a.rmse_pp * 100
        report += [f'- **{spec["label"]}**：平均MAE {a.mae_pp:.3f} → {b.mae_pp:.3f}；平均RMSE {a.rmse_pp:.3f} → {b.rmse_pp:.3f}，相对降低{gain:.2f}%。最坏最大绝对误差 {a.worst_max_abs_error_pp:.3f} → {b.worst_max_abs_error_pp:.3f}。']
    report += ['', '## 误差定位', '', '下列位置为每条融合曲线的最大绝对误差，不因平均指标改善而省略局部失败。起始60秒与后续指标见time_region_metrics.csv。', '']
    for m in metrics:
        if m['method'] == 'EKF_RF':
            report.append(f'- {SCENARIOS[m["scenario"]]["label"]} / {m["file"]}：最大误差出现在{m["max_error_time_s"] / 60:.2f}分钟，参考SOC {m["max_error_reference_pct"]:.2f}%，绝对误差{m["max_abs_error_pp"]:.3f}个百分点，首点有符号误差{m["first_error_pp"]:.3f}。')
    report += ['', '## 解释与边界', '',
               '初始偏差考察未见过的初态，当前随机森林只在正常初态上训练；学习到的补偿规律可能无法覆盖早期收敛段。融合只修正输出，不反馈EKF内部状态，不能据此宣称提高滤波器收敛速度。',
               '加噪同时影响EKF电压校正及随机森林特征；非线性分裂和残差变化可能带来局部跳动。这里仅一次固定噪声实现，不给置信区间，也不宣称多次随机重复下的稳定性。',
               '固定RC参数、低倍率带载电压近似OCV以及未建模的温度/方向效应均可能造成残差；这些是可能解释，本实验没有消融证据确认各自贡献。',
               '参考SOC由满电近似、仪器累计容量和固定容量计算，非独立实测真值；只评价同一电芯、25℃环境下两条留出混合工况，不能外推跨电芯或跨温度性能。', '',
               '## 产出与验收', '',
               '6条逐采样预测CSV、12行主指标、6行汇总及起始/后续分段指标。检查上游正式状态和哈希、测试划分、行数、有限值与SOC输出边界；运行后确认模型与输入哈希未变。',
               '复现：python scripts/run_experiments.py；出图：python scripts/plot_experiments.py。配置和数据来源见manifest.json、experiment_config.json。', '',
               '数据引用：Phillip Kollmeyer, Mina Naguib, Michael Skells, LG 18650HG2 Li-ion Battery Data, Version 2, DOI:10.17632/b5mj79w5w9.2，CC BY 4.0。', '']
    (OUT / '实验报告.md').write_text('\n'.join(report), encoding='utf-8')
    for name, role in [('experiment_config.json', 'fixed_protocol'), ('metrics.csv', 'test_metrics'),
                       ('summary.csv', 'equal_record_summary'), ('time_region_metrics.csv', 'error_location'),
                       ('实验报告.md', 'stage_report')]:
        artifacts.append((OUT / name, role))
    for item in parents + inputs + [settings_item]:
        assert sha(ROOT / item['path']) == item['sha256']
    write_json(OUT / 'manifest.json', {'schema_version': 1, 'stage': '5_final_experiments',
        'status': 'canonical', 'created_at': datetime.now(timezone.utc).isoformat(),
        'producer': 'scripts/run_experiments.py', 'role': '固定模型的最终测试评价；报告与图表正式输入',
        'acceptance': '三工况两记录完整运行；有限值/SOC边界/划分通过；上游模型和输入哈希不变',
        'parents': parents, 'input_files': inputs + [settings_item],
        'producer_sources': [{'path': p, 'sha256': sha(ROOT / p)} for p in
                             ['scripts/run_experiments.py', 'scripts/train_correction.py',
                              'src/battery.py', 'src/ekf.py', 'src/correction.py']],
        'executed_split': 'test', 'files': [{'path': p.relative_to(ROOT).as_posix(),
            'role': role, 'sha256': sha(p)} for p, role in artifacts]})
    print(summary.to_string(index=False), flush=True)


if __name__ == '__main__':
    main()
