"""Chinese independent rotor workbench. Never creates an aircraft document."""
from copy import deepcopy
from decimal import Decimal
from io import BytesIO
import json

import numpy as np
import pandas as pd
import streamlit as st

from . import module_workspace as store, rotor_module
from .parameter_fields import label, help_text


def current():
    return st.session_state['module-draft']


def replace(draft, identifier=None, version=None):
    st.session_state['module-draft'] = deepcopy(draft)
    st.session_state['module-source-snapshot'] = deepcopy(draft['module'])
    st.session_state['module-id'] = identifier
    st.session_state['module-version'] = version
    st.session_state['module-saved-digest'] = store.digest(draft)
    st.session_state['module-epoch'] = st.session_state.get('module-epoch', 0) + 1
    st.session_state.pop('module-result', None)


def key(name):
    return f'm:{st.session_state["module-epoch"]}:{name}'


def fingerprint():
    try:
        return store.digest(current())
    except (ValueError, TypeError):
        return None


def finite_rows(frame):
    """Preserve blank cells as missing values, never coerce them to zero."""
    return frame.astype(object).where(pd.notna(frame), None).to_numpy().tolist()


def field(obj, name, title=None, default=0., options=None, help=None, prefix='', **kwargs):
    """Callbacks write the draft before rerun; widget cleanup cannot erase it."""
    widget = key(prefix + '/' + name)
    value = obj.get(name, default)
    def changed():
        obj[name] = st.session_state[widget]
        if name == 'solve_for' and 'bounds' in obj:
            obj['bounds'] = list(current()['module']['rotor']['limits'][obj[name]])
    title = title or label(name)
    help = help or help_text(name) or '按当前旋翼的实际资料填写；单位见字段名称，资料备注可选，修改记录随方案保存。'
    if options is not None:
        return st.selectbox(title, options, index=list(options).index(value), key=widget,
                            on_change=changed, help=help, **kwargs)
    if isinstance(value, str):
        return st.text_input(title, value, key=widget, on_change=changed, help=help, **kwargs)
    return st.number_input(title, value=float(value), key=widget, on_change=changed, help=help, **kwargs)


def optional(obj, name, title, initial, prefix, help):
    enabled = st.checkbox('填写' + title, value=name in obj, key=key(prefix + '/' + name + '/known'),
                          help='未知请保持未填写；填写后随模块保存。' + help)
    if enabled:
        if name not in obj:
            obj[name] = initial
        field(obj, name, title, prefix=prefix, help=help)
    else:
        obj.pop(name, None)


def vector(obj, name, title, default, prefix, help):
    values = list(obj.get(name, default))
    for i, col in enumerate(st.columns(3)):
        with col:
            widget = key(prefix + '/' + name + str(i))
            def changed(i=i, widget=widget):
                obj.setdefault(name, list(default))[i] = st.session_state[widget]
            st.number_input(title + ' ' + 'xyz'[i], value=float(values[i]), key=widget,
                            on_change=changed, help=help)


def table(frame, name, apply, dynamic=False, disabled=()):
    widget = key(name)
    base_key = widget + ':base'
    if base_key not in st.session_state:
        st.session_state[base_key] = frame.to_dict('records')
    def changed():
        from .design_ui import table_delta
        rows = table_delta(st.session_state[base_key], st.session_state[widget])
        apply(pd.DataFrame(rows, columns=frame.columns))
    st.data_editor(pd.DataFrame(st.session_state[base_key], columns=frame.columns), key=widget,
                   num_rows='dynamic' if dynamic else 'fixed', hide_index=True, disabled=list(disabled),
                   column_config={c: st.column_config.NumberColumn(label(c), help=help_text(c) or c,
                                                                   format='%.9g') for c in frame.columns},
                   on_change=changed)


