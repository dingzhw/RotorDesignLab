"""Local browser interface for RotorDesignLab."""

from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile

import altair as alt
import pandas as pd
import streamlit as st

from rotordesignlab.cases import THREE_BLADE, UH60, read_case, run_case, write_json

DEMO = "三片叶单旋翼"
HELICOPTER = "UH‑60 80 kt"
ENGINEERING = "工程旋翼"


def calculate_engineering(case, axes):
    from rotordesignlab.batch import run_batch
    with TemporaryDirectory(prefix='rotordesignlab-engineering-') as directory:
        base = Path(directory)
        case = dict(case, aircraft_json=str(Path(case['aircraft_json']).resolve()))
        output = base / 'result'
        if axes is None:
            result = run_case(case, base, output)
        else:
            write_json(base / 'input-case.json', case)
            spec = dict(schema_version=1, kind='rotor_sweep', case_json='input-case.json', axes=axes)
            result = run_batch(spec, base, output)
        return result, {file.relative_to(output).as_posix(): file.read_bytes()
                        for file in output.rglob('*') if file.is_file()}


def calculate(case, preset, uploads):
    with TemporaryDirectory(prefix="rotordesignlab-") as directory:
        base = Path(directory)
        for key, upload in uploads.items():
            if upload is None:
                case[key] = str(preset.parent / case[key])
            else:
                name = key + ".csv"
                (base / name).write_bytes(upload.getvalue())
                case[key] = name
        output = base / "result"
        result = run_case(case, base, output)
        return result, {file.name: file.read_bytes() for file in output.iterdir() if file.is_file()}


def frame(files, name):
    return pd.read_csv(BytesIO(files[name]))


def chart(data, x, y, x_title, y_title, *, log=False):
    x_scale = alt.Scale(type="log") if log else alt.Scale(zero=False)
    plot = alt.Chart(data).mark_line(color="#09696b", strokeWidth=2.5).encode(
        x=alt.X(x, title=x_title, scale=x_scale),
        y=alt.Y(y, title=y_title, scale=alt.Scale(zero=False)),
        tooltip=[alt.Tooltip(x, title=x_title, format=".4g"), alt.Tooltip(y, title=y_title, format=".4g")],
    ).properties(height=205)
    st.altair_chart(plot, width="stretch")


def show_rotor(result, files):
    summary = result["summary"]
    left, middle, right = st.columns(3)
    left.metric("拉力", f"{summary['thrust_n']:,.1f} N")
    middle.metric("轴扭矩", f"{summary['torque_nm']:,.2f} N·m")
    right.metric("轴功率", f"{summary['power_w']/1000:,.2f} kW")
    st.caption(f"诱导速度 {summary['induced_speed_m_s']:.3f} m/s · "
               f"入流平衡残差 {summary['residual_n']:.2e} N")
    st.caption(f"实际转速 {summary['rpm']:.3f} rpm · 总距 {summary['collective_deg']:.5f}°")
    if 'target_solution' in result:
        target = result['target_solution']
        label = '总距 / °' if target['solve_for'] == 'collective_deg' else '转速 / rpm'
        st.metric(f'反求{label}', f"{target['value']:.5f}")
        st.caption(f"目标拉力 {target['target_thrust_n']:g} N · 相对残差 {target['relative_thrust_error']:.2e}")
    if 'installation' in result:
        margins = result['installation']['margins']
        st.caption('给定限制的余量：' + ('，'.join(
            f"{('功率' if key == 'power_w' else '扭矩')} {value:.2f} {('W' if key == 'power_w' else 'N·m')}"
            for key, value in margins.items()) or '机型未提供功率和扭矩上限'))
    data = frame(files, "radial_loads.csv")
    tab_t, tab_q = st.tabs(["径向拉力", "径向扭矩"])
    with tab_t:
        chart(data, "r_m", "thrust_n_per_m", "半径 / m", "单位展长拉力 / N·m⁻¹")
    with tab_q:
        chart(data, "r_m", "torque_nm_per_m", "半径 / m", "单位展长扭矩 / N·m/m")


