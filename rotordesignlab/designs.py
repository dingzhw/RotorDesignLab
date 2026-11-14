"""Portable, versioned user designs. Solver inputs retain their existing schema."""
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from uuid import uuid4
from zipfile import ZipFile, ZIP_DEFLATED, BadZipFile

import jsonschema
from .aircraft import ROOT, SCHEMA, SCHEMA_V2, read_aircraft, require_analysis
from .cases import read_rotor, write_json

LIBRARY = ROOT / 'private/designs'
TEMPLATES = {
    '200 kg 合成无人直升机': ROOT/'examples/public-helicopter/synthetic.json',
    'UH-60 公开部件模型（含工程估计）': ROOT/'examples/public-helicopter/uh60-public.json',
    '三片叶孤立旋翼示例（兼容旧版）': ROOT/'examples/synthetic-aircraft.json',
}


def digest(value):
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()).hexdigest()


def from_template(name):
    path=TEMPLATES[name]; aircraft=read_aircraft(path); assets={}
    for i,rotor in enumerate(aircraft['rotors']):
        for key in ('geometry_csv','polar_csv','polar_json'):
            if key not in rotor:continue
            target=f'rotor-{i}-{key.replace("_", ".")}'
            assets[target]=(path.parent/rotor[key]).read_text(encoding='utf-8-sig')
            rotor[key]=target
    return dict(format_version=1,template=name,aircraft=aircraft,assets=assets,settings={})


def materialize(design, directory):
    """Write only normalized asset names to a task-owned empty directory."""
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    for name,content in design['assets'].items():
        if not re.fullmatch(r'rotor-\d+-(geometry\.csv|polar\.(csv|json))',name):
            raise ValueError('方案含无效的数据表名称。')
        with (directory/name).open('x',encoding='utf-8',newline='') as stream:stream.write(content)
    write_json(directory/'aircraft.json',design['aircraft'])
    return directory/'aircraft.json'


def issues(design, analysis=None):
    """Collect field-level structure errors, then reuse solver input validation."""
    from .parameter_fields import location, schema_message
    errors=[];a=design['aircraft']
    try:digest(design)
    except (ValueError,TypeError):return ['方案：含空值以外的非有限数值或无效数据类型。']
    schema=SCHEMA_V2 if a.get('schema_version')==2 else SCHEMA
    for error in jsonschema.Draft202012Validator(schema).iter_errors(a):
        errors.append(location(list(error.absolute_path))+'：'+schema_message(error))
    if errors:return errors
    with TemporaryDirectory(prefix='rdl-check-') as temp:
        try:
            path=materialize(design,temp);read_aircraft(path)
        except (ValueError,OSError,KeyError,TypeError) as error:return ['机型参数：'+str(error)]
        if analysis is not None:
            try:require_analysis(a,analysis)
            except (ValueError,KeyError,TypeError) as error:errors.append('分析用途：'+str(error))
        for rotor in a['rotors']:
            label='主旋翼' if rotor.get('role','main')=='main' else '尾桨'
            if rotor['geometry_csv'] not in design['assets'] or rotor.get('polar_json',rotor.get('polar_csv')) not in design['assets']:
                errors.append(label+'：缺少几何或翼型数据表。');continue
            cfg=dict(rotor,**rotor['defaults'],axial_speed_m_s=0.,density_kg_m3=1.225)
            try:read_rotor(cfg,Path(temp))
            except (ValueError,OSError,KeyError,TypeError) as error:errors.append(label+' / 几何与气动：'+str(error))
    return errors


def pack(design):
    errors=issues(design)
    if errors:raise ValueError('\n'.join(errors))
    manifest={k:deepcopy(v) for k,v in design.items() if k!='assets'}
    manifest['asset_hashes']={k:sha256(v.encode('utf-8')).hexdigest() for k,v in design['assets'].items()}
    stream=BytesIO()
    with ZipFile(stream,'w',ZIP_DEFLATED) as z:
        z.writestr('design.json',json.dumps(manifest,ensure_ascii=False,allow_nan=False))
        for name,text in design['assets'].items():z.writestr(name,text.encode('utf-8'))
    return stream.getvalue()


