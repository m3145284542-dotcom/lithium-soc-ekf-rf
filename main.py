"""课程项目统一入口；默认只列出步骤，显式指定阶段才更新产物。"""
import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
STAGES = {
    'data': ['prepare_data.py', 'clean_data.py', 'build_reference.py', 'plot_inputs.py'],
    'model': ['build_model.py', 'plot_model.py'],
    'correction': ['train_correction.py', 'plot_correction.py'],
    'experiments': ['run_experiments.py', 'plot_experiments.py'],
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=[*STAGES, 'all'], help='运行指定阶段；all按依赖顺序运行全部阶段')
    parser.add_argument('--dry-run', action='store_true', help='只显示命令，不执行')
    args = parser.parse_args()
    stages = list(STAGES) if args.stage in (None, 'all') else [args.stage]
    for stage in stages:
        print(f'[{stage}]', flush=True)
        for script in STAGES[stage]:
            print(f'  {sys.executable} scripts/{script}', flush=True)
            if args.stage and not args.dry_run:
                subprocess.run([sys.executable, str(ROOT / 'scripts' / script)], cwd=ROOT, check=True)
    if args.stage is None:
        print('以上仅为步骤列表。快速复现实验：python main.py --stage experiments')


if __name__ == '__main__':
    main()
