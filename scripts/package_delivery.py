"""按显式目录打包课程项目，排除缓存和临时预览，保留完整复现输入。"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def item(path):
    return {'path': path.relative_to(ROOT).as_posix(), 'bytes': path.stat().st_size, 'sha256': sha(path)}


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    parents = []
    for rel in ['outputs/model/manifest.json', 'outputs/correction/manifest.json',
                'outputs/experiments/manifest.json', 'outputs/figures/experiments/manifest.json']:
        path = ROOT / rel
        manifest = json.loads(path.read_text(encoding='utf-8'))
        if manifest['status'] != 'canonical':
            raise ValueError(f'上游未正式验收：{rel}')
        # 检查交付所引用的正式来源，不重新运行模型。
        for group in ['parents', 'input_files', 'producer_sources', 'files']:
            for entry in manifest.get(group, []):
                if 'path' in entry and 'sha256' in entry:
                    target = ROOT / entry['path']
                    if sha(target) != entry['sha256']:
                        raise ValueError(f'上游文件已变化：{entry["path"]}')
        parents.append(item(path))
    slides = ROOT / 'presentation/SOC融合估计_6分钟汇报.pptx'
    with zipfile.ZipFile(slides) as deck:
        count = sum(n.startswith('ppt/slides/slide') and n.endswith('.xml') for n in deck.namelist())
        if count != 7:
            raise ValueError(f'PPT应为7页，实际{count}页')
    materials = [slides, ROOT / 'presentation/6分钟讲稿与答辩.md',
                 ROOT / 'presentation/贡献记录与个人反思.md', ROOT / '交付说明.md']
    sources = [ROOT / 'main.py', ROOT / 'README.md', ROOT / '项目大纲与执行计划.md',
               ROOT / 'work/presentation-build/build.mjs']
    write(ROOT / 'presentation/manifest.json', {
        'schema_version': 1, 'stage': '6_delivery', 'status': 'canonical',
        'created_at': datetime.now(timezone.utc).isoformat(),
        'producer': 'scripts/package_delivery.py',
        'role': '课程技术成果与展示材料；个人贡献记录为成员待填写模板',
        'acceptance': '7页PPT已渲染检查；指标引用既有正式实验；上游哈希匹配；仅作交付基本检查',
        'parents': parents, 'files': [item(p) for p in materials],
        'supporting_sources': [item(p) for p in sources],
        'pending_human_items': ['实际组员身份', '真实贡献及比例', '个人反思', '真人计时演练'],
    })
    files = []
    for dirname in ['data', 'outputs', 'scripts', 'src', 'presentation']:
        files.extend(p for p in (ROOT / dirname).rglob('*')
                     if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc')
    files.extend(ROOT / p for p in ['main.py', 'README.md', 'requirements.txt',
                                  '项目大纲与执行计划.md', '数据选型说明.md', '交付说明.md',
                                  'work/deepseek-handoffs.md', 'work/presentation-build/build.mjs'])
    files = sorted(set(files))
    delivery = ROOT / 'delivery'
    delivery.mkdir(exist_ok=True)
    package = delivery / 'SOC融合估计_完整交付.zip'
    with zipfile.ZipFile(package, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in files:
            archive.write(path, 'SOC融合估计/' + path.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(package) as archive:
        if len(archive.namelist()) != len(files):
            raise ValueError('打包文件数量不符')
        bad = archive.testzip()
        if bad:
            raise ValueError(f'压缩包CRC失败：{bad}')
    receipt = {
        'schema_version': 1, 'status': 'canonical', 'producer': 'scripts/package_delivery.py',
        'created_at': datetime.now(timezone.utc).isoformat(), 'package': item(package),
        'file_count': len(files), 'uncompressed_bytes': sum(p.stat().st_size for p in files),
        'checks': {'zip_crc': 'passed', 'pptx_slides': count, 'upstream_hashes': 'passed'},
        'files': [item(p) for p in files],
    }
    write(delivery / '交付包校验.json', receipt)
    print(json.dumps({k: receipt[k] for k in ['package', 'file_count', 'checks']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
