"""随机森林误差补偿；特征只读取当前/历史测量与EKF输出。"""
import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

FEATURES = ['soc_ekf', 'voltage_v', 'current_a', 'temperature_degC',
            'voltage_residual_v', 'current_mean_5s_a', 'voltage_change_5s_v']
MEASUREMENTS = ['source_row', 'time_s', 'segment_id', 'voltage_v', 'current_a', 'temperature_degC']
EKF_COLUMNS = ['source_row', 'time_s', 'soc_ekf', 'voltage_residual_v']


def build_features(measurements, ekf):
    d = measurements[MEASUREMENTS].reset_index(drop=True)
    e = ekf[EKF_COLUMNS].reset_index(drop=True)
    if (len(d) != len(e) or not np.array_equal(d.source_row, e.source_row) or
            not np.allclose(d.time_s, e.time_s, rtol=0, atol=1e-6)):
        raise ValueError('测量与EKF预测未按source_row/time_s对齐')
    features = pd.DataFrame({'soc_ekf': e.soc_ekf, 'voltage_v': d.voltage_v,
                             'current_a': d.current_a, 'temperature_degC': d.temperature_degC,
                             'voltage_residual_v': e.voltage_residual_v})
    for _, part in d.groupby('segment_id', sort=False):
        t = part.time_s.to_numpy()
        if np.any(np.diff(t) <= 0):
            raise ValueError('段内时间必须严格递增')
        # 精确时间窗[t-5,t]，包括当前样本；开头使用已有数据，不跨segment。
        left = np.searchsorted(t, t - 5, side='left')
        current = part.current_a.to_numpy()
        cumulative = np.r_[0., np.cumsum(current)]
        mean = (cumulative[np.arange(len(t)) + 1] - cumulative[left]) / (np.arange(len(t)) - left + 1)
        voltage = part.voltage_v.to_numpy()
        features.loc[part.index, 'current_mean_5s_a'] = mean
        features.loc[part.index, 'voltage_change_5s_v'] = voltage - voltage[left]
    features = features[FEATURES]
    if not np.isfinite(features.to_numpy()).all():
        raise ValueError('特征含缺失或非有限值')
    return features


def predict_corrected(measurements, ekf, forest):
    correction = forest.predict(build_features(measurements, ekf))
    raw = ekf.soc_ekf.to_numpy() + correction
    return pd.DataFrame({'correction_soc': correction, 'soc_fused_unclipped': raw,
                         'soc_fused': np.clip(raw, 0, 1)})


def load_forest(root):
    root = Path(root)
    path = root / 'outputs/correction/manifest.json'
    manifest = json.loads(path.read_text(encoding='utf-8'))
    if manifest['status'] != 'canonical':
        raise ValueError('补偿模型尚未验收')
    # EKF或特征实现变化后必须重新生成，避免消费旧训练模型。
    for item in manifest['parents'] + manifest['producer_sources']:
        if hashlib.sha256((root / item['path']).read_bytes()).hexdigest() != item['sha256']:
            raise ValueError('补偿模型的上游或实现已变化，请重新训练')
    item = next(x for x in manifest['files'] if x['role'] == 'random_forest')
    model_path = root / item['path']
    if hashlib.sha256(model_path.read_bytes()).hexdigest() != item['sha256']:
        raise ValueError('随机森林文件哈希不匹配')
    return joblib.load(model_path)
