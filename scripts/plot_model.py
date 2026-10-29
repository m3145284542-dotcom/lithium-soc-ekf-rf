"""绘制近似OCV与完整验证记录的EKF结果，不抽稀样本。"""
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.battery import BatteryModel


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    manifest_path = ROOT / 'outputs/model/manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    model = BatteryModel.load(ROOT)
    out = ROOT / 'outputs/figures/model'
    out.mkdir(parents=True, exist_ok=True)
    inputs, artifacts = [], []

    def checked(path):
        item = next(x for x in manifest['files'] + manifest['input_files'] if x['path'] == path)
        assert sha(ROOT / path) == item['sha256']
        inputs.append(item)
        return pd.read_csv(ROOT / path)

    plt.rcParams.update({'font.family': 'sans-serif', 'font.sans-serif': ['Arial', 'DejaVu Sans'],
                         'font.size': 10, 'axes.spines.top': False, 'axes.spines.right': False,
                         'legend.frameon': False, 'pdf.fonttype': 42, 'svg.fonttype': 'none'})

    def canvas(title, ylabel):
        fig, ax = plt.subplots(figsize=(7.1, 3.7))
        fig.subplots_adjust(left=.13, right=.97, bottom=.17, top=.85)
        ax.set_title(title, pad=16, fontsize=12)
        ax.set_ylabel(ylabel)
        ax.grid(axis='y', linewidth=.5, color='#E5E7EB')
        ax.set_axisbelow(True)
        return fig, ax

    def save(fig, stem):
        for ext in ['png', 'pdf', 'svg']:
            path = out / f'{stem}.{ext}'
            fig.savefig(path, dpi=220)
            artifacts.append({'path': path.relative_to(ROOT).as_posix(), 'sha256': sha(path)})
        plt.close(fig)

    raw = checked('data/processed/LG_HG2_25degC/549_C20DisCh.csv')
    raw = raw[raw.status.eq('DCH') & raw.current_a.gt(.1)].copy()
    soc = 1 + raw.capacity_raw_ah / model.capacity
    fig, ax = canvas('C/20 discharge | approximate OCV', 'Voltage (V)')
    ax.plot(soc * 100, raw.voltage_v, '.', color='#ADB5BD', markersize=3,
            label='Measured loaded voltage', rasterized=True)
    grid = np.linspace(0, 1, 501)
    ax.plot(grid * 100, model.ocv(grid), color='#7855A1', linewidth=1.5, label='Monotone OCV model')
    ax.set_xlabel('SOC on fixed 2.72639 Ah capacity axis (%)')
    ax.legend(loc='upper left', fontsize=9)
    save(fig, 'ocv_curve')

    # 同时展示两条预先指定的验证记录，不根据好坏挑选。
    for name in ['552_Mixed5', '552_Mixed6']:
        d = checked(f'outputs/predictions/ekf/{name}.csv')
        t = d.time_s / 60
        fig, ax = canvas(f'{name} | validation SOC', 'SOC (%)')
        ax.plot(t, d.soc_ref * 100, color='#474E58', linewidth=1.3, label='Computed reference', rasterized=True)
        ax.plot(t, d.soc_ekf * 100, color='#7855A1', linewidth=1., label='EKF', rasterized=True)
        ax.set_xlabel('Elapsed time (min)')
        ax.legend(loc='upper right', fontsize=9)
        ax.margins(x=0)
        save(fig, name + '_soc')
        fig, ax = canvas(f'{name} | EKF error against computed reference', 'SOC error (percentage points)')
        ax.axhline(0, color='#81858B', linewidth=.8, linestyle='--')
        ax.plot(t, d.error_pp, color='#7855A1', linewidth=.8, rasterized=True)
        ax.set_xlabel('Elapsed time (min)')
        ax.margins(x=0)
        save(fig, name + '_error')
    (out / 'figure_notes.md').write_text(
        '# 建模图表说明\n\n'
        'Python / Matplotlib；定量曲线，单面板，7.1×3.7英寸，PNG/PDF/SVG。\n\n'
        '- OCV图展示固定容量轴上的低倍率带载电压与单调拟合。负SOC源点仍展示，拟合仅限0~1。\n'
        '- 两条验证记录均展示全部采样：SOC图说明总体跟踪，误差图定位偏差时段。\n'
        '- 参考SOC为计算基准，非独立测量真值；没有重复实验，不绘制置信区间。\n'
        '- 每图仅一个坐标轴，无多面板对齐要求；按课程测试范围仅作数据哈希核对及图像目视检查。\n', encoding='utf-8')
    info = {'schema_version': 1, 'status': 'canonical', 'stage': '3_model_figures',
            'producer': 'scripts/plot_model.py', 'producer_sha256': sha(Path(__file__)),
            'created_at': datetime.now(timezone.utc).isoformat(),
            'parent_manifest': 'outputs/model/manifest.json', 'parent_manifest_sha256': sha(manifest_path),
            'inputs': inputs, 'files': artifacts,
            'acceptance': '模型与数据哈希核对；两条验证记录全采样；单面板PNG/PDF/SVG导出',
            'scope': '课程测试项目结果图；无最终测试或融合结果'}
    (out / 'manifest.json').write_text(json.dumps(info, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Saved 5 figures:', out)


if __name__ == '__main__':
    main()
