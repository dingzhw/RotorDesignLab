"""Verify a delivered directory, including runtime files, without networking."""
from hashlib import sha256
import json
from pathlib import Path
import sys


def verify(root):
    manifest=json.loads((root/'distribution-manifest.json').read_text(encoding='utf-8'))
    errors=[]
    for name,expected in manifest['files'].items():
        path=(root/name).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            errors.append(name+'：缺失或路径无效')
        elif sha256(path.read_bytes()).hexdigest()!=expected:
            errors.append(name+'：内容不符')
    return errors


if __name__=='__main__':
    root=Path(__file__).resolve().parent
    try:
        errors=verify(root)
        if errors:
            print('\n'.join(errors))
            sys.exit(1)
        import launch
        launch.check_environment()
        print('分发文件哈希与运行依赖检查通过。用户private/与运行runs/不在原包校验范围内。')
    except (OSError,ValueError,RuntimeError) as error:
        print('检查失败：'+str(error))
        sys.exit(1)