def table_assets(group):
    draft = current()
    assets = draft['assets']
    for name, title in [('geometry.csv', '桨叶几何表'), ('polar.csv', '翼型极曲线表')]:
        if (name == 'geometry.csv') != (group == '桨叶几何形状'):
            continue
        if name not in assets:
            continue
        st.markdown('**' + title + '**')
        frame = pd.read_csv(BytesIO(assets[name]))
        def apply(frame, name=name):
            assets[name] = frame.to_csv(index=False).encode('utf-8')
            note = '；用户修改（待核）：' + name
            if note not in draft['module']['provenance']:
                draft['module']['provenance'] += note
        def replace_table(frame, source, name=name):
            if name == 'geometry.csv' and frame.iloc[0, 0] > current()['module']['rotor']['pitch_reference_r_over_R']:
                raise ValueError('有效桨根超出总距参考站；请先核对模块几何定义。')
            candidate = deepcopy(current())
            candidate['assets'][name] = frame.to_csv(index=False).encode('utf-8')
            candidate['module']['provenance'] += '；'+name+'：'+source
            rotor_module.pack(candidate['module'], candidate['assets'])
            current().update(candidate)
            st.session_state['module-epoch'] += 1
            st.session_state[key('detail-group')] = group
            st.rerun()
        from .engineering_input_ui import geometry_generator, table_exchange
        if name == 'geometry.csv':
            geometry_generator(frame, draft['module']['rotor']['pitch_reference_r_over_R'],
                               lambda v: key('generator/'+v), replace_table, optional_source=True)
        table(frame, name, apply, dynamic=True)
        from .previews import csv_figure, show
        try:
            show(csv_figure(assets[name].decode('utf-8-sig'), name == 'geometry.csv'))
        except (ValueError, TypeError, KeyError) as error:
            st.warning('表格尚不完整，暂不绘图：' + str(error))
        table_exchange(frame, title, draft['module']['provenance'],
                       lambda v, name=name: key('exchange/'+name+'/'+v), replace_table, optional_source=True)
    if group == '翼型气动数据' and 'polar.json' in assets:
        grid = json.loads(assets['polar.json'])
        sections = grid['sections']
        station = st.selectbox('展向翼型站', range(len(sections)), key=key('span'),
                               format_func=lambda i: f'r/R = {sections[i]["r_over_R"]:g}',
                               help='选择需要编辑的展向站。表内保留原Re/Mach/攻角域及来源。')
        slices = sections[station].get('reynolds_slices', [sections[station]])
        layer = st.selectbox('雷诺数数据层', range(len(slices)), key=key('re'),
                             format_func=lambda i: str(slices[i].get('reynolds', '不区分Re')),
                             help='Re以当地弦长和相对速度定义；有分层数据时按log(Re)插值。')
        coefficient = st.selectbox('气动系数', ['cl', 'cd'], format_func=label, key=key('coefficient'),
                                   help='CL为升力系数，CD为阻力系数；无量纲。')
        item = slices[layer][coefficient]
        columns = ['alpha_deg'] + [f'Ma={m:g}' for m in item['mach']]
        frame = pd.DataFrame([[a, *v] for a, v in zip(item['alpha_deg'], item['values'])], columns=columns)
        def apply_grid(frame):
            item['values'] = finite_rows(frame[columns[1:]])
            grid['provenance'] = str(grid.get('provenance', '')) + '；用户修改当前气动数据层（待核）'
            assets['polar.json'] = json.dumps(grid, ensure_ascii=False, allow_nan=False).encode()
        table(frame, f'grid/{station}/{layer}/{coefficient}', apply_grid, disabled=['alpha_deg'])
        def replace_layer(incoming, source):
            if not np.array_equal(incoming['alpha_deg'], item['alpha_deg']):
                raise ValueError('攻角网格不一致；数据层导入只替换当前系数值。')
            candidate = deepcopy(current())
            new_grid = deepcopy(grid)
            new_slices = new_grid['sections'][station].get('reynolds_slices', [new_grid['sections'][station]])
            new_slices[layer][coefficient]['values'] = finite_rows(incoming[columns[1:]])
            new_grid['provenance'] = str(new_grid.get('provenance', ''))+'；'+source
            from .airfoils import AirfoilGrid
            AirfoilGrid(new_grid)
            candidate['assets']['polar.json'] = json.dumps(new_grid, ensure_ascii=False, allow_nan=False).encode()
            rotor_module.pack(candidate['module'], candidate['assets'])
            current().update(candidate)
            st.session_state['module-epoch'] += 1
            st.session_state[key('detail-group')] = group
            st.rerun()
        from .engineering_input_ui import table_exchange
        table_exchange(frame, '当前翼型数据层', str(grid.get('provenance', draft['module']['provenance'])),
                       lambda v: key(f'layer-exchange/{station}/{layer}/{coefficient}/'+v), replace_layer, optional_source=True)
        if 'outer_alpha' in item:
            outer = item['outer_alpha']
            st.caption('高攻角独立分支；保留原数据定义。')
            def apply_outer(frame):
                outer['values'] = [row[0] for row in finite_rows(frame[[coefficient]])]
                grid['provenance'] = str(grid.get('provenance', '')) + '；用户修改高攻角数据（待核）'
                assets['polar.json'] = json.dumps(grid, ensure_ascii=False, allow_nan=False).encode()
            table(pd.DataFrame({'alpha_deg': outer['alpha_deg'], coefficient: outer['values']}),
                  f'outer/{station}/{layer}/{coefficient}', apply_outer, disabled=['alpha_deg'])
        st.caption('数据来源：' + str(grid.get('provenance', current()['module']['provenance'])))
        from .previews import polar_figure, show
        try:
            show(polar_figure(item, coefficient))
        except (ValueError, TypeError) as error:
            st.warning('气动系数尚不完整，暂不绘图：' + str(error))


