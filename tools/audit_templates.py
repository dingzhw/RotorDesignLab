"""Export source/assumption ledger without rebuilding historical templates."""
from pathlib import Path
import argparse
import json
import csv
from rotordesignlab.template_audit import audit


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out',type=Path,required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True,exist_ok=False)
    result = audit()
    (args.out/'audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    with (args.out/'模板参数来源.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['模板','参数路径','实际值','来源性质','来源与假设说明'])
        for row in result['parameters']:
            writer.writerow([row['template'],row['parameter'],json.dumps(row['value'],ensure_ascii=False),row['classification'],row['source']])
    print(f"Audited {len(result['templates'])} templates, {len(result['parameters'])} parameters")


if __name__ == '__main__':
    main()
