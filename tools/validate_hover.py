"""Offline milestone acceptance: templates, grids, design maps and timing."""
import argparse
import hashlib
import json
import platform
from pathlib import Path
from unittest.mock import patch

from rotordesignlab.batch import run_batch
from rotordesignlab.cases import read_case,run_case,write_json


def main(out):
    base=Path(__file__).resolve().parents[1]/'examples/hover'
    out.mkdir(parents=True,exist_ok=True)
    record=dict(platform=platform.platform(),processor=platform.processor(),python=platform.python_version(),
                grid='240 radial panels per rotor unless specified',points={},batches={},grid_checks={})
    if platform.system()=='Windows':
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r'HARDWARE\DESCRIPTION\System\CentralProcessor\0') as key:
            record['hardware']=winreg.QueryValueEx(key,'ProcessorNameString')[0].strip()
    record['input_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in base.iterdir() if p.is_file()}
    with patch('socket.socket.connect',side_effect=RuntimeError('offline acceptance')):
        for name in ('synthetic','uh60-public'):
            case=read_case(base/f'{name}-case.json');answers=[]
            for n in (120,240,480):
                r=run_case(dict(case,radial_stations=n),base,out/f'{name}-{n}')
                assert r['status']=='converged',r
                answers.append(r)
            record['points'][name]=dict(summary=answers[1]['summary'],elapsed_s=answers[1]['elapsed_s'])
            changes={key:abs(answers[-1]['summary'][key]/answers[-2]['summary'][key]-1) for key in
                     ('main_thrust_n','main_torque_nm','tail_thrust_n','tail_torque_nm','required_power_w')}
            assert max(changes.values())<=.002,changes
            record['grid_checks'][name]=changes
        for name in ('mass-altitude','main-design','tail-design','three-candidates','hundred-points'):
            spec=read_case(base/f'{name}.json')
            r=run_batch(spec,base,out/name)
            assert r['summary']['total']>=3,r
            record['batches'][name]=r
    write_json(out/'acceptance.json',record)
    print(json.dumps(record,ensure_ascii=True))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True)
    main(parser.parse_args().out)