def details():
    module = current()['module']
    rotor = module['rotor']
    st.subheader('旋翼设置')
    with st.expander('详细设置'):
        group = st.selectbox('旋翼参数分组', ['总体参数', '桨叶质量矩', '桨毂质量属性', '挥舞特性', '操纵与载荷限制', '桨叶几何形状', '翼型气动数据'],
                             key=key('detail-group'), help='这些都是旋翼本体参数。安装位置、整机质量和动力在整机装配中设置。')
        if group == '总体参数':
            field(rotor, 'blade_count', '桨叶数', prefix='rotor', options=list(range(2, 13)))
            field(rotor, 'radius_m', prefix='rotor')
            field(rotor, 'pitch_reference_r_over_R', prefix='rotor')
            field(rotor, 'rotation_sign', '旋向', prefix='rotor', options=[1, -1],
                  format_func=lambda v: '+1：从+x向+y转动' if v == 1 else '−1：从+x向−y转动',
                  help='局部右手系z沿正推力轴，x为零方位。+1从正z端看向桨毂为逆时针；−1为顺时针。')
            optional(rotor, 'precone_deg', '固定对照预锥 / °', 0., 'rotor',
                     '仅选择固定桨叶对照时使用；采用模块挥舞特性时使用挥舞组预锥。旧文件两项保持原语义。')
            st.caption('半径改变时保持几何表中的实际弦长与扭转；质量矩不会自动缩放。')
        elif group == '桨叶质量矩':
            mass = module['blade_mass']
            st.info('均为单片桨叶，质量矩以挥舞铰为原点沿铰外桨叶积分。稳态挥舞使用一阶和二阶质量矩；单片质量暂用于记录与一致性检查。')
            for name, title, initial, note in [
                ('mass_kg', '单片桨叶质量 / kg', 1., '不含桨毂。'),
                ('first_mass_moment_kg_m', '铰外一阶质量矩 / (kg·m)', .5, '积分∫s dm，用于重力与惯性力矩。'),
                ('inertia_kg_m2', '挥舞惯量 Iβ / (kg·m²)', .3, '积分∫s² dm；s为距挥舞铰距离。')]:
                optional(mass, name, title, initial, 'blade', note)
            with st.expander('资料与备注（可选）'):
                field(mass, 'provenance', '桨叶质量资料来源', prefix='blade')
        elif group == '桨毂质量属性':
            hub = module['hub']
            st.info('此处保存桨毂本体属性。当前稳态气动求解不使用桨毂质量和惯量；动力学分账在A2接通。')
            optional(hub, 'mass_kg', '桨毂质量 / kg', 1., 'hub', '仅桨毂，不重复计入桨叶。')
            for name, title, default in [('cg_rotor_m', '桨毂重心坐标 / m', [0., 0., 0.]),
                                         ('inertia_cg_kg_m2', '桨毂重心惯量 / (kg·m²)', np.eye(3).tolist())]:
                if st.checkbox('填写' + title, value=name in hub, key=key(name+'known'), help='未知留空；坐标轴采用模块局部桨毂系。'):
                    hub.setdefault(name, default)
                    if name == 'cg_rotor_m':
                        vector(hub, name, title, default, 'hub', '相对局部桨毂原点；不是整机重心。')
                    else:
                        st.caption('完整惯量张量，行列均为x/y/z，非对角项按张量符号填写，须对称正定。')
                        table(pd.DataFrame(hub[name], columns=['x', 'y', 'z']), 'hub-inertia',
                              lambda frame: hub.update({name: finite_rows(frame)}))
                else:
                    hub.pop(name, None)
            with st.expander('资料与备注（可选）'):
                field(hub, 'provenance', '桨毂资料来源', prefix='hub')
        elif group == '挥舞特性':
            flap = module['flapping']
            field(flap, 'mode', '模块挥舞类型', options=['fixed', 'hinged'], prefix='flap',
                  format_func=lambda v: {'fixed': '固定桨叶', 'hinged': '铰接稳态挥舞'}[v])
            for name in ('hinge_offset_m', 'precone_deg', 'max_flap_deg'):
                field(flap, name, prefix='flap')
            for name, title in [('spring_nm_rad', '挥舞刚度 / (N·m/rad)'), ('damper_nms_rad', '挥舞阻尼 / (N·m·s/rad)'),
                                ('delta3_deg', '变距—挥舞耦合角 δ₃ / °')]:
                optional(flap, name, title, 0., 'flap', help_text(name))
            st.caption('铰接求解还需要桨叶一阶质量矩、挥舞惯量、刚度和阻尼。当前为一阶稳态挥舞，未接入完整动态挥舞。')
        elif group == '操纵与载荷限制':
            for container, name, title in [(rotor['limits'], 'rpm', '转速 / (r/min)'),
                                           (rotor['limits'], 'collective_deg', '总距 / °'),
                                           (rotor, 'cyclic_cos_deg', '余弦周期变距 / °'),
                                           (rotor, 'cyclic_sin_deg', '正弦周期变距 / °')]:
                values = container.get(name, [-15., 15.])
                for i, bound in enumerate(('下限', '上限')):
                    widget = key(name + bound)
                    def changed(i=i, container=container, name=name, widget=widget, values=values):
                        container.setdefault(name, list(values))[i] = st.session_state[widget]
                    st.number_input(title + bound, value=float(values[i]), key=widget, on_change=changed,
                                    help='用于工况检查与反求边界；上下限必须递增。')
            for name, title in [('power_w', '旋翼轴功率上限 / W'), ('torque_nm', '旋翼轴扭矩上限 / (N·m)')]:
                optional(rotor['limits'], name, title, 1000., 'limit', '旋翼本体允许值，不是发动机额定功率。')
        else:
            table_assets(group)


