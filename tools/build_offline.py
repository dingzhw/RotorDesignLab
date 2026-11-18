"""Build a Windows x64 self-contained directory from the locked local runtime.

No pip/install/network calls. Only reviewed Git-index files enter the source payload.
The CPython installation is copied explicitly; a venv is never claimed relocatable.
"""
import argparse
from hashlib import sha256
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]


def canonical(name):
    return name.lower().replace('_','-').replace('.','-')


def payload_paths(root):
    names = subprocess.check_output(['git','ls-files','-z'],cwd=root).decode('utf-8').split('\0')
    folders = {'rotordesignlab','schemas','examples','validation','data','src','julia','tools','tests'}
    roots = {'app.py','launch.py','replay_results.py','offline_check.py','启动旋翼设计台.cmd',
             '复算导出结果.cmd','验证分发包.cmd','先读我.txt','README.md','requirements-win64-py314.txt'}
    paths = []
    for name in names:
        if not name:
            continue
        path = Path(name)
        if (name in roots or name=='.streamlit/config.toml' or path.parts[0] in folders or
                (path.parts[0]=='docs' and path.suffix in ('.md','.json','.csv'))):
            source = root/path
            if source.is_symlink() or not source.is_file():
                raise ValueError('分发清单存在链接或缺失文件：'+name)
            paths.append(path)
    return paths


def build(output):
    if os.name!='nt' or platform.machine().upper() not in ('AMD64','X86_64') or sys.version_info[:2]!=(3,14):
        raise ValueError('本构建器只接受已锁定的Windows x64 Python 3.14环境。')
    expected = {}
    for line in (ROOT/'requirements-win64-py314.txt').read_text().splitlines():
        if line.strip() and not line.startswith('#'):
            name,version = line.split('==')
            expected[canonical(name)] = version
    distributions = {canonical(d.metadata['Name']):d for d in metadata.distributions()}
    for name,version in expected.items():
        if name not in distributions or distributions[name].version != version:
            raise ValueError('锁定依赖不一致：'+name)
    if set(distributions)-set(expected)-{'pip'}:
        raise ValueError('构建环境含未锁定包，请使用项目环境。')
    output = Path(output).resolve()
    output.mkdir(parents=True,exist_ok=False)
    paths = payload_paths(ROOT)
    for path in paths:
        target = output/path
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(ROOT/path,target)
    runtime = output/'runtime'
    runtime.mkdir()
    base = Path(sys.base_prefix)
    for name in ('python.exe','pythonw.exe','python3.dll','python314.dll','vcruntime140.dll','vcruntime140_1.dll','LICENSE.txt'):
        shutil.copy2(base/name,runtime/name)
    def ignored(directory,names):
        return [name for name in names if name=='__pycache__' or name.endswith(('.pyc','.pyo')) or
                (Path(directory)==base/'Lib' and name=='site-packages')]
    for name in ('DLLs','Lib','tcl'):
        shutil.copytree(base/name,runtime/name,ignore=ignored)
    site = Path(sys.prefix)/'Lib/site-packages'
    if list(site.glob('*.pth')):
        raise ValueError('环境含.pth扩展路径，须先审核后显式支持，不能静默打包外部路径。')
    shutil.copytree(site,runtime/'Lib/site-packages',ignore=lambda d,n:[v for v in n if v=='__pycache__' or v.endswith('.pyc') or v=='pip' or v.startswith('pip-')])
    # Isolate against host PYTHONPATH, user-site and registry; .. is this payload.
    (runtime/'python314._pth').write_text('.\nLib\nDLLs\nLib/site-packages\n..\nimport site\n',encoding='utf-8')
    dependencies = []
    for name in sorted(expected):
        dist = distributions[name]
        licenses = [str(p) for p in dist.files or [] if any(term in str(p).lower() for term in ('license','copying','notice'))]
        dependencies.append(dict(name=dist.metadata['Name'],version=dist.version,
                                 license_expression=dist.metadata.get('License-Expression') or dist.metadata.get('License',''),
                                 license_files=licenses))
    (output/'DEPENDENCIES.json').write_text(json.dumps(dependencies,ensure_ascii=False,indent=2),encoding='utf-8')
    shutil.copy2(ROOT/'src/LICENSE',output/'LICENSE-J-GenHel.txt')
    manifest = dict(schema_version=1,kind='rotordesignlab_windows_directory',python=sys.version,
                    architecture=platform.machine(),source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip(),
                    source_worktree_changes=subprocess.check_output(['git','diff','HEAD','--name-only'],cwd=ROOT).decode('utf-8'),
                    note='内容以文件哈希为准；不含用户方案、运行历史、Git凭据或Julia运行时。',
                    files={p.relative_to(output).as_posix():sha256(p.read_bytes()).hexdigest()
                           for p in sorted(output.rglob('*')) if p.is_file()})
    (output/'distribution-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    archive = Path(str(output)+'.zip')
    if archive.exists():
        raise ValueError('目标ZIP已经存在。')
    with ZipFile(archive,'x',ZIP_DEFLATED,compresslevel=6) as package:
        for path in sorted(output.rglob('*')):
            if path.is_file():
                package.write(path,output.name+'/'+path.relative_to(output).as_posix())
    checksum = sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix('.zip.sha256').write_text(checksum+'  '+archive.name+'\n',encoding='utf-8')
    print(json.dumps(dict(directory=str(output),archive=str(archive),sha256=checksum,files=len(manifest['files'])),ensure_ascii=False),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',required=True,type=Path)
    build(parser.parse_args().out)
