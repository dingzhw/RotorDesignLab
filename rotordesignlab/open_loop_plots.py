"""Standalone export figures; all plotted data remain in adjacent CSV/JSON."""
from pathlib import Path
import csv
import numpy as np
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt


def save_figures(output,result):
    out=Path(output);meta=result['linearization']
    fig,ax=plt.subplots(figsize=(7,4.5))
    roots=[m for m in meta['modes'] if m['within_low_frequency_band']]
    ax.scatter([m['real'] for m in roots],[m['imag'] for m in roots],c=['#cf4e33' if m['real']>1e-7 else '#087e8b' for m in roots])
    ax.axvline(0,color='grey',lw=.8);ax.axhline(0,color='grey',lw=.8);ax.grid(alpha=.2)
    ax.set(xlabel='Real / 1/s',ylabel='Imaginary / rad/s',title='Low-frequency poles (model estimate)')
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
        pair[0].set_ylabel(f'{control} -> {state}\ndB re 1 {unit}');pair[1].set_ylabel('Phase / deg')
        for ax in pair:ax.grid(alpha=.25)
    for ax in axes[-1]:ax.set_xlabel('Frequency / rad/s')
    fig.suptitle('Reduced open-loop frequency response (raw blade-pitch inputs)');fig.tight_layout()
    for suffix in ('png','svg'):fig.savefig(out/f'frequency.{suffix}',dpi=160)
    plt.close(fig)
    if (out/'response.csv').exists():
        with (out/'response.csv').open() as f:history=list(csv.DictReader(f))
        fig,axes=plt.subplots(3,2,figsize=(9,8),sharex=True);time=[float(r['time_s']) for r in history]
        for state,ax in zip(('u','v','w','p','q','r'),axes.ravel()):
            for kind,style in [('nonlinear','-'),('linear','--')]:
                ax.plot(time,[float(r[state+'_'+kind]) for r in history],style,label=kind)
            ax.set_ylabel('Delta '+state+(' / m/s' if state in 'uvw' else ' / rad/s'));ax.grid(alpha=.25)
        axes[0,0].legend();axes[-1,0].set_xlabel('Time / s');axes[-1,1].set_xlabel('Time / s');fig.tight_layout()
        for suffix in ('png','svg'):fig.savefig(out/f'response.{suffix}',dpi=160)
        plt.close(fig)
