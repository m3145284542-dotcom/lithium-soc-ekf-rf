"""只读盘点原始 CSV，用于确定清洗规则。"""
import io
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def read_raw(path):
    text = path.read_bytes().decode('utf-8-sig').replace('\x00', '')
    lines = text.splitlines()
    header = next(i for i, line in enumerate(lines) if line.startswith('Time Stamp,'))
    return pd.read_csv(io.StringIO('\n'.join(lines[header:])), skiprows=[1])


def seconds(series):
    parts = series.str.split(':', expand=True).astype(float)
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


if __name__ == '__main__':
    manifest = json.loads((ROOT / 'data/dataset_manifest.json').read_text(encoding='utf-8'))
    for item in manifest['files']:
        df = read_raw(ROOT / item['path'])
        t = seconds(df['Prog Time']); dt = t.diff()
        nums = df[['Voltage', 'Current', 'Temperature', 'Capacity']].apply(pd.to_numeric, errors='coerce')
        dq = nums.Capacity.diff(); integral = (nums.Current.shift() + nums.Current) / 2 * dt / 3600
        err = dq - integral
        print(Path(item['path']).name, 'n=',len(df), 'missing=',int(nums.isna().sum().sum()),
              'duplicates=',int(df.duplicated().sum()), 'dt<=0=',int((dt<=0).sum()),
              'dt=',round(dt.min(),4),round(dt.median(),4),round(dt.max(),4),
              'V=',round(nums.Voltage.min(),3),round(nums.Voltage.max(),3),
              'I=',round(nums.Current.min(),3),round(nums.Current.max(),3),
              'T=',round(nums.Temperature.min(),2),round(nums.Temperature.max(),2),
              'Q=',nums.Capacity.iloc[0], nums.Capacity.iloc[-1],
              'counter jumps=',int((err.abs()>.02).sum()), flush=True)
