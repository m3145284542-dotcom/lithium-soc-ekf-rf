"""留出测试全部工况的SOC/误差图；不平滑或抽稀采样。"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.build_model import sha, write_json


def main():
    source = ROOT / 'outputs/experiments/manifest.json'
    manifest = json.loads(source.read_text(encoding='utf-8'))
    assert manifest['status'] == 'canonical'
    out = ROOT / 'outputs/figures/experiments'
    out.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({'font.family': 'sans-serif', 'font.sans-serif': ['Arial', 'DejaVu Sans'],
                         'font.size': 10, 'axes.spines.top': False, 'axes.spines.right': False,
                         'legend.frameon': False, 'pdf.fonttype': 42, 'svg.fonttype': 'none'})
    inputs, files = [], []
    for item in manifest['files']:
        if item['role'] != 'test_prediction':
            continue
        assert sha(ROOT / item['path']) == item['sha256']
        inputs.append(item)
        path = Path(item['path'])
        scenario, name = path.parent.name, path.stem
        d = pd.read_csv(ROOT / path)
        title = {'normal': 'Normal', 'initial_bias': 'Initial SOC = 90%',
                 'measurement_noise': 'Measurement noise'}[scenario]
        for kind in ['soc', 'error']:
            fig, ax = plt.subplots(figsize=(7.1, 3.7))
            fig.subplots_adjust(left=.13, right=.97, bottom=.17, top=.75)
            fig.suptitle(f'{name} | Test | {title}', fontsize=12, y=.96)
            if kind == 'soc':
                specs = [('soc_ref', 'Computed reference', '#474E58', 1.3),
                         ('soc_ekf', 'EKF', '#9B8BB4', 1.), ('soc_fused', 'EKF + RF', '#287F8E', 1.)]
                for column, label, color, width in specs:
                    ax.plot(d.time_s / 60, d[column] * 100, label=label, color=color,
                            linewidth=width, rasterized=True)
                ax.set_ylabel('SOC (%)')
            else:
                ax.axhline(0, color='#81858B', linewidth=.8, linestyle='--')
                ax.plot(d.time_s / 60, d.ekf_error_pp, label='EKF', color='#9B8BB4',
                        linewidth=1., rasterized=True)
                ax.plot(d.time_s / 60, d.fused_error_pp, label='EKF + RF', color='#287F8E',
                        linewidth=.8, rasterized=True)
                ax.set_ylabel('SOC error (percentage points)')
            ax.legend(loc='lower left', bbox_to_anchor=(0, 1.015), borderaxespad=0,
                      ncol=3, fontsize=9)
            ax.set_xlabel('Elapsed time (min)')
            ax.grid(axis='y', color='#E5E7EB', linewidth=.5)
            ax.set_axisbelow(True)
            ax.margins(x=0)
            stem = out / f'{scenario}_{name}_{kind}'
            fig.savefig(f'{stem}.png', dpi=300)
            fig.savefig(f'{stem}.pdf')
            fig.savefig(f'{stem}.svg')
            for ext in ['png', 'pdf', 'svg']:
                target = out / f'{scenario}_{name}_{kind}.{ext}'
                files.append({'path': target.relative_to(ROOT).as_posix(), 'sha256': sha(target)})
            plt.close(fig)
    notes = out / 'figure_notes.md'
    notes.write_text('# 最终实验图说明\n\n'
        '问题：固定随机森林是否改善留出记录的正常与扰动SOC估计？结论须结合主指标与局部误差，不预设所有情形改善。\n\n'
        '12张单面板图：3种设置×2条测试记录×SOC/误差；每条使用全部采样，不平滑、不截掉起始段。\n'
        'SOC图展示跟踪，误差图展示局部失败；方法配色和字号一致，纵轴按每图完整数据范围自动取值。\n'
        'Python/Matplotlib，7.1×3.7英寸，字号9pt以上，PNG 300dpi、可编辑文字PDF/SVG；密集曲线栅格化。\n'
        '单条时序非独立重复；固定一次噪声实现，无统计显著性检验或置信区间。参考值为计算SOC。\n'
        '课程测试项目：输入哈希检查及图像目视检查。单面板无需跨面板对齐。\n', encoding='utf-8')
    files.append({'path': notes.relative_to(ROOT).as_posix(), 'sha256': sha(notes)})
    write_json(out / 'manifest.json', {'schema_version': 1, 'status': 'canonical',
        'producer': 'scripts/plot_experiments.py', 'producer_sha256': sha(Path(__file__)),
        'created_at': datetime.now(timezone.utc).isoformat(),
        'parent_manifest': source.relative_to(ROOT).as_posix(), 'parent_manifest_sha256': sha(source),
        'acceptance': '六条正式预测哈希一致；12张完整时序图导出PNG/PDF/SVG',
        'inputs': inputs, 'files': files})
    print('Saved 12 test comparison figures:', out)


if __name__ == '__main__':
    main()
