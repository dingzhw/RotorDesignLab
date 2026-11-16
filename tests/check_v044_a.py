"""Measure real call counts and workflow stages on public/synthetic inputs."""
from io import BytesIO
import json
import os
from pathlib import Path
import platform
import sys
from time import perf_counter
from unittest.mock import patch
from zipfile import ZipFile, ZIP_DEFLATED

from rotordesignlab import __version__, designs
from rotordesignlab.azimuth import AzimuthRotor
from rotordesignlab.open_loop_plots import save_figures


def measure(template, speed, analysis):
    counters = dict(element_calls=0, element_elapsed_s=0., plot_elapsed_s=0.)
    original = AzimuthRotor.elements

    def elements(self, *args, **kwargs):
        counters['element_calls'] += 1
        started = perf_counter()
        try:
            return original(self, *args, **kwargs)
        finally:
            counters['element_elapsed_s'] += perf_counter() - started

    def plot(*args, **kwargs):
        started = perf_counter()
        try:
            return save_figures(*args, **kwargs)
        finally:
            counters['plot_elapsed_s'] += perf_counter() - started

    case = dict(schema_version=3, model='helicopter', analysis=analysis, altitude_m=0.,
                speed_m_s=speed, climb_m_s=0., requested_duration_s=600., radial_stations=24, azimuth_stations=24)
    started = perf_counter()
    with patch.object(AzimuthRotor, 'elements', elements), patch('rotordesignlab.open_loop_plots.save_figures', plot):
        result, files = designs.execute(designs.from_template(template), case)
    workflow = perf_counter() - started
    archive = BytesIO()
    started = perf_counter()
    with ZipFile(archive, 'w', ZIP_DEFLATED) as stream:
        for name, data in files.items():
            stream.writestr(name, data)
    zip_elapsed = perf_counter() - started
    diagnostic = result.get('diagnostics', result.get('trim', {}).get('diagnostics', {}))
    return dict(template=template, case=case, status=result['status'], error=result.get('error'),
                solver_status=result['solver_status'], support_status=result['support_status'],
                trim_diagnostics=diagnostic, measured=counters, workflow_elapsed_s=workflow,
                workflow_timings_s=result['workflow_timings_s'], result_zip_elapsed_s=zip_elapsed,
                result_zip_bytes=len(archive.getvalue()))


if __name__ == '__main__':
    names = list(designs.TEMPLATES)
    records = [measure(names[0], 20., 'linearize'), measure(names[1], 40., 'trim')]
    assert records[0]['status'] == 'converged', records[0]
    assert records[1]['status'] == 'failed' and records[1]['solver_status'] == 'converged', records[1]
    assert all(r['trim_diagnostics']['residual_calls'] > r['trim_diagnostics']['nfev'] for r in records)
    payload = dict(solver_version=__version__, python=platform.python_version(), platform=platform.platform(),
                   processor=platform.processor(), logical_cpu_count=os.cpu_count(), cases=records,
                   timing_scope='Wall clock, warm dependency imports; element timer nested in solver timer, not additive.')
    Path(sys.argv[1]).write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps([dict(status=r['status'], elapsed_s=r['workflow_elapsed_s'],
                           nfev=r['trim_diagnostics']['nfev'], njev=r['trim_diagnostics']['njev'],
                           residual_calls=r['trim_diagnostics']['residual_calls'],
                           element_calls=r['measured']['element_calls']) for r in records], ensure_ascii=False))
