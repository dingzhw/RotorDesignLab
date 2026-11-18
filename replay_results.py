"""GUI replay of an exported Python result ZIP; always writes a new run."""
from datetime import datetime
import json
from pathlib import Path, PurePosixPath
from queue import Queue, Empty
from threading import Thread
from uuid import uuid4
from zipfile import ZipFile, BadZipFile

ROOT=Path(__file__).resolve().parent


def replay(archive_path, output):
    from rotordesignlab.cases import read_case, run_case, write_json
    from rotordesignlab.batch import run_batch
    from rotordesignlab import __version__
    output=Path(output).resolve()
    output.mkdir(parents=True,exist_ok=False)
    inputs=output/'input'
    inputs.mkdir()
    with ZipFile(archive_path) as archive:
        entries=archive.infolist()
        names=[item.filename.casefold().rstrip('/') for item in entries]
        if len(entries)>10000 or len(set(names))!=len(names) or sum(item.file_size for item in entries)>512*1024**2:
            raise ValueError('结果包过大或含重复文件。')
        for item in entries:
            name=item.filename
            if ('\\' in name or ':' in name or PurePosixPath(name).is_absolute() or
                    any(part in ('.','..') or part.endswith((' ','.')) for part in name.split('/') if part) or
                    (item.external_attr>>16)&0o170000 == 0o120000):
                raise ValueError('结果包含不安全路径或链接。')
            target=(inputs/name).resolve()
            if not target.is_relative_to(inputs):
                raise ValueError('结果包路径越界。')
            if item.is_dir():
                target.mkdir(parents=True,exist_ok=True)
            else:
                target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes(archive.read(item))
    def check_refs(value, base):
        if isinstance(value,dict):
            for key,item in value.items():
                if key in ('case_json','aircraft_json','module_file','geometry_csv','polar_csv','polar_json') and isinstance(item,str):
                    if not (base/item).resolve().is_relative_to(inputs):
                        raise ValueError('导出输入引用了结果包外文件：'+key)
                check_refs(item,base)
        elif isinstance(value,list):
            for item in value:
                check_refs(item,base)
    for path in inputs.rglob('*.json'):
        value=read_case(path)
        check_refs(value,path.parent)
        if isinstance(value,dict) and value.get('model')=='uh60':
            raise ValueError('原Julia基准需单独配置Julia环境，本入口用于Python结果包。')
    if (inputs/'batch.json').exists():
        answer=run_batch(read_case(inputs/'batch.json'),inputs,output/'calculation')
    elif (inputs/'case.json').exists():
        case=read_case(inputs/'case.json')
        answer=run_case(case,inputs,output/'calculation')
    else:
        raise ValueError('未找到工况；请选择“下载结果与可搬移复算包”导出的ZIP，不是方案包。')
    original=read_case(inputs/'result.json') if (inputs/'result.json').exists() else {}
    record=dict(current_version=__version__,original_version=original.get('solver_version'),
                status=answer['status'],original_status=original.get('status'),
                summary_exactly_equal=bool(original.get('summary')) and original.get('summary')==answer.get('summary'),
                note='复算创建新目录；summary相同只说明所列指标一致，不替代物理精度验收。')
    write_json(output/'replay-check.json',record)
    return record


def window():
    import tkinter as tk
    from tkinter import ttk,filedialog,messagebox
    root=tk.Tk()
    root.title('旋翼设计台｜导出结果复算')
    root.geometry('620x240')
    selected=tk.StringVar()
    status=tk.StringVar(value='选择从工作台下载的结果ZIP；复算会创建新结果目录。')
    messages=Queue()
    running=False
    poll_id=None
    def choose():
        value=filedialog.askopenfilename(filetypes=[('结果压缩包','*.zip')],parent=root)
        if value:
            selected.set(value)
    def start():
        nonlocal running
        if not selected.get():
            messagebox.showinfo('选择结果包','请先选择结果ZIP。',parent=root)
            return
        destination=ROOT/'runs/replay'/(datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid4().hex[:8])
        path=selected.get()
        running=True
        button.configure(state='disabled')
        status.set('正在复算，请等待；原结果包保持不变。')
        def work():
            try:
                result=replay(path,destination)
                status_name={'converged':'收敛','failed':'失败','partial':'部分完成'}.get(result['status'],result['status'])
                equal='是' if result['summary_exactly_equal'] else '否，请查看原结果和新结果'
                messages.put('复算结束：'+status_name+'；汇总是否逐值一致：'+equal+'\n结果：'+str(destination))
            except Exception as error:
                # GUI boundary: keep the window usable and retain unexpected diagnostics.
                import traceback
                try:
                    destination.mkdir(parents=True,exist_ok=True)
                    (destination/'error.txt').write_text(traceback.format_exc(),encoding='utf-8')
                except OSError:
                    messages.put('复算失败：'+str(error)+'\n无法写入诊断，请将程序完整解压到可写目录。')
                    return
                messages.put('复算失败：'+str(error)+'\n诊断目录：'+str(destination))
        Thread(target=work,daemon=True).start()
    def poll():
        nonlocal running,poll_id
        try:
            status.set(messages.get_nowait())
            running=False
            button.configure(state='normal')
        except Empty:
            pass
        poll_id=root.after(150,poll)
    def cleanup(event):
        if event.widget is root and poll_id is not None:
            root.after_cancel(poll_id)
    def close():
        if running:
            messagebox.showinfo('正在复算','请等待本次复算结束后关闭。',parent=root)
        else:
            root.destroy()
    ttk.Button(root,text='选择导出的结果ZIP',command=choose).pack(pady=10)
    ttk.Entry(root,textvariable=selected,width=85).pack()
    button=ttk.Button(root,text='开始复算',command=start)
    button.pack(pady=10)
    ttk.Label(root,textvariable=status,wraplength=590).pack(padx=10)
    root.protocol('WM_DELETE_WINDOW',close)
    root.bind('<Destroy>',cleanup)
    poll_id=root.after(150,poll)
    root.mainloop()


if __name__=='__main__':
    window()