def show_uh60(result, files):
    st.metric("配平加权残差", f"{result['summary']['weighted_trim_residual']:.3e}")
    controls = frame(files, "trim_controls.csv").rename(columns={"value_pct": "操纵量 / %"})
    controls["control"] = ["横向杆", "纵向杆", "总距杆", "脚蹬"]
    st.dataframe(controls.rename(columns={"control": "操纵"}), hide_index=True, width="stretch")
    frequency, response = st.tabs(["全阶频响", "开环时程"])
    with frequency:
        method = st.radio("线化口径", ["固定方位", "方位平均"], horizontal=True)
        channels = {"横滚 / 横向杆": "p_lateral", "俯仰 / 纵向杆": "q_longitudinal", "偏航 / 脚蹬": "r_pedal"}
        channel = channels[st.selectbox("操纵通道", channels)]
        label = "fixed_azimuth" if method == "固定方位" else "azimuth_average"
        data = frame(files, label + "_frequency.csv")
        chart(data, "frequency_rad_s", channel + "_db", "角频率 / rad·s⁻¹", "幅值 / dB", log=True)
        chart(data, "frequency_rad_s", channel + "_phase_deg", "角频率 / rad·s⁻¹", "相位 / °", log=True)
        st.caption("幅值以角速度 rad/s 对操纵百分比计。")
    with response:
        data = frame(files, "open_loop.csv")
        chart(data, "time_s", "p_rad_s", "时间 / s", "横滚角速度 / rad·s⁻¹")


st.set_page_config(page_title="RotorDesignLab｜旋翼设计台", layout="wide")
st.title("RotorDesignLab｜旋翼设计台")
choice = st.radio("选择算例", [DEMO, HELICOPTER, ENGINEERING, '整机悬停预算'], horizontal=True)
if choice == '整机悬停预算':
    from rotordesignlab.hover_ui import render
    render()
    st.stop()
preset = THREE_BLADE if choice == DEMO else (UH60 if choice == HELICOPTER else THREE_BLADE.parent / 'engineering-rotor.json')
case = read_case(preset)
uploads = {}
axes = None
if choice == ENGINEERING:
    engineering_mode = st.radio('计算方式', ['正算', '反求总距', '反求转速', '批量正算', '批量反求总距'], horizontal=True)

with st.form("case_parameters"):
    if choice == DEMO:
        condition = st.selectbox("飞行状态", ["悬停", "轴向推进"])
        left, middle, right = st.columns(3)
        case["rpm"] = left.number_input("转速 / rpm", 1, 30000, case["rpm"])
        case["collective_deg"] = middle.number_input("总距 / °", -20.0, 55.0, float(case["collective_deg"]))
        speed = right.number_input("推进算例来流 / m/s", 0.1, 150.0, 25.0)
        case["axial_speed_m_s"] = 0.0 if condition == "悬停" else speed
        with st.expander("专业设置"):
            left, right = st.columns(2)
            case["radius_m"] = left.number_input("半径 / m", 0.03, 30.0, case["radius_m"])
            case["blade_count"] = right.number_input("桨叶数", 2, 12, case["blade_count"])
            case["density_kg_m3"] = left.number_input("空气密度 / kg/m³", 0.05, 3.0, case["density_kg_m3"], format="%.3f")
            case["radial_stations"] = right.number_input("径向叶素数", 8, 2000, case["radial_stations"])
            case["pitch_reference_r_over_R"] = left.number_input(
                "总距参考站 r/R", 0.0, 1.0, case["pitch_reference_r_over_R"])
            uploads["geometry_csv"] = left.file_uploader("桨叶几何 CSV", type="csv")
            uploads["polar_csv"] = right.file_uploader("翼型极曲线 CSV", type="csv")
    elif choice == HELICOPTER:
        st.write("80 kt 平飞配平、频率响应和短时横向操纵。")
        with st.expander("专业设置"):
            left, right = st.columns(2)
            case["duration_s"] = left.number_input("仿真时长 / s", 0.1, 3.0, 1.0, 0.1)
            case["time_step_s"] = right.selectbox("积分步长 / s", [0.02, 0.01, 0.005, 0.0025], index=1)
    else:
        case['aircraft_json'] = st.text_input('本地机型 JSON 路径', str(preset.parent / 'synthetic-aircraft.json'))
        left, middle, right = st.columns(3)
        case['rotor_id'] = left.text_input('旋翼 ID', 'main')
        case['rpm'] = middle.number_input('转速 / rpm', 1.0, 30000.0, 1700.0)
        case['collective_deg'] = right.number_input('总距 / °', -20.0, 55.0, 17.0)
        case['axial_speed_m_s'] = left.number_input('轴向来流 / m/s', 0.0, 150.0, 0.0)
        case['density_kg_m3'] = middle.number_input('空气密度 / kg/m³', 0.05, 3.0, 1.225, format='%.3f')
        if '反求' in engineering_mode:
            thrust = right.number_input('目标拉力 / N', 0.1, 1e7, 2000.0)
            case['target'] = dict(thrust_n=thrust, solve_for='rpm' if engineering_mode == '反求转速' else 'collective_deg')
        if '批量' in engineering_mode:
            sweep_x_key = 'target_thrust_n' if '反求' in engineering_mode else 'collective_deg'
            sweep_x = st.text_input('目标拉力扫描 / N（逗号分隔）' if '反求' in engineering_mode else '总距扫描 / °（逗号分隔）',
                                    '1000,1500,2000,2500,3000' if '反求' in engineering_mode else '6,8,10,12,14,16,18,20,22,24')
            sweep_rpm = st.text_input('转速扫描 / rpm（逗号分隔）', '1400,1700,2000')
        st.caption('机型默认采用合成参数。当前分析选定孤立旋翼，机型文件与结果均保存在本机。')
    submitted = st.form_submit_button("运行工况", type="primary")

