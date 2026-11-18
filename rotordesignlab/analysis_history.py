"""Immutable local analysis archives; reopening never overwrites their inputs."""
from datetime import datetime, timezone
from io import BytesIO
import json
import os
from pathlib import Path
import re
from uuid import uuid4
from zipfile import ZipFile, ZIP_DEFLATED, BadZipFile

from . import designs

LIBRARY = designs.ROOT / 'private' / 'assembly-results'


def save(record):
    root = Path(LIBRARY)
    root.mkdir(parents=True, exist_ok=True)
    identifier = uuid4().hex
    meta = {key: record[key] for key in ('answer', 'case', 'task', 'input_fingerprint', 'fingerprint', 'context')}
    meta.update(created_utc=datetime.now(timezone.utc).isoformat(), name=record['design']['aircraft']['name'],
                schema_version=1, aircraft_id=record['design']['aircraft']['id'])
    metadata = json.dumps(meta, ensure_ascii=False, allow_nan=False).encode('utf-8')
    if (len(metadata) > 16*1024**2 or len(record['files']) + 1 > 10000 or
            len(metadata) + sum(len(data) for data in record['files'].values()) > 512*1024**2):
        raise ValueError('历史结果包超过读取容量，请下载本次结果包保留。')
    stream = BytesIO()
    with ZipFile(stream, 'w', ZIP_DEFLATED) as archive:
        archive.writestr('history-record.json', metadata)
        for name, data in record['files'].items():
            archive.writestr(name, data)
    temporary = root / (identifier + '.tmp')
    try:
        with temporary.open('xb') as target:
            target.write(stream.getvalue())
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, root / (identifier + '.zip'))
    finally:
        if temporary.exists():
            temporary.unlink()
    return identifier


def entries(context):
    rows = []
    for path in sorted(Path(LIBRARY).glob('*.zip'), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            with ZipFile(path) as archive:
                if archive.getinfo('history-record.json').file_size > 16*1024**2:
                    continue
                meta = json.loads(archive.read('history-record.json'))
            if meta['context'] == context:
                rows.append((path.stem, meta['created_utc'], meta['name']))
        except (OSError, ValueError, KeyError, BadZipFile):
            continue
    return rows


def load(identifier):
    if not re.fullmatch('[a-f0-9]{32}', identifier):
        raise ValueError('无效结果编号。')
    with ZipFile(Path(LIBRARY) / (identifier + '.zip')) as archive:
        entries = archive.infolist()
        if len(entries) > 10000 or len({e.filename for e in entries}) != len(entries) or sum(e.file_size for e in entries) > 512*1024**2:
            raise ValueError('历史结果包过大或含重复文件。')
        meta = json.loads(archive.read('history-record.json'))
        if meta['schema_version'] != 1:
            raise ValueError('历史结果版本不受支持。')
        files = {e.filename: archive.read(e.filename) for e in entries if e.filename != 'history-record.json'}
    record = {key: meta[key] for key in ('answer', 'case', 'task', 'input_fingerprint', 'fingerprint', 'context')}
    record.update(files=files, design=designs.unpack(files['design.rdl']), history_id=identifier)
    return record