def physical_conditions(hidden):
    case = current()['case']
    st.subheader('旋翼工况设置')
    st.caption('局部右手系：z沿正推力轴，x为零方位，y由右手系确定。这里不涉及机头/机尾或整机安装。')
    field(case, 'method', '计算方法', default='spatial', options=['spatial', 'axial'], prefix='case',
          format_func=lambda v: {'spatial': '三方向方位角叶素', 'axial': '纯轴流性能'}[v],
          help='三方向法支持盘面内来流、周期变距和稳态挥舞；纯轴流法只支持固定桨叶、零周期变距。不会随来流静默换核。')
    field(case, 'flapping_model', '挥舞处理', default='module', options=['module', 'fixed'], prefix='case',
          format_func=lambda v: '采用模块挥舞特性' if v == 'module' else '固定桨叶对照',
          help='对照选项不修改模块本体。固定对照采用模块rotor中的历史固定预锥；若未给定则为0°。')
    if case.get('flapping_model', 'module') == 'fixed':
        st.caption(f"固定对照预锥：{current()['module']['rotor'].get('precone_deg', 0.):g}°（历史固定桨叶口径）。")
    motion = st.radio('速度填写方式', ['旋翼相对空气运动速度', '空气相对桨毂速度'], horizontal=True,
                      key=key('motion-view'), help='静止空气中，运动速度与空气相对桨毂速度互为相反数，入口只转换一次；均在旋翼局部系表达。')
    sign = -1 if motion.startswith('旋翼') else 1
    flow = case['flow_rotor_m_s']
    for i, col in enumerate(st.columns(3)):
        with col:
            if 'flow_'+'xyz'[i] in hidden:
                st.caption('该方向速度由扫描点列给定。')
                continue
            widget = key('velocity-' + str(sign) + str(i))
            def changed(i=i, widget=widget):
                case['flow_rotor_m_s'][i] = sign * st.session_state[widget]
                # Drop the other view so toggling always reflects the physical draft.
                st.session_state.pop(key('velocity-' + str(-sign) + str(i)), None)
            st.number_input(('盘面内 ' if i < 2 else '沿正推力轴 ') + 'xyz'[i] + '速度 / (m/s)',
                            value=float(sign*flow[i]), key=widget, on_change=changed,
                            help='正值沿局部轴正向。当前支持正贯流：运动z≥0，或空气相对速度z≤0；盘面内速度可正可负。')
    st.caption('实际空气相对桨毂速度 [x, y, z] = ' + str(case['flow_rotor_m_s']) + ' m/s')
    with st.expander('周期变距与试验姿态'):
        for name in ('cyclic_cos_deg', 'cyclic_sin_deg'):
            field(case, name, '余弦周期变距系数 θc / °' if name == 'cyclic_cos_deg' else '正弦周期变距系数 θs / °', default=0., prefix='case', help='θ(ψ)=总距+几何扭转差+θc cosψ+θs sinψ；ψ从局部+x朝+y几何增大；旋向决定桨叶经过的时间次序。单位°。')
        vector(case, 'gravity_rotor_m_s2', '局部重力 / (m/s²)', [0., 0., -9.80665], 'case',
               '水平向上旋翼填写[0,0,−9.80665]；竖直试验台按姿态投影，例如[0,−9.80665,0]。零向量仅用于无重力数值对照。')
    with st.expander('空气环境'):
        env = case.setdefault('environment', {'mode': 'isa', 'isa_temperature_offset_k': 0.})
        choice = st.selectbox('空气环境来源', ['isa', 'custom'], index=0 if env['mode'] == 'isa' else 1,
                              format_func=lambda v: '高度与ISA温差联动' if v == 'isa' else '填写当地空气性质',
                              key=key('environment-mode'), help='密度、声速与黏度属于工况，模块本体不保存第二套环境。')
        if choice != env['mode']:
            case['environment'] = ({'mode': 'isa', 'isa_temperature_offset_k': 0.} if choice == 'isa' else
                                   {'mode': 'custom', 'density_kg_m3': 1.225, 'speed_of_sound_m_s': 340.3,
                                    'dynamic_viscosity_pa_s': 1.7894e-5})
            env = case['environment']
            for name in ('isa_temperature_offset_k', 'density_kg_m3', 'speed_of_sound_m_s', 'dynamic_viscosity_pa_s'):
                st.session_state.pop(key(('isa' if name.startswith('isa') else 'custom') + '/' + name), None)
        if choice == 'isa':
            if 'altitude_m' not in hidden:
                field(case, 'altitude_m', '气压高度 / m', default=0., prefix='case')
            field(env, 'isa_temperature_offset_k', 'ISA温差 / K', default=0., prefix='isa', help='相对标准大气温度的偏差，正值更热。')
        else:
            for name in ('density_kg_m3', 'speed_of_sound_m_s', 'dynamic_viscosity_pa_s'):
                field(env, name, prefix='custom', format='%.9g')
        from .environment import from_case
        try:
            air = from_case(case)
            st.caption(f"实际密度 {air['density_kg_m3']:.6g} kg/m³；声速 {air['speed_of_sound_m_s']:.6g} m/s；动力黏度 {air['dynamic_viscosity_pa_s']:.6g} Pa·s。")
        except ValueError as error:
            st.error(str(error))
