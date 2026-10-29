"""一阶 RC 电池模型；放电电流为正，SOC 为 0~1。"""
import json
from pathlib import Path

import numpy as np
from scipy.interpolate import PchipInterpolator


class BatteryModel:
    def __init__(self, parameters):
        self.parameters = parameters
        self.capacity = parameters['capacity_ah']
        self.r0 = parameters['r0_ohm']
        self.r1 = parameters['r1_ohm']
        self.tau = parameters['tau_s']
        self.curve = PchipInterpolator(parameters['ocv_soc'], parameters['ocv_v'])
        self.slope = self.curve.derivative()

    def ocv(self, soc):
        return self.curve(np.clip(soc, 0, 1))

    def derivative(self, soc):
        return self.slope(np.clip(soc, 0, 1))

    @classmethod
    def load(cls, root):
        # 后续补偿阶段从此入口读取，拒绝尚未验收或已变化的模型。
        import hashlib
        root = Path(root)
        manifest = json.loads((root / 'outputs/model/manifest.json').read_text(encoding='utf-8'))
        if manifest['status'] != 'canonical':
            raise ValueError('电池模型尚未通过阶段验收')
        item = next(x for x in manifest['files'] if x['role'] == 'battery_parameters')
        path = root / item['path']
        if hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
            raise ValueError('电池参数哈希不匹配，请重新运行建模阶段')
        return cls(json.loads(path.read_text(encoding='utf-8')))
