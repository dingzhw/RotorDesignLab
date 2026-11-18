"""Run inside an extracted payload; guard external connections in the test process."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import platform
import runpy
import socket
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def main(destination):
    import numpy
    import scipy
    import pandas
    import matplotlib
    import streamlit
    import tkinter
    from offline_check import verify
    from rotordesignlab import __version__

    assert Path(sys.prefix).resolve() == ROOT/'runtime', sys.prefix
    assert not verify(ROOT)
    command = subprocess.run(['cmd', '/d', '/c', '验证分发包.cmd'], cwd=ROOT,
                             input='\n', capture_output=True, encoding='utf-8')
    assert command.returncode == 0, command.stdout+command.stderr
    assert '分发文件哈希与运行依赖检查通过' in command.stdout
    packages = {}
    for module in (numpy, scipy, pandas, matplotlib, streamlit, tkinter):
        path = Path(module.__file__).resolve()
        assert path.is_relative_to(ROOT/'runtime'), path
        packages[module.__name__] = str(path.relative_to(ROOT))
    assert tkinter.Tcl().eval('info patchlevel')
    connect = socket.socket.connect
    connect_ex = socket.socket.connect_ex
    blocked = []

    def guard(method, sock, address):
        if isinstance(address, tuple) and address[0] not in ('127.0.0.1', '::1', 'localhost'):
            blocked.append(str(address))
            raise OSError('离线检查禁止非本机网络连接')
        return method(sock, address)

    started = time.perf_counter()
    sys.path.insert(0, str(ROOT/'tests'))
    with patch.object(socket.socket, 'connect', lambda sock, address: guard(connect, sock, address)), \
            patch.object(socket.socket, 'connect_ex', lambda sock, address: guard(connect_ex, sock, address)):
        suite = unittest.defaultTestLoader.discover(str(ROOT/'tests'), pattern='test_offline_delivery.py')
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        assert result.wasSuccessful()
        runpy.run_path(str(ROOT/'tests/check_c4c_ui.py'), run_name='__main__')
        runpy.run_path(str(ROOT/'tests/check_offline_ui.py'), run_name='__main__')
        runpy.run_path(str(ROOT/'tests/check_launcher.py'), run_name='__main__')
    record = dict(version=__version__, platform=platform.platform(), python=sys.version,
                  isolated_import_paths=packages, manifest_sha256=sha256((ROOT/'distribution-manifest.json').read_bytes()).hexdigest(),
                  focused_tests=result.testsRun, webpage_exports_and_replay='passed', native_windows='passed',
                  unified_scheme_operations='passed',
                  verify_cmd_exit_code=command.returncode,
                  elapsed_s=time.perf_counter()-started, external_connection_attempts=blocked,
                  network_scope='Test process blocks external socket connects; server subprocess uses localhost config. OS network unchanged.',
                  human_acceptance='pending', browser_callback='captured automatically; real colleague browser acceptance pending')
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    print('离线目录检查通过：'+str(destination), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    main(parser.parse_args().out)
