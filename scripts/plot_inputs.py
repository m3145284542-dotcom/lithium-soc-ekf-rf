"""绘制训练工况Mixed1的全部输入和计算参考SOC，不进行数据抽稀。"""
import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--qa-tools', type=Path, help='可选：本地nature-figure技能scripts目录，用于额外布局检查')
    args = parser.parse_args()
    manifest_path = ROOT / 'data/reference/manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    assert manifest['status'] == 'canonical'
    item = next(r for r in manifest['files'] if Path(r['path']).name == '551_Mixed1.csv')
    source = ROOT / item['path']
    assert hashlib.sha256(source.read_bytes()).hexdigest() == item['sha256']
    df = pd.read_csv(source)
    assert len(df) == item['rows'] and df.time_s.diff().iloc[1:].gt(0).all()
    plt.rcParams.update({'font.family': 'sans-serif', 'font.sans-serif': ['Arial', 'DejaVu Sans'],
                         'font.size': 9, 'axes.labelsize': 9, 'xtick.labelsize': 9, 'ytick.labelsize': 9,
                         'pdf.fonttype': 42, 'svg.fonttype': 'none',
                         'axes.spines.top': False, 'axes.spines.right': False,
                         'axes.linewidth': .7, 'legend.frameon': False})
    fig, axes = plt.subplots(4, 1, sharex=True, figsize=(7.0866, 8.6614))  # 180 × 220 mm。
    fig.subplots_adjust(left=.16, right=.97, bottom=.075, top=.91, hspace=.36)
    fig.suptitle('Mixed1 | measured inputs and reference SOC', fontsize=11, y=.97)
    fig.text(.16, .935, 'Reference: coulomb counter / 2.72639 Ah; initial SOC assumed full', fontsize=9)
    specs = [('voltage_v', 'Voltage (V)', '#4F6480'),
             ('current_a', 'Current (A)', '#4F6480'),
             ('temperature_degC', 'Temperature (°C)', '#4F6480'),
             ('soc_ref_pct', 'Reference SOC (%)', '#8653AB')]
    for letter, ax, (column, label, color) in zip('abcd', axes, specs):
        ax.set_label(letter)
        ax.plot(df.time_s / 60, df[column], color=color, linewidth=.65, rasterized=True)
        ax.set_ylabel(label, labelpad=9)
        ax.text(-.14, 1.04, letter, transform=ax.transAxes, fontsize=10, fontweight='bold')
        ax.margins(x=0, y=.08)
        ax.grid(axis='y', color='#E6E8EC', linewidth=.5)
        ax.set_axisbelow(True)
    axes[-1].set_xlabel('Elapsed time (min)')
    fig.align_ylabels(axes)
    fig.canvas.draw()
    out = ROOT / 'outputs/figures'
    out.mkdir(parents=True, exist_ok=True)
    stem = out / 'Mixed1_inputs_reference'
    qa = 'not_run'
    if args.qa_tools:
        sys.path.insert(0, str(args.qa_tools))
        from audit_panel_alignment import require_matplotlib_panel_alignment
        require_matplotlib_panel_alignment(fig, json_out=str(stem)+'.alignment.json',
                                          tolerance_pt=1.5, gutter_tolerance_pt=1.5,
                                          require_panel_labels=True, strict=True)
        qa = 'passed'
    fig.savefig(str(stem)+'.png', dpi=300)
    fig.savefig(str(stem)+'.pdf', dpi=300)
    fig.savefig(str(stem)+'.svg', dpi=300)
    plt.close(fig)
    info = {'schema_version': 1, 'status': 'canonical', 'producer': 'scripts/plot_inputs.py',
            'created_at': datetime.now(timezone.utc).isoformat(),
            'producer_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'acceptance': '全部来源采样绘制，输入哈希匹配，已导出PNG/PDF/SVG；本次布局和PDF检查见QA.md',
            'source_path': item['path'], 'source_sha256': item['sha256'],
            'source_rows': len(df), 'plotted_rows': len(df),
            'description': '完整训练记录输入和计算参考SOC，不是算法预测结果',
            'alignment_qa': qa,
            'files': [{'path': p.relative_to(ROOT).as_posix(),
                       'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
                      for p in [Path(str(stem)+'.png'), Path(str(stem)+'.pdf'), Path(str(stem)+'.svg')]]}
    (out / 'manifest.json').write_text(json.dumps(info, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print('Saved', stem, 'PNG/PDF;', len(df), 'samples')


if __name__ == '__main__':
    main()