def conditions():
    case = current()['case']
    condition_area = st.container()
    if 'target' in case:
        st.session_state[key('target-draft')] = deepcopy(case['target'])
    if current().get('sweep'):
        st.session_state[key('sweep-draft')] = deepcopy(current()['sweep'])
    mode = st.radio('求解任务', ['给定操纵正算', '指定拉力反求', '批量性能扫描'], horizontal=True,
                    key=key('solve-task'), index=2 if current().get('sweep') else 1 if 'target' in case else 0,
                    help='正算给定总距和转速；反求在限位内寻找目标拉力；扫描固定模块，改变工况。')
    if mode == '指定拉力反求':
        target = case.setdefault('target', deepcopy(st.session_state.get(key('target-draft'), {'thrust_n': 1500., 'solve_for': 'collective_deg'})))
        field(target, 'thrust_n', '目标拉力 / N', prefix='target', help='沿正推力轴的正拉力；超出模块限位可达范围会报告失败。')
        field(target, 'solve_for', '反求变量', options=['collective_deg', 'rpm'], prefix='target',
              format_func=lambda v: '总距' if v == 'collective_deg' else '转速')
        if st.checkbox('限定反求搜索区间', value='bounds' in target, key=key('target-bounds'),
                       help='不勾选时使用模块限位。搜索区间必须在限位内，可用于排除多个解。'):
            target.setdefault('bounds', list(current()['module']['rotor']['limits'][target['solve_for']]))
            unit = '°' if target['solve_for'] == 'collective_deg' else 'r/min'
            for i, title in enumerate(('搜索下限', '搜索上限')):
                widget = key('bounds/' + str(i) + target['solve_for'])
                def changed(i=i, widget=widget):
                    target['bounds'][i] = st.session_state[widget]
                st.number_input(title + ' / ' + unit, value=float(target['bounds'][i]), key=widget,
                                on_change=changed, help='反求变量的实际搜索边界；修改待求变量后请核对单位和范围。')
        else:
            target.pop('bounds', None)
        st.caption('待求量在结果中显示；未限定搜索区间时采用旋翼限位。')
        current()['sweep'] = None
    else:
        case.pop('target', None)
        saved_sweep = current().get('sweep') or st.session_state.get(key('sweep-draft'))
        current()['sweep'] = None
        if mode == '批量性能扫描':
            from .module_batch import AXES
            axes = {}
            previous = (saved_sweep or {}).get('axes', {})
            axis_history = st.session_state.setdefault(key('axis-drafts'), {})
            axis_history.update(deepcopy(previous))
            dimensions = st.selectbox('扫描维数', [1, 2], index=max(0, len(previous)-1), key=key('scan-dim'), help='最多100点；每点保存独立工况与诊断。')
            for i in range(dimensions):
                initial = list(previous)[i] if i < len(previous) else list(AXES)[i]
                choices = [name for name in AXES if name not in axes]
                axis = st.selectbox(f'扫描参数{i+1}', choices, key=key(f'scan-axis{i}'), index=choices.index(initial) if initial in choices else 0,
                                    format_func=lambda v: AXES[v], help='只改变本次工况，旋翼几何、质量矩和挥舞属性保持。')
                default = case.get(axis, 0.) if not axis.startswith('flow_') else case['flow_rotor_m_s']['xyz'.index(axis[-1])]
                old_values = previous.get(axis, axis_history.get(axis, [default, default+.5, default+1.]))
                start = st.number_input(f'起点{i+1}', value=float(old_values[0]), key=key(f'start{i}/{axis}'), help=AXES[axis])
                stop = st.number_input(f'终点{i+1}', value=float(old_values[-1]), key=key(f'stop{i}/{axis}'), help=AXES[axis])
                spacing = st.selectbox(f'点列生成方式{i+1}', ['原点列/点数', '步长'], key=key(f'spacing{i}/{axis}'),
                                       help='旧不等间隔点列原样保留；主动选择步长后才重新生成。')
                if spacing == '步长':
                    from .engineering_inputs import scan_range
                    step = st.number_input(f'步长{i+1}', value=float(Decimal(str(old_values[1]))-Decimal(str(old_values[0]))) if len(old_values)>1 else 1.,
                                           key=key(f'step{i}/{axis}'), help=AXES[axis]+'；不补入偏离步长的终点。')
                    axes[axis] = scan_range(start, stop, step, maximum=100)
                else:
                    count = st.number_input(f'点数{i+1}', value=len(old_values), min_value=1, max_value=100, key=key(f'count{i}/{axis}'), help='包含起点和终点。')
                    axes[axis] = (list(old_values) if start == old_values[0] and stop == old_values[-1] and count == len(old_values)
                                  else np.linspace(start, stop, count).tolist())
                st.caption('实际扫描点：' + ', '.join(f'{value:g}' for value in axes[axis]) +
                           '。导入点列保持原值；修改端点或点数后生成等间隔点列。')
            current()['sweep'] = dict(schema_version=1, kind='rotor_module_sweep', axes=axes)
            from .module_batch import validate_spec
            validate_spec(dict(current()['sweep'], case_json='case.json'))
            st.caption(f'本次共{int(np.prod([len(v) for v in axes.values()]))}个工况；最多100点。')

    hidden = set((current().get('sweep') or {}).get('axes', {}))
    if 'target' in case:
        hidden.add(case['target']['solve_for'])
    with condition_area:
        physical_conditions(hidden)
    for name, title in [('collective_deg', '总距 / °'), ('rpm', '转速 / (r/min)')]:
        if name not in hidden:
            field(case, name, title, prefix='case', help='该任务的给定量；总距为参考站桨距角，转速为每分钟转数。')
    with st.expander('求解器参数设置'):
        rotor = current()['module']['rotor']
        field(rotor, 'inflow_model', '轴流性能入流模型', default='uniform', options=['uniform', 'annular'], prefix='rotor',
              format_func=lambda v: {'uniform': '均匀入流', 'annular': '径向环带入流'}[v],
              help='仅轴流性能法使用；三方向方位角叶素法使用Pitt–Peters三状态入流。')
        field(rotor, 'tip_loss', '轴流性能桨尖损失', default='none', options=['none', 'prandtl'], prefix='rotor',
              format_func=lambda v: {'none': '不附加', 'prandtl': 'Prandtl桨尖损失'}[v],
              help='只作用于轴流性能法；更换假设时分别记录比较。')
        field(rotor, 'polar_interpolation', '翼型攻角插值', default='linear_v1',
              options=['linear_v1', 'pchip_alpha_v1'], prefix='rotor',
              format_func=lambda v: {'linear_v1': '分段线性（旧方案）',
                                     'pchip_alpha_v1': '连续斜率 PCHIP（显式候选）'}[v],
              help='PCHIP目前仅支持CSV翼型表，保留CL/CD节点并使内部斜率连续。'
                   '不增加气动数据，不提高尾迹模型精度，不作域外外推。随模块保存并用于各求解任务；旧文件缺省仍为分段线性。')
        if 'polar_json' in rotor:
            st.caption('当前为Re/Mach多维翼型表，请使用分段线性；不兼容的PCHIP选项会明确拒算，可在上方改回。')
        for name, title, value in [('radial_stations', '径向叶素数', 80), ('azimuth_stations', '方位离散数', 36)]:
            widget = key(name)
            def changed(name=name, widget=widget):
                case[name] = st.session_state[widget]
            st.number_input(title, value=int(case.get(name, value)), min_value=8 if name == 'radial_stations' else 12,
                            max_value=2000 if name == 'radial_stations' else 720, step=1,
                            key=widget, on_change=changed, help='整数；加密后比较总量变化。轴流法不使用方位离散数。')


