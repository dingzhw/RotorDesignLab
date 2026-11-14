"""Local server lifecycle, port collision, directory-specific reuse and GUI."""
from pathlib import Path
import os,socket,subprocess,time,tempfile,shutil
from unittest.mock import patch
import tkinter as tk
import launch

launch.check_environment()
find_spec=launch.importlib.util.find_spec
with patch.object(launch.importlib.util,'find_spec',side_effect=lambda name:None if name=='streamlit' else find_spec(name)):
    try:launch.check_environment()
    except RuntimeError as error:assert 'streamlit' in str(error) and '缺少' in str(error)
    else:raise AssertionError('Missing dependency must produce a clear diagnostic')
with tempfile.TemporaryDirectory(prefix='旋翼 启动检查 ') as temporary:
    base=Path(temporary);(base/'app.py').write_text("import streamlit as st\nst.title('启动检查')\n",encoding='utf-8')
    if os.name=='nt':
        shutil.copy2(launch.ROOT/'启动旋翼设计台.cmd',base/'start.cmd')
        result=subprocess.run(['cmd','/d','/c','start.cmd'],cwd=base,input='\n',capture_output=True,encoding='utf-8')
        assert result.returncode==1 and '未找到项目运行环境' in result.stdout
    print('Missing environment and dependency diagnostics passed.',flush=True)
    block=socket.socket()
    try:block.bind(('127.0.0.1',8501));block.listen();occupied=True
    except OSError:occupied=False
    first=launch.InstanceLock(base);second=launch.InstanceLock(base)
    assert first.owned and not second.owned
    server=launch.LocalServer(base)
    try:
        url=server.start();assert ':8501/' not in url
        deadline=time.monotonic()+30
        while not launch.healthy(url) and time.monotonic()<deadline:
            assert server.process.poll() is None
            time.sleep(.1)
        assert launch.healthy(url)
        assert launch.existing_url(base)==url
        assert launch.existing_url(base/'elsewhere') is None
    finally:server.stop();first.close();second.close();block.close()
    assert server.process.poll() is not None and not (base/'runs/launcher/state.json').exists()
    assert not launch.healthy(url)
    print('Server: occupied port, Chinese/space path, reuse and owned-process shutdown passed.',flush=True)

# Exercise the real native control window and automatic browser-open callback.
real_tk=tk.Tk;windows=[];captured=[];server_class=launch.LocalServer
def create_window():
    w=real_tk();windows.append(w)
    w.after(20000,lambda:w.event_generate('<<TestTimeout>>'))
    w.bind('<<TestTimeout>>',lambda e:w.destroy())
    return w
def open_browser(url):
    captured.append(url)
    def stop():
        frame=windows[0].winfo_children()[-1]
        button=next(child for child in frame.winfo_children() if child.cget('text')=='停止服务并退出')
        button.invoke()
    windows[0].after(100,stop)
    return True
with patch.object(tk,'Tk',side_effect=create_window),patch.object(launch.webbrowser,'open',side_effect=open_browser):
    launch.launch_window()
assert len(captured)==1 and captured[0].startswith('http://127.0.0.1:')
assert not launch.healthy(captured[0])
print('Native window: readiness, automatic browser callback and stop button passed.',flush=True)
