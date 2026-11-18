"""AppTest of the explicit CSV interpolation choice and saved replay."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from rotordesignlab import module_workspace as store, designs, analysis_history

ROOT = Path(__file__).resolve().parents[1]


def get(items, label):
    return next(item for item in items if item.label == label)


def main():
    with TemporaryDirectory() as directory, \
            patch.object(store, 'LIBRARY', Path(directory)/'modules'), \
            patch.object(designs, 'LIBRARY', Path(directory)/'aircraft'), \
            patch.object(analysis_history, 'LIBRARY', Path(directory)/'results'):
        app = AppTest.from_file(str(ROOT/'app.py'), default_timeout=120).run()
        before = deepcopy(app.session_state['module-draft'])
        get(app.selectbox, '旋翼参数分组').select('几何与旋向').run()
        assert app.session_state['module-draft'] == before
        get(app.selectbox, '翼型攻角插值').set_value('pchip_alpha_v1').run()
        assert not app.exception
        get(app.number_input, '径向叶素数').set_value(24).run()
        get(app.number_input, '方位离散数').set_value(12).run()
        get(app.button, '运行旋翼计算').click().run()
        assert not app.exception
        first = deepcopy(app.session_state['module-result']['answer'])
        assert first['status'] == 'converged', first
        get(app.button, '保存旋翼算例').click().run()
        saved = deepcopy(app.session_state['module-draft'])
        assert store.load(app.session_state['module-id'])[0] == saved
        get(app.selectbox, '翼型攻角插值').set_value('linear_v1').run()
        get(app.checkbox, '允许替换当前旋翼草稿').check().run()
        get(app.button, '重新打开旋翼算例').click().run()
        assert app.session_state['module-draft'] == saved
        get(app.button, '运行旋翼计算').click().run()
        assert app.session_state['module-result']['answer']['summary'] == first['summary']
        assert not app.exception
        print('PCHIP网页改参、保存重开及同输入复算通过')


if __name__ == '__main__':
    main()
