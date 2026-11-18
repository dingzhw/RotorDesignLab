"""Recoverable aircraft deletion using the same optimistic lock as saving."""
from hashlib import sha256
from pathlib import Path
import re
from . import designs


def path_for(identifier):
    if not re.fullmatch('[a-f0-9]{32}', identifier):
        raise ValueError('无效整机方案编号。')
    return Path(designs.LIBRARY)/(identifier+'.rdl')


def trash(identifier, expected):
    source = path_for(identifier)
    lock = source.with_suffix('.lock')
    try:
        handle = lock.open('x')
    except FileExistsError as error:
        raise ValueError('方案正在保存，请稍后重试。') from error
    try:
        if sha256(source.read_bytes()).hexdigest() != expected:
            raise ValueError('方案已被修改，请重新打开后再移入回收区。')
        folder = source.parent/'trash'
        folder.mkdir(exist_ok=True)
        target = folder/source.name
        if target.exists():
            raise ValueError('回收区已有同编号方案，请先恢复副本。')
        source.rename(target)
    finally:
        handle.close()
        lock.unlink()


def deleted():
    return designs.saved_designs(Path(designs.LIBRARY)/'trash')


def restore(identifier):
    path_for(identifier)
    design, _ = designs.load_design(identifier, Path(designs.LIBRARY)/'trash')
    return designs.save_design(design)