def manager():
    from .module_manager_ui import render
    render()


def results(record):
    answer, files = record['answer'], record['files']
    same = record['fingerprint'] == fingerprint()
    st.subheader('计算结果' if same else '上次结果（当前草稿已修改，请重新计算）')
    st.caption('结果旋翼：' + record['draft']['module']['name'])
    if answer['status'] != 'converged':
        st.error('求解失败：' + answer.get('error', '部分扫描点失败，请查看逐点诊断。'))
    else:
        st.success('求解已收敛')
    if 'thrust_n' in answer.get('summary', {}):
        summary = answer['summary']
        for col, name, title, factor in zip(st.columns(3), ('thrust_n', 'torque_nm', 'power_w'),
                                          ('拉力 / N', '轴扭矩 / (N·m)', '轴功率 / kW'), (1, 1, .001)):
            col.metric(title, f'{summary[name]*factor:.6g}')
        from .engineering_display import result_table
        st.dataframe(result_table(pd.DataFrame([summary])).rename(columns={
            'flap_coning_deg': '锥度角 / °', 'flap_cos_deg': '余弦一阶挥舞 / °',
            'flap_sin_deg': '正弦一阶挥舞 / °'}), hide_index=True)
        st.dataframe(pd.DataFrame([answer['force_rotor_n'], answer['moment_hub_rotor_nm']],
                                  index=['局部气动力 / N', '关于桨毂的气动力矩 / (N·m)'], columns=['x', 'y', 'z']))
        missing_limits = [name for name in ('power_w', 'torque_nm') if name not in record['draft']['module']['rotor']['limits']]
        if missing_limits:
            st.caption('未给定的部件限制未评价：' + '、'.join(label(name) for name in missing_limits))
        for field_name, title in [('support_status', '支持范围'), ('design_limits_status', '设计限制'), ('evidence_status', '验证依据')]:
            from .engineering_display import label as engineering_label
            value = answer.get(field_name, 'not_evaluated')
            translated = {'within_implemented_steady_domain': '在当前稳态实现范围内', 'model_estimate': '模型估算，精度按基准分别记录'}.get(value, engineering_label(value))
            st.write(title + '：' + translated)
    if 'performance.csv' in files:
        from .engineering_display import result_table
        from .module_batch import AXES
        st.dataframe(result_table(pd.read_csv(BytesIO(files['performance.csv']))).rename(
            columns=dict(AXES, point='工况编号')), hide_index=True)
    if 'radial_loads.csv' in files:
        import altair as alt
        frame = pd.read_csv(BytesIO(files['radial_loads.csv']))
        radius = 'radius_m' if 'radius_m' in frame else 'r_m'
        for name, title in [('thrust_n_per_m', '径向拉力密度 / (N/m)'), ('torque_nm_per_m', '径向扭矩密度 / N')]:
            if name in frame and radius in frame:
                chart = alt.Chart(frame).mark_line().encode(x=alt.X(radius, title='半径 / m'), y=alt.Y(name, title=title))
                st.altair_chart(chart, width='stretch')
        st.download_button('下载径向载荷 CSV', files['radial_loads.csv'], 'radial_loads.csv')
    for name in ('performance.png', 'azimuth.png'):
        if name in files:
            st.image(files[name])
    for warning in answer.get('warnings', []):
        st.caption(warning)
    with st.expander('缺项、参数使用与完整诊断'):
        st.json({k: v for k, v in answer.items() if k not in ('summary', 'warnings', 'rows')})
    st.download_button('下载结果与可搬移复算包', store.archive(files), 'rotor-result.zip')


