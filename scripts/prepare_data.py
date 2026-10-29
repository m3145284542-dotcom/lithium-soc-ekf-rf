"""阶段 1：下载原始 CSV，校验完整性，保存固定划分。仅使用 Python 标准库。"""
import csv
import hashlib
import io
import json
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/LG_HG2_25degC"
SOURCE = "https://data.mendeley.com/datasets/b5mj79w5w9/2"
SPLITS = {
    "capacity_reference": ["551_Cap_1C.csv"],
    "capacity_check": ["552_Cap_1C.csv"],
    "ocv_model": ["549_C20DisCh.csv"],
    "rc_model": ["549_HPPC.csv"],
    "train": ["551_Mixed1.csv", "551_Mixed2.csv", "552_Mixed3.csv", "552_Mixed4.csv"],
    "validation": ["552_Mixed5.csv", "552_Mixed6.csv"],
    "test": ["552_Mixed7.csv", "552_Mixed8.csv"],
    "charge_context": ["549_Charge.csv"]
    + [f"551_Charge{i}.csv" for i in range(1, 9)]
    + [f"552_Charge{i}.csv" for i in range(9, 17)],
}


def inspect_csv(path):
    # 只作原始数据盘点，不清洗、不积分、不拟合，不根据测试内容调整方案。
    text = path.read_bytes().decode("utf-8-sig", errors="replace").replace("\x00", "")
    lines = text.splitlines()
    header = next(i for i, line in enumerate(lines) if line.startswith("Time Stamp,"))
    reader = csv.DictReader(io.StringIO("\n".join(lines[header:])))
    fields = reader.fieldnames
    required = {"Time Stamp", "Prog Time", "Voltage", "Current", "Temperature", "Capacity"}
    if not required.issubset(fields):
        raise ValueError(f"{path.name}: 缺少必要字段")
    next(reader)  # 原始单位行。
    count, first, last = 0, None, None
    for row in reader:
        if not row["Time Stamp"]:
            continue
        if first is None:
            first = row
        last = row
        count += 1
    if not count:
        raise ValueError(f"{path.name}: 无数据行")
    return {"rows": count, "columns": [f for f in fields if f],
            "first_timestamp": first["Time Stamp"], "last_timestamp": last["Time Stamp"]}


def acquire(item):
    name = item["filename"]
    path = RAW / name
    details = item["content_details"]
    expected = details["sha256_hash"]
    if not path.exists():
        partial = path.with_suffix(".csv.part")
        for attempt in range(3):
            try:
                request = urllib.request.Request(details["download_url"], headers={"User-Agent": "LG-HG2-course-project/1.0"})
                with urllib.request.urlopen(request, timeout=90) as response, partial.open("wb") as output:
                    while chunk := response.read(1024 * 1024):
                        output.write(chunk)
                if partial.stat().st_size != item["size"] or hashlib.sha256(partial.read_bytes()).hexdigest() != expected:
                    raise ValueError(f"{name}: 下载大小或哈希不匹配")
                partial.replace(path)
                break
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(2)
    size = path.stat().st_size
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if size != item["size"] or digest != expected:
        raise ValueError(f"{name}: 已有文件校验失败，未覆盖原文件")
    record = {"path": path.relative_to(ROOT).as_posix(), "status": "canonical",
              "role": next(role for role, names in SPLITS.items() if name in names),
              "source_filename": name, "source_file_id": item["id"],
              "download_url": details["download_url"], "bytes": size, "sha256": digest,
              "acceptance": "与来源清单字节数及 SHA-256 一致，必要字段及非空记录已确认",
              **inspect_csv(path)}
    print(f"OK {name}: {record['rows']} rows, {size} bytes", flush=True)
    return record


def main():
    items = json.loads((RAW / "source_files_manifest.json").read_text(encoding="utf-8-sig"))
    wanted = [name for names in SPLITS.values() for name in names]
    lookup = {item["filename"]: item for item in items}
    if len(wanted) != len(set(wanted)):
        raise ValueError("数据用途重复")
    with ThreadPoolExecutor(max_workers=4) as pool:
        records = list(pool.map(acquire, [lookup[name] for name in wanted]))
    manifest = {"schema_version": 1, "stage": 1, "status": "canonical",
                "scope": "原始数据收集与划分；尚未清洗、构造 SOC 或训练模型",
                "producer": "scripts/prepare_data.py", "created_at": datetime.now(timezone.utc).isoformat(),
                "source": {"url": SOURCE, "doi": "10.17632/b5mj79w5w9.2", "version": 2,
                           "license": "CC BY 4.0", "temperature_degC": 25,
                           "catalog_path": "data/raw/LG_HG2_25degC/source_files_manifest.json",
                           "catalog_sha256": hashlib.sha256((RAW / "source_files_manifest.json").read_bytes()).hexdigest()},
                "split_policy": "按完整工况固定划分；测试集不用于拟合或调参；充电记录仅作上下文，逐条关联留待阶段2",
                "splits": SPLITS, "files": records}
    (ROOT / "data/dataset_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    total = sum(record["bytes"] for record in records)
    rows = ["# 第一阶段数据清单", "", f"已完成 {len(records)} 个原始 CSV，共 {total:,} 字节（{total / 1024**2:.2f} MiB）。",
            "全部文件已通过来源清单的大小、SHA-256、必要字段及非空记录检查。", "",
            "固定用途及下载来源以 `data/dataset_manifest.json` 为准。行数不含说明、表头、单位行。", "",
            "| 文件 | 用途 | 数据行数 | 首条采样时间 | 末条采样时间 |", "|---|---|---:|---|---|"]
    rows += [f"| {Path(r['path']).name} | {r['role']} | {r['rows']:,} | {r['first_timestamp']} | {r['last_timestamp']} |" for r in records]
    rows += ["", "本阶段仅确认原始文件完整并冻结工况划分。初始满电状态、充电记录对应关系、时间连续性、容量计数器及参考 SOC 在第二阶段处理。",
             "充电编号不作为与 Mixed 编号一一对应的证据；容量取值也尚未由测试数据确定。", ""]
    (ROOT / "data/数据清单.md").write_text("\n".join(rows), encoding="utf-8")
    print(f"COMPLETE: {len(records)} files, {total:,} bytes", flush=True)


if __name__ == "__main__":
    main()
