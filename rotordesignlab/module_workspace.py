"""Independent rotor workspace persistence and portable execution."""
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import json
import math
import os
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from uuid import uuid4
from zipfile import ZipFile, ZIP_DEFLATED, BadZipFile

from . import rotor_module
from .cases import read_case, write_json, run_case

ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / 'private' / 'rotor-modules'
TEMPLATES = {'合成三桨叶旋翼（工程估计）': 'synthetic', 'UH-60 公开基准旋翼': 'uh60-public'}


def template(name):
    root = ROOT / 'examples/rotor-modules' / TEMPLATES[name]
    module, assets = rotor_module.load(root / 'module.json')
    module['name'] = name
    return dict(module=module, assets=assets, case=read_case(root / 'case.json'), sweep=None)


def digest(draft):
    content = {k: v for k, v in draft.items() if k != 'assets'}
    content['assets'] = {k: sha256(v).hexdigest() for k, v in draft['assets'].items()}
    return sha256(json.dumps(content, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def pack(draft):
    """A case package contains a pure component package plus its test conditions."""
    validate_case(draft['case'])
    if draft.get('sweep') is not None:
        from .module_batch import validate_spec
        validate_spec(dict(draft['sweep'], case_json='case.json'))
    component = rotor_module.pack(draft['module'], draft['assets'])
    manifest = dict(schema_version=1, kind='rotor_workspace', case=draft['case'],
                    sweep=draft.get('sweep'), migration=draft.get('migration'), module_sha256=sha256(component).hexdigest())
    if 'trial' in draft:
        from .rotor_trial import validate
        validate(draft['trial'], draft['case'])
        manifest.update(schema_version=2, trial=draft['trial'])
    stream = BytesIO()
    with ZipFile(stream, 'w', ZIP_DEFLATED) as archive:
        archive.writestr('module.rdlr', component)
        archive.writestr('workspace.json', json.dumps(manifest, ensure_ascii=False, allow_nan=False))
    return stream.getvalue()


def unpack(data):
    try:
        with ZipFile(BytesIO(data)) as archive:
            entries = archive.infolist()
            if (len(data) > 34*1024**2 or len(entries) != 2 or
                    set(archive.namelist()) != {'module.rdlr', 'workspace.json'} or
                    sum(e.file_size for e in entries) > 34*1024**2):
                raise ValueError('旋翼算例包文件清单或大小无效。')
            manifest = json.loads(archive.read('workspace.json'))
            component = archive.read('module.rdlr')
        if (set(manifest) != ({'schema_version', 'kind', 'case', 'sweep', 'migration', 'module_sha256'} |
                              ({'trial'} if manifest.get('schema_version') == 2 else set())) or
                manifest['schema_version'] not in (1, 2) or manifest['kind'] != 'rotor_workspace' or
                manifest['module_sha256'] != sha256(component).hexdigest()):
            raise ValueError('旋翼算例包版本或内容哈希无效。')
        module, assets = rotor_module.unpack(component)
        case = manifest['case']
        validate_case(case)
        if manifest['sweep'] is not None:
            from .module_batch import validate_spec
            validate_spec(dict(manifest['sweep'], case_json='case.json'))
        draft = dict(module=module, assets=assets, case=case, sweep=manifest['sweep'])
        if manifest['migration'] is not None:
            draft['migration'] = manifest['migration']
        if manifest['schema_version'] == 2:
            from .rotor_trial import validate
            validate(manifest['trial'], case)
            draft['trial'] = manifest['trial']
        digest(draft)
        return draft
    except (BadZipFile, KeyError, TypeError, UnicodeError, RuntimeError) as error:
        raise ValueError('无法读取旋翼算例：' + str(error)) from error


def validate_case(case):
    """Check editable structure, leaving operating-domain failures to the solver."""
    if not isinstance(case, dict) or case.get('model') != 'rotor_module' or case.get('schema_version') != 4:
        raise ValueError('算例必须使用独立旋翼工况。')
    allowed = {'schema_version', 'model', 'module_file', 'method', 'flapping_model', 'rpm', 'collective_deg',
               'radial_stations', 'azimuth_stations', 'flow_rotor_m_s', 'gravity_rotor_m_s2',
               'cyclic_cos_deg', 'cyclic_sin_deg', 'environment', 'altitude_m', 'target'}
    if set(case) - allowed:
        raise ValueError('独立旋翼工况含未识别字段。')
    for name in ('rpm', 'collective_deg', 'radial_stations'):
        if name not in case or type(case[name]) not in (int, float) or not math.isfinite(case[name]):
            raise ValueError('工况缺少有限数值：' + name)
    for name in ('radial_stations', 'azimuth_stations'):
        if name in case and type(case[name]) is not int:
            raise ValueError('离散数必须为整数：' + name)
    for name in ('cyclic_cos_deg', 'cyclic_sin_deg', 'altitude_m'):
        if name in case and (type(case[name]) not in (int, float) or not math.isfinite(case[name])):
            raise ValueError('工况需要有限数值：' + name)
    for name in ('flow_rotor_m_s', 'gravity_rotor_m_s2'):
        values = case.get(name)
        if not isinstance(values, list) or len(values) != 3 or any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
            raise ValueError('工况需要三分量有限向量：' + name)
    if case.get('method', 'spatial') not in ('spatial', 'axial') or case.get('flapping_model', 'module') not in ('module', 'fixed'):
        raise ValueError('工况方法无效。')
    from .environment import from_case
    from_case(case)
    if 'target' in case:
        target = case['target']
        if (not isinstance(target, dict) or target.get('solve_for') not in ('rpm', 'collective_deg') or
                type(target.get('thrust_n')) not in (int, float) or not math.isfinite(target['thrust_n'])):
            raise ValueError('反求工况需要待求变量和有限目标拉力。')
        if set(target) - {'thrust_n', 'solve_for', 'bounds'}:
            raise ValueError('反求工况含未识别字段。')
        if 'bounds' in target:
            bounds = target['bounds']
            if not isinstance(bounds, list) or len(bounds) != 2 or any(type(v) not in (int, float) or not math.isfinite(v) for v in bounds):
                raise ValueError('反求搜索边界必须为两个有限数。')


def checked_id(identifier):
    if not re.fullmatch('[a-f0-9]{32}', identifier):
        raise ValueError('无效模块库编号。')
    return identifier


def load(identifier, library=None, revision=None, deleted=False):
    root = Path(library or LIBRARY)
    identifier = checked_id(identifier)
    if revision is not None:
        if not re.fullmatch('[a-f0-9]{64}', revision):
            raise ValueError('无效历史版本编号。')
        path = root / 'history' / f'{identifier}-{revision}.rdlc'
    else:
        path = (root / 'trash' if deleted else root) / f'{identifier}.rdlc'
    data = path.read_bytes()
    return unpack(data), sha256(data).hexdigest()


def saved(library=None, deleted=False):
    root = Path(library or LIBRARY)
    if deleted:
        root = root / 'trash'
    rows = []
    for path in sorted(root.glob('*.rdlc'), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            draft = unpack(path.read_bytes())
            rows.append((path.stem, draft['module']['name']))
        except (ValueError, OSError):
            continue
    return rows


def revisions(identifier, library=None):
    root = Path(library or LIBRARY) / 'history'
    return [p.stem.split('-')[-1] for p in sorted(root.glob(checked_id(identifier) + '-*.rdlc'),
                                               key=lambda p: p.stat().st_mtime, reverse=True)]


def save(draft, identifier=None, expected=None, library=None):
    data = pack(draft)
    root = Path(library or LIBRARY)
    root.mkdir(parents=True, exist_ok=True)
    identifier = checked_id(identifier or uuid4().hex)
    path = root / (identifier + '.rdlc')
    lock = root / (identifier + '.lock')
    temporary = root / (uuid4().hex + '.tmp')
    try:
        handle = lock.open('x')
    except FileExistsError as error:
        raise ValueError('该模块正在保存，请稍后再试。') from error
    try:
        if path.exists():
            old = path.read_bytes()
            oldhash = sha256(old).hexdigest()
            if oldhash != expected:
                raise ValueError('模块已被另一窗口修改，请另存新模块或重新打开。草稿已保留。')
            history = root / 'history'
            history.mkdir(exist_ok=True)
            backup = history / f'{identifier}-{oldhash}.rdlc'
            if not backup.exists():
                backup.write_bytes(old)
        elif expected is not None:
            raise ValueError('原模块已移出库，请另存新模块。')
        with temporary.open('xb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        handle.close()
        lock.unlink()
        if temporary.exists():
            temporary.unlink()
    return identifier, sha256(data).hexdigest()


def trash(identifier, expected, library=None):
    root = Path(library or LIBRARY)
    identifier = checked_id(identifier)
    lock = root / (identifier + '.lock')
    handle = lock.open('x')
    try:
        source = root / (identifier + '.rdlc')
        if sha256(source.read_bytes()).hexdigest() != expected:
            raise ValueError('模块已更改，请重新打开后再移入回收区。')
        target = root / 'trash'
        target.mkdir(exist_ok=True)
        if (target / source.name).exists():
            raise ValueError('回收区已有同编号模块，请先恢复。')
        source.rename(target / source.name)
    finally:
        handle.close()
        lock.unlink()


def extract(data, rotor_id, old_case=None):
    with TemporaryDirectory(prefix='rdl-module-extract-') as directory:
        root = Path(directory)
        (root / 'source.rdl').write_bytes(data)
        output = root / 'extracted'
        rotor_module.extract(root / 'source.rdl', rotor_id, output)
        module, assets = rotor_module.load(output / 'module.json')
        case = read_case(output / 'case.json')
        if old_case is not None:
            case = rotor_module.convert_case(old_case, read_case(output / 'migration.json'), case)
        return dict(module=module, assets=assets, case=case, sweep=None, migration=read_case(output/'migration.json'))


def execute(draft):
    submitted = deepcopy(draft)
    with TemporaryDirectory(prefix='rdl-module-run-') as directory:
        root = Path(directory)
        rotor_module.save(submitted['module'], submitted['assets'], root / 'module.rdlr')
        case = dict(submitted['case'], module_file='module.rdlr')
        write_json(root / 'case.json', case)
        if submitted.get('sweep'):
            from .module_batch import run_batch
            spec = dict(submitted['sweep'], case_json='case.json')
            answer = run_batch(spec, root, root / 'output')
        else:
            answer = run_case(case, root, root / 'output')
        files = {p.relative_to(root/'output').as_posix(): p.read_bytes()
                 for p in (root/'output').rglob('*') if p.is_file()}
    files['workspace.rdlc'] = pack(submitted)
    if submitted.get('migration'):
        files['migration.json'] = json.dumps(submitted['migration'], ensure_ascii=False, indent=2).encode()
    return dict(answer=answer, files=files, draft=submitted, fingerprint=digest(submitted))


def archive(files):
    stream = BytesIO()
    with ZipFile(stream, 'w', ZIP_DEFLATED) as output:
        for name, data in files.items():
            output.writestr(name, data)
    return stream.getvalue()
