"""两条验证记录的EKF/随机森林融合对照图，保留全部采样。"""
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
    manifest_path = ROOT / 'outputs/correction/manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    assert manifest['status'] == 'canonical'
    out = ROOT / 'outputs/figures/correction'
    out.mkdir(parents=True, exist_ok=True)
    inputs, files = [], []
    plt.rcParams.update({'font.family': 'sans-serif', 'font.sans-serif': ['Arial', 'DejaVu Sans'],
                         'font.size': 10, 'axes.spines.top': False, 'axes.spines.right': False,
                         'legend.frameon': False, 'pdf.fonttype': 42, 'svg.fonttype': 'none'})
    for name in ['552_Mixed5', '552_Mixed6']:
        item = next(x for x in manifest['files'] if x['path'] == f'outputs/predictions/fusion/{name}.csv')
        path = ROOT / item['path']
        assert sha(path) == item['sha256']
        inputs.append(item)
        d = pd.read_csv(path)
        for kind in ['soc', 'error']:
            fig, ax = plt.subplots(figsize=(7.1, 3.7))
            fig.subplots_adjust(left=.13, right=.97, bottom=.17, top=.85)
            ax.set_title(f'{name} | validation ' + ('SOC' if kind == 'soc' else 'error'), fontsize=12, pad=16)
            if kind == 'soc':
                specs = [('soc_ref', 'Computed reference', '#474E58', 1.3),
                         ('soc_ekf', 'EKF', '#9B8BB4', 1.), ('soc_fused', 'EKF + RF', '#287F8E', 1.)]
                for column, label, color, width in specs:
                    ax.plot(d.time_s / 60, d[column] * 100, label=label, color=color,
                            linewidth=width, rasterized=True)
                ax.set_ylabel('SOC (%)')
                ax.legend(loc='upper right', fontsize=9)
            else:
                ax.axhline(0, color='#81858B', linewidth=.8, linestyle='--')
                ax.plot(d.time_s / 60, d.ekf_error_pp, label='EKF', color='#9B8BB4',
                        linewidth=1., rasterized=True)
                ax.plot(d.time_s / 60, d.fused_error_pp, label='EKF + RF', color='#287F8E',
                        linewidth=.8, rasterized=True)
                ax.set_ylabel('SOC error (percentage points)')
                ax.legend(loc='lower left', fontsize=9)
            ax.set_xlabel('Elapsed time (min)')
            ax.grid(axis='y', color='#E5E7EB', linewidth=.5)
            ax.set_axisbelow(True)
            ax.margins(x=0)
            for ext in ['png', 'pdf', 'svg']:
                target = out / f'{name}_{kind}.{ext}'
                fig.savefig(target, dpi=220)
                files.append({'path': target.relative_to(ROOT).as_posix(), 'sha256': sha(target)})
            plt.close(fig)
    notes = out / 'figure_notes.md'
    notes.write_text('# 融合结果图说明\n\n'
                     'Python/Matplotlib，单面板，7.1×3.7英寸；输出PNG/PDF/SVG，全部采样绘制。\n\n'
                     'SOC图回答融合后能否跟踪计算参考值，误差图定位相对于EKF改善或变差的时段。\n'
                     '两个验证记录均展示，不挑选表现较好的记录；这些记录参与过选型，不是最终测试。\n'
                     '参考SOC是容量计数器构造的基准；无重复实验，不绘制置信区间。\n'
                     '课程测试项目仅做数据哈希及图像目视检查，无多面板对齐要求。\n', encoding='utf-8')
    files.append({'path': notes.relative_to(ROOT).as_posix(), 'sha256': sha(notes)})
    write_json(out / 'manifest.json', {'schema_version': 1, 'status': 'canonical',
               'producer': 'scripts/plot_correction.py', 'producer_sha256': sha(Path(__file__)),
               'created_at': datetime.now(timezone.utc).isoformat(),
               'parent_manifest': manifest_path.relative_to(ROOT).as_posix(), 'parent_manifest_sha256': sha(manifest_path),
               'acceptance': '两条验证记录的全采样对照，输入哈希一致，PNG/PDF/SVG导出',
               'inputs': inputs, 'files': files})
    print('Saved 4 comparison figures:', out)


if __name__ == '__main__':
    main()
