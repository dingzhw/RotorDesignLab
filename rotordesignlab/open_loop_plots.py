"""Standalone export figures; all plotted data remain in adjacent CSV/JSON."""
from pathlib import Path
import csv
import numpy as np
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt
from .presentation import configure_chinese_plots, CONTROL_LABELS, STATE_LABELS


def save_figures(output,result):
    configure_chinese_plots()
    out=Path(output);meta=result['linearization']
    fig,ax=plt.subplots(figsize=(7,4.5))
    roots=[m for m in meta['modes'] if m['within_low_frequency_band']]
    ax.scatter([m['real'] for m in roots],[m['imag'] for m in roots],c=['#cf4e33' if m['real']>1e-7 else '#087e8b' for m in roots])
    ax.axvline(0,color='grey',lw=.8);ax.axhline(0,color='grey',lw=.8);ax.grid(alpha=.2)
    ax.set(xlabel='特征根实部 / (1/s)',ylabel='特征根虚部 / (rad/s)',title='低频特征根（试验性·模型估算）')
    fig.tight_layout()
    for suffix in ('png','svg'):fig.savefig(out/f'modes.{suffix}',dpi=160)
    plt.close(fig)
    with (out/'frequency.csv').open() as f:rows=list(csv.DictReader(f))
    channels=[('main_collective','w','(m/s)/rad'),('main_cos','q','(rad/s)/rad'),('main_sin','p','(rad/s)/rad'),('tail_collective','r','(rad/s)/rad')]
    fig,axes=plt.subplots(4,2,figsize=(10,10),sharex=True)
    for (control,state,unit),pair in zip(channels,axes):
        selected=[r for r in rows if r['input']==control and r['output']==state]
        omega=[float(r['omega_rad_s']) for r in selected];gain=[float(r['gain_db']) for r in selected]
        phase=np.rad2deg(np.unwrap(np.deg2rad([float(r['phase_deg']) for r in selected])))
        pair[0].semilogx(omega,gain);pair[1].semilogx(omega,phase)
        pair[0].set_ylabel(f'{CONTROL_LABELS[control]} → {state}\n幅值 / dB（基准：1 {unit}）');pair[1].set_ylabel('相位 / °')
        for ax in pair:ax.grid(alpha=.25)
    for ax in axes[-1]:ax.set_xlabel('角频率 / (rad/s)')
    fig.suptitle('低频开环频率响应（试验性·桨叶变距角输入）')
    fig.tight_layout()
    for suffix in ('png','svg'):fig.savefig(out/f'frequency.{suffix}',dpi=160)
    plt.close(fig)
    if (out/'response.csv').exists():
        with (out/'response.csv').open() as f:history=list(csv.DictReader(f))
        fig,axes=plt.subplots(3,2,figsize=(9,8),sharex=True);time=[float(r['time_s']) for r in history]
        for state,ax in zip(('u','v','w','p','q','r'),axes.ravel()):
            for kind,style in [('nonlinear','-'),('linear','--')]:
                ax.plot(time,[float(r[state+'_'+kind]) for r in history],style,label={'nonlinear':'非线性','linear':'线性'}[kind])
            ax.set_ylabel(STATE_LABELS[state]+' 增量'+(' / (m/s)' if state in 'uvw' else ' / (rad/s)'));ax.grid(alpha=.25)
        axes[0,0].legend()
        axes[-1,0].set_xlabel('时间 / s')
        axes[-1,1].set_xlabel('时间 / s')
        fig.suptitle('开环小扰动响应（低频模型·试验性）')
        fig.tight_layout()
        for suffix in ('png','svg'):fig.savefig(out/f'response.{suffix}',dpi=160)
        plt.close(fig)
