"""第四阶段：固定EKF、训练两组RF并按验证集等记录平均RMSE选型。"""
import json
import sys
from pathlib import Path
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestRegressor

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.build_model import sha, write_json
from src.correction import FEATURES, MEASUREMENTS, EKF_COLUMNS, build_features, predict_corrected

OUT = ROOT / 'outputs/correction'


def score(reference, prediction):
    err = (np.asarray(prediction) - np.asarray(reference)) * 100
    return {'mae_pp': float(np.mean(abs(err))), 'rmse_pp': float(np.sqrt(np.mean(err ** 2))),
            'max_abs_error_pp': float(np.max(abs(err))), 'mean_error_pp': float(np.mean(err))}


def check_features():
    # 一个有意义的边界检查：未来样本、标签列和另一连续段都不能污染当前特征。
    n = 120
    t = np.arange(n) * .1
    d = pd.DataFrame({'source_row': np.arange(n), 'time_s': t, 'segment_id': 0,
                      'voltage_v': 4.1 - .001 * t, 'current_a': np.sin(t), 'temperature_degC': 25.})
    e = pd.DataFrame({'source_row': d.source_row, 'time_s': t,
                      'soc_ekf': .8 - .001 * t, 'voltage_residual_v': .001})
    full = build_features(d, e)
    np.testing.assert_allclose(build_features(d.iloc[:70], e.iloc[:70]), full.iloc[:70], rtol=0, atol=0)
    polluted = d.assign(soc_ref=-999, net_discharge_ah=999, capacity_raw_ah=999)
    np.testing.assert_array_equal(build_features(polluted, e.assign(soc_ref=999)), full)
    split = d.copy()
    split.loc[70:, 'segment_id'] = 1
    f = build_features(split, e)
    assert f.current_mean_5s_a.iloc[70] == d.current_a.iloc[70]
    assert f.voltage_change_5s_v.iloc[70] == 0
    return '通过：前缀一致、标签及累计容量不进入特征、segment窗口不串段'


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    write_json(OUT / 'manifest.json', {'schema_version': 1, 'status': 'candidate',
                                      'producer': 'scripts/train_correction.py'})
    paths = ['outputs/model/manifest.json', 'data/reference/manifest.json']
    parents = [{'path': p, 'sha256': sha(ROOT / p)} for p in paths]
    model_manifest, reference_manifest = [json.loads((ROOT / p).read_text(encoding='utf-8')) for p in paths]
    assert model_manifest['status'] == reference_manifest['status'] == 'canonical'
    for item in model_manifest['parents'] + model_manifest['producer_sources']:
        assert sha(ROOT / item['path']) == item['sha256'], item['path']
    inputs = []

    def checked(items, path):
        item = next(x for x in items if x['path'] == path)
        assert sha(ROOT / path) == item['sha256'], path
        inputs.append({'path': path, 'sha256': item['sha256']})
        return pd.read_csv(ROOT / path)

    records = {}
    for split in ['train', 'validation']:
        for name in reference_manifest['splits'][split]:
            d = checked(reference_manifest['files'], f'data/reference/{name}')
            e = checked(model_manifest['files'], f'outputs/predictions/ekf/{name}')
            # 标签只在训练/评价处使用；预测API接收明确白名单。
            x = build_features(d[MEASUREMENTS], e[EKF_COLUMNS])
            np.testing.assert_allclose(d.soc_ref, e.soc_ref, atol=1e-8, rtol=0)
            records[name] = {'split': split, 'd': d, 'e': e, 'x': x,
                             'y': d.soc_ref.to_numpy() - e.soc_ekf.to_numpy()}
    checks = check_features()
    training = [v for v in records.values() if v['split'] == 'train']
    x_train = pd.concat([v['x'] for v in training], ignore_index=True)
    y_train = np.concatenate([v['y'] for v in training])
    common = {'n_estimators': 120, 'max_features': 1., 'bootstrap': True,
              'max_samples': .7, 'random_state': 20261029, 'n_jobs': 4}
    candidates = [{'name': 'depth12_leaf50', 'max_depth': 12, 'min_samples_leaf': 50},
                  {'name': 'depth18_leaf20', 'max_depth': 18, 'min_samples_leaf': 20}]
    candidate_rows, fitted, objectives = [], {}, {}
    for candidate in candidates:
        name = candidate['name']
        rf = RandomForestRegressor(**common, **{k: v for k, v in candidate.items() if k != 'name'})
        print(f'Training {name}: {len(x_train)} rows, {len(FEATURES)} features', flush=True)
        rf.fit(x_train, y_train)
        fitted[name] = rf
        rmses = []
        for record, v in records.items():
            if v['split'] != 'validation':
                continue
            raw = v['e'].soc_ekf.to_numpy() + rf.predict(v['x'])
            metrics = score(v['d'].soc_ref, np.clip(raw, 0, 1))
            rmses.append(metrics['rmse_pp'])
            candidate_rows.append({'candidate': name, 'file': record, **metrics})
        objectives[name] = float(np.mean(rmses))
        print(f'{name}: validation mean-record RMSE={objectives[name]:.6f} pp', flush=True)
    selected = min(objectives, key=objectives.get)
    forest = fitted[selected]
    joblib.dump(forest, OUT / 'random_forest.joblib', compress=3)
    # 模型持久化后只做一次小样本一致性检查。
    probe = next(v for v in records.values() if v['split'] == 'validation')['x'].iloc[:256]
    np.testing.assert_allclose(forest.predict(probe), joblib.load(OUT / 'random_forest.joblib').predict(probe),
                               rtol=0, atol=1e-14)
    pd.DataFrame(candidate_rows).to_csv(OUT / 'validation_candidates.csv', index=False)
    config = {'schema_version': 1, 'selected_candidate': selected,
              'parameters': forest.get_params(), 'features': FEATURES,
              'target': 'soc_ref - soc_ekf，SOC比例单位', 'window_seconds': 5,
              'current_mean': '精确[t-5,t]内样本电流算术均值，非时间加权均值',
              'voltage_change': '当前电压减窗口内首个采样电压，开头使用已有历史',
              'selection_rule': '两个验证记录各自RMSE的等权平均；相同值保留较浅方案',
              'candidate_objectives_rmse_pp': objectives,
              'training_files': reference_manifest['splits']['train'],
              'selection_files': reference_manifest['splits']['validation'],
              'held_out_test': reference_manifest['splits']['test'],
              'training_rows': len(x_train), 'refit_on_validation': False,
              'clip_output': [0, 1], 'feedback_to_ekf': False,
              'library_versions': {'sklearn': sklearn.__version__, 'joblib': joblib.__version__}}
    write_json(OUT / 'training_config.json', config)
    importance = pd.DataFrame({'feature': FEATURES, 'impurity_importance': forest.feature_importances_})
    importance.sort_values('impurity_importance', ascending=False).to_csv(OUT / 'feature_importance.csv', index=False)
    artifacts = []
    metrics = []
    pred_dir = ROOT / 'outputs/predictions/fusion'
    pred_dir.mkdir(parents=True, exist_ok=True)
    for name, v in records.items():
        d, e = v['d'], v['e']
        fused = predict_corrected(d[MEASUREMENTS], e[EKF_COLUMNS], forest)
        result = e[['source_row', 'time_s', 'soc_ekf']].copy()
        result = pd.concat([result, fused], axis=1)
        result['soc_ref'] = d.soc_ref
        result['ekf_error_pp'] = (e.soc_ekf - d.soc_ref) * 100
        result['fused_error_pp'] = (fused.soc_fused - d.soc_ref) * 100
        assert np.isfinite(result.to_numpy()).all() and result.soc_fused.between(0, 1).all()
        path = pred_dir / name
        result.to_csv(path, index=False, float_format='%.9g')
        artifacts.append((path, 'fusion_prediction'))
        for method, values in [('EKF', e.soc_ekf), ('EKF_RF', fused.soc_fused)]:
            row = {'file': name, 'split': v['split'], 'method': method, 'rows': len(d),
                   **score(d.soc_ref, values),
                   'output_clip_count': int(((fused.soc_fused_unclipped < 0) |
                                             (fused.soc_fused_unclipped > 1)).sum()) if method == 'EKF_RF' else 0}
            metrics.append(row)
        print(name, 'EKF / RF MAE:', metrics[-2]['mae_pp'], metrics[-1]['mae_pp'], flush=True)
    scores = pd.DataFrame(metrics)
    scores.to_csv(OUT / 'metrics.csv', index=False)
    report = ['# 随机森林误差补偿报告', '', '状态：第四阶段完成，固定EKF上的随机森林补偿器已训练；最终测试尚未执行。', '',
              '## 训练与选择', '',
              f'4条完整训练记录共{len(x_train):,}个采样；2条完整验证记录用于比较两组超参数。未随机拆分相邻采样，也未读取Mixed7/8的数据。',
              '标签为参考SOC减EKF SOC，容量和参考值不进入特征。补偿加到最终SOC，不回灌EKF；融合结果裁剪至0~1，裁剪前数值及次数保留。',
              f'候选参数及每条验证结果见 validation_candidates.csv。选中 **{selected}**；选择目标为两条验证记录RMSE的等权均值。',
              '两组均120棵树、每棵树bootstrap抽取训练采样数的70%、随机种子20261029；固定EKF和容量，选型后没有用验证集重新拟合。', '',
              '## 特征', '',
              'EKF SOC、端电压、电流、表面温度、校正前电压残差、过去5秒电流样本均值、过去5秒窗口首点至当前的电压变化量。',
              '时间仅用于[t-5,t]窗口定位，不作为预测特征。窗口包括当前点，开头使用已有历史，不跨segment；均值为样本算术均值，非时间加权值。', '',
              '## 结果（单位：SOC百分点）', '',
              '|记录|用途|方法|MAE|RMSE|最大绝对误差|', '|---|---|---|---:|---:|---:|']
    for m in metrics:
        report.append(f'|{m["file"]}|{m["split"]}|{m["method"]}|{m["mae_pp"]:.3f}|{m["rmse_pp"]:.3f}|{m["max_abs_error_pp"]:.3f}|')
    val = scores[scores.split.eq('validation')].groupby('method')[['mae_pp', 'rmse_pp']].mean()
    report += ['', '按记录等权平均：', '',
               f'- 验证MAE：EKF {val.loc["EKF", "mae_pp"]:.3f} → 融合 {val.loc["EKF_RF", "mae_pp"]:.3f}。',
               f'- 验证RMSE：EKF {val.loc["EKF", "rmse_pp"]:.3f} → 融合 {val.loc["EKF_RF", "rmse_pp"]:.3f}。', '',
               '训练指标为训练内拟合表现，验证指标参与过方案选择；两者均不能替代最终测试结论。所有指标从第一个有效采样计分。', '',
               '## 验收与边界', '', checks + '；模型保存后256行预测在1e-14绝对容差内一致；六条融合预测有限且SOC位于0~1；上游模型与数据哈希未变。',
               '参考SOC为计算基准，不是独立测量真值。结果只覆盖同一电芯、25℃环境的留出记录，不代表跨电芯/温度泛化。',
               '特征重要性为树分裂不纯度重要性，相关特征会分摊重要性，不能解释因果贡献。',
               '当前补偿器用初始SOC=1的正常工况训练；初始偏差与加噪时能否改善，仍需固定模型后在下一阶段检验。',
               '下一阶段固定本模型，在Mixed7/8执行正常、初始SOC低估10个百分点、独立测量噪声三个实验，不根据测试结果再挑选模型。', '']
    (OUT / '补偿建模报告.md').write_text('\n'.join(report), encoding='utf-8')
    for name, role in [('random_forest.joblib', 'random_forest'), ('training_config.json', 'training_config'),
                       ('validation_candidates.csv', 'selection_metrics'), ('metrics.csv', 'comparison_metrics'),
                       ('feature_importance.csv', 'feature_importance'), ('补偿建模报告.md', 'stage_report')]:
        artifacts.append((OUT / name, role))
    for item in parents + inputs:
        assert sha(ROOT / item['path']) == item['sha256']
    write_json(OUT / 'manifest.json', {
        'schema_version': 1, 'stage': '4_random_forest_correction', 'status': 'canonical',
        'created_at': datetime.now(timezone.utc).isoformat(), 'producer': 'scripts/train_correction.py',
        'role': '第五阶段固定融合模型；训练/验证对照预测与指标',
        'acceptance': '上游正式状态与哈希一致；因果窗口/标签排除检查；保存复读预测一致；全量六条有限值及SOC边界通过',
        'parents': parents, 'input_files': inputs,
        'producer_sources': [{'path': p, 'sha256': sha(ROOT / p)} for p in
                             ['scripts/train_correction.py', 'scripts/build_model.py', 'src/correction.py']],
        'selected_candidate': selected, 'executed_splits': ['train', 'validation'],
        'held_out_test': reference_manifest['splits']['test'],
        'files': [{'path': p.relative_to(ROOT).as_posix(), 'role': role, 'sha256': sha(p)} for p, role in artifacts]})
    print('随机森林补偿完成：', selected, flush=True)


if __name__ == '__main__':
    main()