def unpack(data):
    if len(data)>32*1024**2:raise ValueError('方案包超过32 MB。')
    try:
        with ZipFile(BytesIO(data)) as z:
            records=z.infolist();names=[f.filename for f in records]
            if len(records)>50 or len(set(names))!=len(names) or sum(f.file_size for f in records)>32*1024**2:
                raise ValueError('方案包过大或存在重复文件。')
            manifest=json.loads(z.read('design.json'))
            if (set(manifest)!={'format_version','template','aircraft','settings','asset_hashes'} or
                type(manifest['format_version']) is not int or manifest['format_version']!=1 or
                not isinstance(manifest['settings'],dict) or not isinstance(manifest['aircraft'],dict)):
                raise ValueError('方案格式或版本不受支持。')
            hashes=manifest.pop('asset_hashes')
            if set(names)!={'design.json',*hashes}:raise ValueError('方案包文件清单不一致。')
            assets={name:z.read(name).decode('utf-8') for name in hashes}
            if any(sha256(text.encode('utf-8')).hexdigest()!=hashes[name] for name,text in assets.items()):
                raise ValueError('方案包数据校验失败。')
            manifest['assets']=assets
        errors=issues(manifest)
        if errors:raise ValueError('\n'.join(errors))
        return manifest
    except (BadZipFile,KeyError,TypeError,UnicodeError,RuntimeError) as error:
        raise ValueError('无法读取方案包：'+str(error)) from error


def saved_designs(library=None):
    library=LIBRARY if library is None else library
    result=[]
    for path in sorted(Path(library).glob('*.rdl'),key=lambda p:p.stat().st_mtime,reverse=True):
        try:
            design=unpack(path.read_bytes())
            result.append((path.stem,design['aircraft']['name']))
        except (ValueError,OSError):continue
    return result


def load_design(identifier,library=None):
    library=LIBRARY if library is None else library
    if not re.fullmatch(r'[a-f0-9]{32}',identifier):raise ValueError('无效的方案编号。')
    data=(Path(library)/(identifier+'.rdl')).read_bytes()
    return unpack(data),sha256(data).hexdigest()


def save_design(design,identifier=None,expected=None,library=None):
    """Atomic write, optimistic concurrency and recoverable prior revisions."""
    data=pack(design);library=Path(LIBRARY if library is None else library);library.mkdir(parents=True,exist_ok=True)
    identifier=identifier or uuid4().hex
    if not re.fullmatch(r'[a-f0-9]{32}',identifier):raise ValueError('无效的方案编号。')
    path=library/(identifier+'.rdl');lock=path.with_suffix('.lock');temporary=None
    try:
        handle=lock.open('x')
    except FileExistsError as error:raise ValueError('此方案正在保存，请稍后重试。') from error
    try:
        if path.exists():
            old=path.read_bytes();oldhash=sha256(old).hexdigest()
            if expected!=oldhash:raise ValueError('方案已被另一窗口修改，请先另存为新方案，或重新打开后再编辑。')
            history=library/'history';history.mkdir(exist_ok=True)
            backup=history/f'{identifier}-{oldhash}.rdl'
            if not backup.exists():backup.write_bytes(old)
        elif expected is not None:raise ValueError('原方案已不存在，请另存为新方案。')
        temporary=library/(uuid4().hex+'.tmp');temporary.write_bytes(data);os.replace(temporary,path)
    finally:
        handle.close();lock.unlink()
        if temporary and temporary.exists():temporary.unlink()
    return identifier,sha256(data).hexdigest()


def execute(design,case,batch=None):
    """Same CLI solver, with an immutable submitted design and portable exports."""
    from .cases import run_case
    from .batch import run_batch
    design=deepcopy(design);case=deepcopy(case)
    errors=issues(design,case.get('analysis'))
    if errors:raise ValueError('\n'.join(errors))
    with TemporaryDirectory(prefix='rdl-design-run-') as directory:
        root=Path(directory);path=materialize(design,root/'inputs');out=root/'output'
        case['aircraft_json']=str(path)
        if batch is None:answer=run_case(case,root,out)
        else:
            write_json(root/'case.json',case)
            answer=run_batch(dict(batch,case_json='case.json'),root,out)
        files={p.relative_to(out).as_posix():p.read_bytes() for p in out.rglob('*') if p.is_file()}
    files['design.rdl']=pack(design)
    notes=['# 本次实际方案',design['aircraft']['name'],'',
           '方案指纹：'+digest(design),'', '模板来源：'+design['template'],
           '参数来源：'+design['aircraft'].get('provenance','未填写'),'',
           '修改记录（原来源保留供参考，新值须另核对依据）：']
    notes.extend('- '+v for v in design['settings'].get('_edits',[]))
    files['design-summary.md']=('\n'.join(notes)+'\n').encode('utf-8')
    return answer,files
