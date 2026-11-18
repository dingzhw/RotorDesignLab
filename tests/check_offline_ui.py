"""C3: use the delivered replay entry for real C2 webpage exports and a Tk window."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import tkinter as tk
import time

import check_c2_ui
import replay_results
from rotordesignlab import module_workspace


def replay_export(record):
    with TemporaryDirectory(prefix='离线 结果复算 ') as directory:
        root = Path(directory)
        archive = root/'网页导出.zip'
        archive.write_bytes(module_workspace.archive(record['files']))
        checked = replay_results.replay(archive, root/'new-result')
        assert checked['status'] == record['answer']['status'], checked
        assert checked['summary_exactly_equal'], checked
        print('网页实际导出ZIP复算通过：'+record['answer']['model'], flush=True)


def native_replay():
    draft = module_workspace.template(next(iter(module_workspace.TEMPLATES)))
    draft['case']['radial_stations'] = 24
    draft['case']['azimuth_stations'] = 12
    result = module_workspace.execute(draft)
    real_tk = tk.Tk
    completed = []
    windows = []
    with TemporaryDirectory(prefix='复算窗口 ') as directory:
        root = Path(directory)
        archive = root/'结果.zip'
        archive.write_bytes(module_workspace.archive(result['files']))
        deadline = time.monotonic()+120

        def create_window():
            window = real_tk()
            windows.append(window)

            def interact():
                buttons = [child for child in window.winfo_children() if child.winfo_class() == 'TButton']
                buttons[0].invoke()
                buttons[1].invoke()
                poll()

            def poll():
                labels = [child for child in window.winfo_children() if child.winfo_class() == 'TLabel']
                message = str(labels[0].cget('text'))
                if '复算结束' in message or '复算失败' in message or time.monotonic() > deadline:
                    completed.append(message)
                    window.destroy()
                else:
                    window.after(100, poll)

            window.after(100, interact)
            return window

        with patch.object(replay_results, 'ROOT', root), \
                patch.object(tk, 'Tk', side_effect=create_window), \
                patch('tkinter.filedialog.askopenfilename', return_value=str(archive)):
            replay_results.window()
        assert not windows[0].tk.call('after', 'info'), '窗口退出后遗留定时回调'
        assert completed and '复算结束：收敛' in completed[0], completed
        assert '逐值一致：是' in completed[0], completed
        assert len(list((root/'runs/replay').glob('*/replay-check.json'))) == 1
        print('原生复算窗口：选择ZIP、执行、显示中文结果及创建新结果通过', flush=True)


if __name__ == '__main__':
    check_c2_ui.replay = replay_export
    check_c2_ui.main()
    native_replay()
