"""Draft-only geometry and source-table plots; no new physical model."""
from io import StringIO
import numpy as np
import pandas as pd
from .coordinates import selected_basis, vector3
from .presentation import configure_chinese_plots


def new_figure(*args, **kwargs):
    from matplotlib import pyplot as plt
    configure_chinese_plots()
    return plt.subplots(*args, **kwargs, layout='constrained')


def layout_figure(aircraft):
    cg = vector3(aircraft['mass_properties']['cg_m'], '重心坐标')
    angle = np.linspace(0, 2 * np.pi, 121)
    installed = []
    for rotor in aircraft['rotors']:
        basis = selected_basis(rotor)
        pos = vector3(rotor['position_m'], '桨毂位置')
        radius = float(rotor['radius_m'])
        if not np.isfinite(radius) or radius <= 0:
            raise ValueError('旋翼半径需要正值才能预览。')
        disk = pos[:, None] + radius * (basis[:, 0, None] * np.cos(angle) + basis[:, 1, None] * np.sin(angle))
        installed.append((rotor.get('role', 'main'), pos, disk))
    surfaces = [(s.get('id'), vector3(s['position_m'], '尾翼气动中心')) for s in aircraft.get('trim', {}).get('surfaces', [])]
    fig, axes = new_figure(1, 2, figsize=(9, 3.6))
    for ax, vertical, sign, title, ylabel in zip(axes, (2, 1), (-1, 1), ('侧视安装示意', '俯视安装示意'), ('向上位置 / m', '向右位置 / m')):
        ax.scatter(cg[0], sign * cg[vertical], marker='x', s=70, label='重心', color='black')
        for role, pos, disk in installed:
            name = '主旋翼' if role == 'main' else '尾桨'
            ax.plot(disk[0], sign * disk[vertical], label=name + '桨盘')
            ax.scatter(pos[0], sign * pos[vertical], s=15)
            ax.plot([cg[0], pos[0]], [sign * cg[vertical], sign * pos[vertical]], '--', color='0.65', linewidth=.8)
        for identifier, pos in surfaces:
            name = '平尾' if identifier == 'horizontal_tail' else '垂尾'
            ax.scatter(pos[0], sign * pos[vertical], marker='s', s=35, label=name + '气动中心')
        ax.set(title=title, xlabel='向前位置 / m', ylabel=ylabel)
        ax.set_aspect('equal', adjustable='datalim')
        ax.grid(alpha=.25)
        ax.legend(fontsize=8, loc='upper center', bbox_to_anchor=(.5, -.27), ncol=2, frameon=False)
    return fig


def csv_figure(text, geometry):
    data = pd.read_csv(StringIO(text))
    columns = ('r_over_R', 'chord_m', 'twist_deg') if geometry else ('alpha_deg', 'cl', 'cd')
    values = data[list(columns)].to_numpy(dtype=float)
    if not len(values) or not np.isfinite(values).all():
        raise ValueError('图表需要完整有限的数据。')
    fig, axes = new_figure(1, 2, figsize=(9, 3.3))
    names = ('弦长 / m', '原表几何扭转 / °') if geometry else ('升力系数 CL', '阻力系数 CD')
    xlabel = '半径比 r/R' if geometry else '攻角 α / °'
    for i, ax in enumerate(axes):
        ax.plot(values[:, 0], values[:, i + 1], marker='.', markersize=4)
        ax.set(xlabel=xlabel, ylabel=names[i])
        ax.grid(alpha=.25)
    return fig


def polar_figure(table, coefficient):
    alpha = np.asarray(table['alpha_deg'], dtype=float)
    mach = np.asarray(table['mach'], dtype=float)
    values = np.asarray(table['values'], dtype=float)
    if values.shape != (len(alpha), len(mach)) or not np.isfinite(values).all():
        raise ValueError('气动系数表尺寸或数值不完整。')
    fig, ax = new_figure(figsize=(8, 3.5))
    for j, value in enumerate(mach):
        ax.plot(alpha, values[:, j], label=f'Ma={value:g}')
    outer = table.get('outer_alpha')
    if outer:
        angles = np.asarray(outer['alpha_deg'])
        numbers = np.asarray(outer['values'])
        # Plot disconnected high-alpha branches separately; do not bridge the table gap.
        for i, mask in enumerate((angles < alpha[0], angles > alpha[-1])):
            ax.plot(angles[mask], numbers[mask], '--', color='black', label='独立高攻角分支' if i == 0 else None)
    ax.set(xlabel='攻角 α / °', ylabel='升力系数 CL' if coefficient == 'cl' else '阻力系数 CD')
    ax.grid(alpha=.25)
    ax.legend(fontsize=8, ncol=5, loc='upper center', bbox_to_anchor=(.5, -.23), frameon=False)
    return fig


def show(fig):
    import streamlit as st
    from matplotlib import pyplot as plt
    st.pyplot(fig)
    plt.close(fig)
