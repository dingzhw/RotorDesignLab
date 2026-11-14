"""Local Windows launcher; no installation, global settings or remote access."""
import argparse
import ctypes
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.request import build_opener,ProxyHandler
import webbrowser

ROOT=Path(__file__).resolve().parent


def check_environment():
    missing=[name for name in ('streamlit','numpy','scipy','matplotlib','pandas','altair','jsonschema','tkinter')
             if importlib.util.find_spec(name) is None]
    if missing:raise RuntimeError('当前环境缺少：'+ '、'.join(missing)+'。请联系维护人员按 README 准备项目环境。')
    if not (ROOT/'app.py').is_file():raise RuntimeError('未找到 app.py，请保留完整程序目录。')


def healthy(url):
    try:
        # The local service must work even when the machine has HTTP proxies.
        with build_opener(ProxyHandler({})).open(url+'_stcore/health',timeout=.4) as r:
            return r.status==200 and r.read(32).strip()==b'ok'
    except (OSError,ValueError):return False


class LocalServer:
    def __init__(self,root=ROOT):
        self.root=Path(root).resolve();self.process=None;self.log=None
        self.directory=self.root/'runs/launcher';self.directory.mkdir(parents=True,exist_ok=True)
        self.path='rdl-'+hashlib.sha256(str(self.root).casefold().encode()).hexdigest()[:12]
        self.url=None

    def start(self):
        for port in range(8501,8601):
            with socket.socket() as probe:
                try:probe.bind(('127.0.0.1',port))
                except OSError:continue
            break
        else:raise RuntimeError('8501–8600 端口均被占用，请关闭闲置程序后重试。')
        self.url=f'http://127.0.0.1:{port}/{self.path}/'
        self.log=(self.directory/'server.log').open('w',encoding='utf-8')
        args=[sys.executable,'-m','streamlit','run',str(self.root/'app.py'),
              '--server.address=127.0.0.1',f'--server.port={port}',f'--server.baseUrlPath={self.path}',
              '--server.headless=true','--browser.gatherUsageStats=false']
        env=dict(os.environ,PYTHONUTF8='1')
        try:
            self.process=subprocess.Popen(args,cwd=self.root,stdout=self.log,stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0,env=env)
        except OSError:
            self.log.close();self.log=None;raise
        (self.directory/'state.json').write_text(json.dumps(dict(url=self.url,pid=self.process.pid,root=str(self.root))),encoding='utf-8')
        return self.url

    def stop(self):
        # Only our Popen object is terminated; never kill by port or stale PID.
        if self.process is not None:
            if self.process.poll() is None:
                self.process.terminate()
                try:self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=5)
            record=self.directory/'state.json'
            if record.exists():
                try:
                    if json.loads(record.read_text(encoding='utf-8')).get('pid')==self.process.pid:record.unlink()
                except (OSError,ValueError):pass
        if self.log is not None:self.log.close();self.log=None


class InstanceLock:
    """Per-directory named mutex; Windows releases it if the launcher exits."""
    def __init__(self,root=ROOT):
        self.handle=None;self.owned=True
        if os.name=='nt':
            kernel=ctypes.WinDLL('kernel32',use_last_error=True)
            kernel.CreateMutexW.argtypes=[ctypes.c_void_p,ctypes.c_bool,ctypes.c_wchar_p]
            kernel.CreateMutexW.restype=ctypes.c_void_p
            kernel.CloseHandle.argtypes=[ctypes.c_void_p]
            name='Local\\RotorDesignLab-'+hashlib.sha256(str(Path(root).resolve()).casefold().encode()).hexdigest()
            self.handle=kernel.CreateMutexW(None,False,name)
            if not self.handle:raise OSError(ctypes.get_last_error(),'启动器互斥锁创建失败')
            self.owned=ctypes.get_last_error()!=183;self.kernel=kernel

    def close(self):
        if self.handle:self.kernel.CloseHandle(self.handle);self.handle=None


def existing_url(root=ROOT):
    try:
        record=json.loads((Path(root)/'runs/launcher/state.json').read_text(encoding='utf-8'))
        expected='rdl-'+hashlib.sha256(str(Path(root).resolve()).casefold().encode()).hexdigest()[:12]
        from urllib.parse import urlparse
        url=record['url'];parsed=urlparse(url)
        if (record.get('root')==str(Path(root).resolve()) and parsed.scheme=='http' and
            parsed.hostname=='127.0.0.1' and parsed.path==f'/{expected}/' and healthy(url)):return url
    except (OSError,ValueError,KeyError):pass
    return None


def launch_window():
    import tkinter as tk
    from tkinter import ttk,messagebox
    from rotordesignlab import __version__
    window=tk.Tk();window.title('RotorDesignLab｜旋翼设计台');window.geometry('560x260');window.resizable(False,False)
    status=tk.StringVar(value='正在检查运行环境…');server=None;lock=None;opened=False
    ttk.Label(window,text='旋翼设计台',font=('Microsoft YaHei',18)).pack(pady=(18,4))
    ttk.Label(window,text=f'版本 {__version__} · 本机计算服务').pack()
    ttk.Label(window,textvariable=status,wraplength=520,justify='center').pack(pady=16)
    address=ttk.Entry(window,width=70);address.pack(padx=15)
    buttons=ttk.Frame(window);buttons.pack(pady=15)
    def open_page():
        if server and healthy(server.url):
            if not webbrowser.open(server.url):status.set('浏览器未自动打开，可复制上方地址到浏览器。')
    opener=ttk.Button(buttons,text='打开工作台',command=open_page,state='disabled');opener.pack(side='left',padx=8)
    def close():
        if server:server.stop()
        if lock:lock.close()
        window.destroy()
    ttk.Button(buttons,text='停止服务并退出',command=close).pack(side='left',padx=8)
    window.protocol('WM_DELETE_WINDOW',close)
    started=0.
    def poll():
        nonlocal opened
        if server.process.poll() is not None:
            status.set('服务启动失败。诊断日志：'+str(server.directory/'server.log'));server.stop();return
        if healthy(server.url):
            status.set('工作台已就绪。可最小化本窗口；关闭本窗口将停止服务。');opener.configure(state='normal')
            if not opened:opened=True;open_page()
            return
        if time.monotonic()-started>60:
            status.set('启动超过60秒，请查看 runs/launcher/server.log 后重试。');server.stop();return
        window.after(300,poll)
    def start():
        nonlocal server,lock,started
        try:
            check_environment();lock=InstanceLock()
            if not lock.owned:
                url=existing_url()
                if url:webbrowser.open(url)
                else:messagebox.showinfo('旋翼设计台','已有启动窗口，请等待其启动完成，或在该窗口查看提示。',parent=window)
                close();return
            server=LocalServer();server.start();started=time.monotonic()
            address.insert(0,server.url);address.configure(state='readonly')
            status.set('正在启动本机工作台，准备好后会自动打开浏览器…');window.after(300,poll)
        except Exception as error:
            if server:server.stop()
            status.set(str(error));messagebox.showerror('启动失败',str(error),parent=window)
    window.after(100,start);window.mainloop()


def main():
    parser=argparse.ArgumentParser(description='旋翼设计台启动器');parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    if args.check:check_environment();print('环境检查通过');return
    launch_window()


if __name__=='__main__':
    try:main()
    except Exception as error:
        if os.name=='nt':ctypes.windll.user32.MessageBoxW(None,str(error),'旋翼设计台启动失败',16)
        else:print(str(error),file=sys.stderr)
        sys.exit(1)