def record_source_changes():
    module = current()['module']
    old = st.session_state.get('module-source-snapshot', module)
    for group in ('rotor', 'blade_mass', 'hub', 'flapping'):
        before = {k: v for k, v in old[group].items() if k != 'provenance'}
        after = {k: v for k, v in module[group].items() if k != 'provenance'}
        changed = sorted(k for k in before.keys() | after.keys() if before.get(k) != after.get(k))
        if changed:
            owner = module[group] if 'provenance' in module[group] else module
            note = '；用户修改（待核）：'+group+'/'+','.join(changed)
            if note not in owner['provenance']:
                owner['provenance'] += note
    st.session_state['module-source-snapshot'] = deepcopy(module)


def render():
    if 'module-draft' not in st.session_state:
        from .module_manager_ui import new_scheme
        replace(new_scheme(next(iter(store.TEMPLATES))))
    st.subheader('孤立旋翼')
    st.info('只配置一个旋翼：桨叶、桨毂、质量矩、挥舞和气动数据。工况中给定操纵、来流与试验姿态，无需整机参数。')
    record_source_changes()
    manager()
    if 'module-pending' in st.session_state:
        return
    ready = True
    try:
        details()
    except (ValueError, KeyError, TypeError) as error:
        st.error('详细设置需要修正，草稿保留：' + str(error))
    previous_sweep = deepcopy(current().get('sweep'))
    try:
        conditions()
    except (ValueError, TypeError) as error:
        ready = False
        current()['sweep'] = previous_sweep
        st.error('扫描或工况需要修正，历史结果保留：'+str(error))
    record_source_changes()
    with st.expander('方案来源与备注（可选）'):
        field(current()['module'], 'provenance', '来源与修改记录', prefix='module')
    if st.button('运行旋翼计算', type='primary', disabled=not ready, help='提交当前模块和工况；计算过程不会改写已保存方案或上次结果的输入。'):
        try:
            with st.spinner('正在计算旋翼…'):
                submitted = deepcopy(current())
                target = submitted['case'].get('target')
                if target:
                    # The bracket solver needs a legal placeholder, not a user seed.
                    bounds = target.get('bounds', submitted['module']['rotor']['limits'][target['solve_for']])
                    submitted['case'][target['solve_for']] = float(np.mean(bounds))
                record = store.execute(submitted)
                record['fingerprint'] = fingerprint()
                st.session_state['module-result'] = record
        except (ValueError, OSError, TypeError, KeyError) as error:
            st.error('未完成计算，草稿和上次结果已保留：' + str(error))
    if 'module-result' in st.session_state:
        results(st.session_state['module-result'])
