"""Extract only public NASA inputs and Betzina Fig. 15 vector markers.

Requires PyMuPDF in the extraction environment; solving needs no PDF library.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import re

import numpy as np
import pymupdf


def save_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+'\n', encoding='utf-8')


def prepare(source, output):
    output.mkdir(parents=True, exist_ok=True)
    pdf = source / 'XV15_TP2004_212262.pdf'
    experiment = source / 'XV15_Betzina_2002.pdf'
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (pdf, experiment)}
    assert hashes[pdf.name] == '22ac1ffbb618c3070df22340b7392bf17a2c20b8dcdc4bde3853cd944833219c'
    assert hashes[experiment.name] == '24c79ddd95a7dc9c98ca72fa0168d8e09a7cda55e4021e39f9210d2f88de9180'
    doc = pymupdf.open(pdf)
    text = '\n'.join(page.get_text() for page in doc)
    starts = list(re.finditer(r'64-X(25|18|12|08)\s+2-D\s+AERODYNAMICS[^\n]*\n', text))
    assert len(starts) == 4
    sections = []
    for match, count, radius in zip(starts, [3, 9, 12, 12], [.2, .55, .8, .95]):
        numbers = []
        for line in text[match.end():].split('CLCD301', 1)[0].splitlines():
            tokens = line.split()
            if len(tokens) < 2:
                continue
            try:
                numbers.extend(float(token) for token in tokens)
            except ValueError:
                raise ValueError(f'Unexpected table text: {line}')
        section = dict(r_over_R=radius, name='64-X'+match[1])
        cursor = 0
        for coefficient in ('cl', 'cd', 'cm'):
            mach = numbers[cursor:cursor+count]
            cursor += count
            values = np.array(numbers[cursor:cursor+23*(count+1)]).reshape(23, count+1)
            cursor += values.size
            assert np.all(np.diff(mach) > 0) and np.all(np.diff(values[:, 0]) > 0)
            assert values[0, 0] == -180 and values[-1, 0] == 180
            if coefficient == 'cd':
                assert values[:, 1:].min() >= 0
            section[coefficient] = dict(mach=mach, alpha_deg=values[:, 0].tolist(), values=values[:, 1:].tolist())
        assert cursor == len(numbers)
        sections.append(section)
    save_json(output/'airfoils.json', dict(schema_version=1, kind='spanwise_airfoil',
        source='NASA/TP-2004-212262 Appendix A pp.28-33, CLCD3015-3018 (1975)',
        reynolds_dependence='not provided', span_boundary='hold_endpoint', sections=sections))
    raw = re.search(r'TWISTA\s*=\s*(.*?)THETAC', text, re.S)[1]
    twist = np.array([float(value) for value in raw.strip().rstrip(',').split(',')])
    assert len(twist) == 51 and abs(np.interp(.75, np.linspace(0, 1, 51), twist)) < 1e-12
    radius = np.unique(np.round(np.r_[np.arange(.1,1.0001,.02),.2,.25,.55,.75,.8,.95,1.],10))
    chord = np.interp(radius, [0, .1, .2, .3, 1], [1.32125, 1.32125, 1.17375, 1.16625, 1.16625]) * .3048
    np.savetxt(output/'geometry.csv', np.column_stack([radius, chord, np.interp(radius, np.linspace(0, 1, 51), twist)]),
               delimiter=',', header='r_over_R,chord_m,twist_deg', comments='', fmt='%.12g')
    # Original PDF coordinates, not fitted to any solver output.
    plot = dict(x0=371.812988, x1=540.810974, y0=412.243988, y1=285.523987,
                xmin=0., xmax=.14, ymin=0., ymax=.014)
    page = pymupdf.open(experiment)[5]
    rows = []
    for index, drawing in enumerate(page.get_drawings()):
        shape = ''.join(item[0] for item in drawing['items'])
        rect = drawing['rect']
        if drawing['type'] != 'f' or drawing['fill'] != (0., 0., 0.) or shape not in ('cccc', 'lll'):
            continue
        x, y = (rect.x0+rect.x1)/2, (rect.y0+rect.y1)/2
        if not (plot['x0'] < x < plot['x1'] and plot['y1'] < y < plot['y0'] and 3 < rect.width < 4 and 3 < rect.height < 4):
            continue
        if 383 < x < 438 and 295 < y < 320:  # legend, visually checked on PDF p.6
            continue
        ct_sigma = (x-plot['x0'])/(plot['x1']-plot['x0'])*.14
        cq_sigma = (plot['y0']-y)/(plot['y0']-plot['y1'])*.014
        rows.append(dict(run=33 if shape == 'cccc' else 51, drawing_index=index,
                         pdf_x_pt=x, pdf_y_pt=y, ct_sigma=ct_sigma, cq_sigma=cq_sigma))
    assert len(rows) == 20, len(rows)
    rows.sort(key=lambda row: (row['run'], row['ct_sigma']))
    with (output/'betzina_fig15.csv').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    save_json(output/'provenance.json', dict(sources=hashes, geometry_pdf_pages=[29,31],
        airfoil_pdf_pages=list(range(34,40)), experiment_pdf_page=6, experiment_figure=15,
        experiment='Runs 33 and 51; hub-tare corrected', plot_calibration=plot,
        marker_center_bound_pt=.3, uncertainty_type='digitization bound, not experimental confidence interval',
        test=dict(blades=3, radius_m=3.81, mach_tip=.691, solidity_reference=.089, precone_deg=1.5, axial_speed_m_s=0),
        assumptions=dict(density_kg_m3=1.225, speed_of_sound_m_s=340.3,
                         rigid_blade=True, sweep_deg=0, reynolds_correction=False),
        gaps=['Test density/temperature and pointwise collective not reported here.',
              'Engineering blade geometry/polars are not as-built measurements for each test run.',
              'Source airfoil tables have no Reynolds dimension; original labels retained.',
              'Elastic twist, sweep, rotor/hub interaction and facility corrections are not modeled.']))
    print(json.dumps(dict(sections=4, markers=len(rows), geometry_stations=len(radius))))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--sources', type=Path, default=Path('runs/public-sources'))
    parser.add_argument('--out', type=Path, default=Path('validation/xv15'))
    args = parser.parse_args()
    prepare(args.sources, args.out)
