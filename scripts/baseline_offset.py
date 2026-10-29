"""补充基线：只用训练记录拟合的简单偏置校正，与随机森林补偿对照，不改动既有正式产物。"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.build_model import sha, write_json
from scripts.train_correction import score

OUT = ROOT / 'outputs/baseline'
TRAIN = ['551_Mixed1.csv', '551_Mixed2.csv', '552_Mixed3.csv', '552_Mixed4.csv']
VALID = ['552_Mixed5.csv', '552_Mixed6.csv']
TEST = ['552_Mixed7.csv', '552_Mixed8.csv']
SCENARIOS = {'normal': '正常工况', 'initial_bias': '初始SOC低估10个百分点', 'measurement_noise': '测量噪声'}


def methods(offset, coef):
    # 两个基线都只读取EKF SOC；输出与融合方法相同地限制在0~1。
    return {'EKF': lambda e: e,
            'EKF_offset': lambda e: np.clip(e + offset, 0, 1),
            'EKF_linear': lambda e: np.clip(e + coef[0] + coef[1] * e, 0, 1)}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    train = pd.concat([pd.read_csv(ROOT / 'outputs/predictions/ekf' / f) for f in TRAIN])
    residual = train.soc_ref - train.soc_ekf
    offset = float(residual.mean())
    coef = np.linalg.lstsq(np.c_[np.ones(len(train)), train.soc_ekf], residual, rcond=None)[0]
    fits = methods(offset, coef)

    rows = []
    for f in VALID:
        e = pd.read_csv(ROOT / 'outputs/predictions/ekf' / f)
        fused = pd.read_csv(ROOT / 'outputs/predictions/fusion' / f)
        for m, fn in fits.items():
            rows.append({'scenario': 'validation', 'file': f, 'method': m, **score(e.soc_ref, fn(e.soc_ekf))})
        rows.append({'scenario': 'validation', 'file': f, 'method': 'EKF_RF', **score(fused.soc_ref, fused.soc_fused)})
    for s in SCENARIOS:
        for f in TEST:
            p = pd.read_csv(ROOT / 'outputs/experiments/predictions' / s / f)
            for m, fn in fits.items():
                rows.append({'scenario': s, 'file': f, 'method': m, **score(p.soc_ref, fn(p.soc_ekf))})
            rows.append({'scenario': s, 'file': f, 'method': 'EKF_RF', **score(p.soc_ref, p.soc_fused)})
    metrics = pd.DataFrame(rows)
    metrics.to_csv(OUT / 'metrics.csv', index=False)

    # 与第五阶段一致：每条记录先算指标，再两条等权平均；最大误差取最坏值。
    summary = metrics.groupby(['scenario', 'method'], sort=False).agg(
        mae_pp=('mae_pp', 'mean'), rmse_pp=('rmse_pp', 'mean'),
        worst_max_abs_error_pp=('max_abs_error_pp', 'max')).reset_index()
    ekf = summary[summary.method == 'EKF'].set_index('scenario').rmse_pp
    summary['rmse_reduction_vs_ekf_pct'] = [(1 - r / ekf[s]) * 100 for s, r in zip(summary.scenario, summary.rmse_pp)]
    summary.to_csv(OUT / 'summary.csv', index=False)

    config = {'schema_version': 1, 'fit_files': TRAIN, 'fit_source': 'outputs/predictions/ekf',
              'offset_soc': offset, 'offset_pp': offset * 100,
              'linear_coef': {'intercept': float(coef[0]), 'slope_on_soc_ekf': float(coef[1])},
              'clip_output': [0, 1], 'note': '仅用4条训练记录拟合；验证与测试只评价，不参与拟合或选择'}
    write_json(OUT / 'baseline_config.json', config)
    inputs = [f'outputs/predictions/ekf/{f}' for f in TRAIN + VALID] + \
             [f'outputs/predictions/fusion/{f}' for f in VALID] + \
             [f'outputs/experiments/predictions/{s}/{f}' for s in SCENARIOS for f in TEST]
    write_json(OUT / 'manifest.json', {
        'schema_version': 1, 'status': 'supplementary', 'producer': 'scripts/baseline_offset.py',
        'created_at': datetime.now(timezone.utc).isoformat(),
        'input_files': [{'path': p, 'sha256': sha(ROOT / p)} for p in inputs],
        'files': [{'path': f'outputs/baseline/{n}', 'sha256': sha(OUT / n)}
                  for n in ['metrics.csv', 'summary.csv', 'baseline_config.json']]})
    print(f'offset={offset * 100:.3f}pp  linear={coef}')
    print(summary.to_string(index=False))


if __name__ == '__main__':
    main()
