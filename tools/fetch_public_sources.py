"""Download explicitly indexed public NASA sources, without modifying solver data."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    sources = json.loads((Path(__file__).resolve().parents[1] / 'docs' /
                          'public-validation-sources.json').read_text(encoding='utf-8'))
    args.out.mkdir(parents=True, exist_ok=True)
    manifest = args.out / 'manifest.json'
    previous = json.loads(manifest.read_text(encoding='utf-8')) if manifest.exists() else []
    prior = {row['id']: row for row in previous}
    rows = []
    for source in sources['sources']:
        if 'filename' not in source:
            continue
        url = source.get('download_url', source['url'])
        target = args.out / source['filename']
        row = dict(id=source['id'], url=url, filename=target.name)
        try:
            if target.exists():
                raw = target.read_bytes()
                digest = hashlib.sha256(raw).hexdigest()
                if source['id'] in prior and digest != prior[source['id']].get('sha256'):
                    raise ValueError('Existing file differs from recorded SHA-256; preserved for inspection')
                stamp = prior.get(source['id'], {}).get('downloaded_at', 'unknown (pre-existing file)')
            else:
                with urlopen(url, timeout=90) as response:
                    raw = response.read()
                if not raw.startswith(b'%PDF-'):
                    raise ValueError('Response is not a PDF')
                target.write_bytes(raw)
                digest = hashlib.sha256(raw).hexdigest()
                stamp = datetime.now(timezone.utc).isoformat()
            if not raw.startswith(b'%PDF-'):
                raise ValueError('Existing file is not a PDF')
            row.update(status='downloaded', downloaded_at=stamp, bytes=len(raw), sha256=digest)
        except (OSError, ValueError) as error:
            row.update(status='failed', error=str(error))
        rows.append(row)
        manifest.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(source['id'], row['status'], flush=True)
    return int(any(row['status'] != 'downloaded' for row in rows))


if __name__ == '__main__':
    raise SystemExit(main())