if submitted:
    with st.spinner("正在求解工况…"):
        if choice == ENGINEERING:
            try:
                if '批量' in engineering_mode:
                    axes = {sweep_x_key: [float(value) for value in sweep_x.split(',')],
                            'rpm': [float(value) for value in sweep_rpm.split(',')]}
                st.session_state[choice] = calculate_engineering(case, axes)
            except (OSError, ValueError) as error:
                st.error(str(error))
        else:
            st.session_state[choice] = calculate(case, preset, uploads)

if choice in st.session_state:
    result, files = st.session_state[choice]
    is_batch = result.get('model') == 'rotor_batch'
    saved = json.loads(files['batch.json' if is_batch else 'case.json'])
    if choice == DEMO:
        st.caption(f"本次结果 · {saved['rpm']:.0f} rpm · 总距 {saved['collective_deg']:g}° · "
                   f"轴向来流 {saved['axial_speed_m_s']:g} m/s")
    elif choice == HELICOPTER:
        st.caption(f"本次结果 · 80 kt · {saved['duration_s']:g} s · 步长 {saved['time_step_s']:g} s")
    elif is_batch:
        st.caption(f"本次实际扫描：{saved.get('axes', {})}")
    else:
        st.caption(f"本次输入 · 旋翼 {saved.get('rotor_id', '')} · 轴向来流 {saved.get('axial_speed_m_s', 0):g} m/s")
    if is_batch:
        if result['summary']:
            summary = result['summary']
            left, middle, right = st.columns(3)
            left.metric('收敛 / 总工况', f"{summary['converged']} / {summary['total']}")
            middle.metric('求解失败', summary['failed'])
            right.metric('超过给定限制', summary['limit_violations'])
        if 'performance.png' in files:
            st.image(files['performance.png'], caption='批量性能图：红叉为超限点，失败点保留在结果表中。')
            st.dataframe(frame(files, 'performance.csv'), hide_index=True)
        if result['status'] != 'converged':
            st.error(result['error'])
    elif result["status"] == "converged":
        if choice in (DEMO, ENGINEERING):
            show_rotor(result, files)
        else:
            show_uh60(result, files)
    else:
        st.error(result["error"])
    for warning in result["warnings"]:
        st.caption(warning)
    archive = BytesIO()
    with ZipFile(archive, "w", ZIP_DEFLATED) as bundle:
        for name, data in sorted(files.items()):
            bundle.writestr(name, data)
    st.download_button("下载完整结果与工况", archive.getvalue(), "rotordesignlab-result.zip")
