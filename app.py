"""Local browser interface for RotorDesignLab."""

from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile

import altair as alt
import pandas as pd
import streamlit as st

from rotordesignlab.cases import THREE_BLADE, UH60, read_case, run_case

DEMO = "三片叶单旋翼"
HELICOPTER = "UH‑60 80 kt"


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
choice = st.radio("选择算例", [DEMO, HELICOPTER], horizontal=True)
preset = THREE_BLADE if choice == DEMO else UH60
case = read_case(preset)
uploads = {}

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
    else:
        st.write("80 kt 平飞配平、频率响应和短时横向操纵。")
        with st.expander("专业设置"):
            left, right = st.columns(2)
            case["duration_s"] = left.number_input("仿真时长 / s", 0.1, 3.0, 1.0, 0.1)
            case["time_step_s"] = right.selectbox("积分步长 / s", [0.02, 0.01, 0.005, 0.0025], index=1)
    submitted = st.form_submit_button("运行工况", type="primary")

if submitted:
    with st.spinner("正在求解工况…"):
        st.session_state[choice] = calculate(case, preset, uploads)

if choice in st.session_state:
    result, files = st.session_state[choice]
    saved = json.loads(files["case.json"])
    if choice == DEMO:
        st.caption(f"本次结果 · {saved['rpm']:.0f} rpm · 总距 {saved['collective_deg']:g}° · "
                   f"轴向来流 {saved['axial_speed_m_s']:g} m/s")
    else:
        st.caption(f"本次结果 · 80 kt · {saved['duration_s']:g} s · 步长 {saved['time_step_s']:g} s")
    if result["status"] == "converged":
        if choice == DEMO:
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
