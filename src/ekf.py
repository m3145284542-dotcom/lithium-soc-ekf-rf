"""SOC / 极化电压双状态 EKF，仅接收时间、电流和电压。"""
import numpy as np
import pandas as pd


def estimate(inputs, model, settings):
    t = inputs.time_s.to_numpy()
    current = inputs.current_a.to_numpy()
    voltage = inputs.voltage_v.to_numpy()
    segment = inputs.segment_id.to_numpy()
    n = len(inputs)
    result = np.empty((n, 7))
    soc = settings['initial_soc']
    up = settings['initial_polarization_v']
    p00, p11 = np.square(settings['initial_std'])
    p01 = 0.
    q_soc, q_up = settings['process_variance_per_s']
    r = settings['voltage_std_v'] ** 2
    # 分段不能以参考SOC重置；缺失区间无法独立传播时明确停止。
    if np.any(np.diff(segment) != 0) or np.any(np.diff(t) <= 0):
        raise ValueError('EKF要求单条连续且时间严格递增的记录；请按segment_id单独运行')
    for k in range(n):
        if k:
            dt = t[k] - t[k - 1]
            a = np.exp(-dt / model.tau)
            # 实测采样间隔变化，采用相邻电流均值近似区间输入。
            mean_i = (current[k - 1] + current[k]) / 2
            soc -= mean_i * dt / (3600 * model.capacity)
            up = a * up + model.r1 * (1 - a) * mean_i
            p00 += q_soc * dt
            p01 *= a
            p11 = a * a * p11 + q_up * model.tau / 2 * (1 - a * a)
        raw_prediction_soc = soc
        soc = float(np.clip(soc, 0, 1))
        predicted_v = float(model.ocv(soc)) - up - model.r0 * current[k]
        innovation = voltage[k] - predicted_v
        h = float(model.derivative(soc))
        z0, z1 = p00 * h - p01, p01 * h - p11
        variance = h * z0 - z1 + r
        k0, k1 = z0 / variance, z1 / variance
        raw_soc = soc + k0 * innovation
        soc = float(np.clip(raw_soc, 0, 1))
        up += k1 * innovation
        # Joseph形式：保持对称性和协方差非负。
        p = np.array([[p00, p01], [p01, p11]])
        gain = np.array([k0, k1])
        b = np.eye(2) - np.outer(gain, [h, -1.])
        p = b @ p @ b.T + r * np.outer(gain, gain)
        p00, p01, p11 = p[0, 0], p[0, 1], p[1, 1]
        result[k] = (soc, up, predicted_v, innovation, raw_soc,
                     raw_prediction_soc, p00)
    if not np.isfinite(result).all() or np.any(result[:, -1] < -1e-12):
        raise ValueError('EKF出现非有限值或负方差')
    return pd.DataFrame(result, columns=['soc_ekf', 'polarization_v', 'voltage_pred_v',
                                       'voltage_residual_v', 'soc_update_unclipped',
                                       'soc_predict_unclipped', 'soc_variance'])
