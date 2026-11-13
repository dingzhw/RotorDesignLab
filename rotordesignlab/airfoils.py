"""Spanwise interpolation of original, independently gridded CL/CD tables."""
import json
from pathlib import Path

import numpy as np


class AirfoilGrid:
    def __init__(self, data):
        if (not isinstance(data, dict) or type(data.get('schema_version')) is not int or
                data['schema_version'] != 1 or data.get('kind') != 'spanwise_airfoil' or
                data.get('span_boundary') != 'hold_endpoint'):
            raise ValueError('Invalid spanwise airfoil database or boundary policy.')
        self.data = data
        self.sections = data.get('sections', [])
        self.span = np.asarray([section['r_over_R'] for section in self.sections], dtype=float)
        if not len(self.span) or not np.isfinite(self.span).all() or not (np.diff(self.span) > 0).all() or not (0 <= self.span[0] <= self.span[-1] <= 1):
            raise ValueError('Airfoil radial anchors must be finite and strictly increasing within [0,1].')
        self.tables = []
        for section in self.sections:
            tables = {}
            for key in ('cl', 'cd'):
                table = section[key]
                alpha, mach, values = (np.asarray(table[name], dtype=float) for name in ('alpha_deg', 'mach', 'values'))
                if (len(alpha) < 2 or len(mach) < 2 or values.shape != (len(alpha), len(mach)) or
                    not all(np.isfinite(array).all() for array in (alpha, mach, values)) or
                    not (np.diff(alpha) > 0).all() or not (np.diff(mach) > 0).all() or
                    mach[0] < 0 or alpha[0] >= 0 or alpha[-1] <= 0 or (key == 'cd' and (values < 0).any())):
                    raise ValueError('Invalid CL/CD table dimensions, domain, ordering or drag.')
                tables[key] = alpha, mach, values
            self.tables.append(tables)

    @classmethod
    def read(cls, path):
        try:
            return cls(json.loads(Path(path).read_text(encoding='utf-8-sig')))
        except (KeyError, TypeError, IndexError) as error:
            raise ValueError('Incomplete spanwise airfoil database.') from error

    def coefficients(self, span, alpha, mach, *, strict=False):
        span, alpha, mach = np.broadcast_arrays(span, alpha, mach)
        if not all(np.isfinite(value).all() for value in (span, alpha, mach)):
            raise ValueError('Non-finite airfoil lookup coordinate.')
        weights = [np.interp(span, self.span, np.eye(len(self.span))[index]) for index in range(len(self.span))]
        outputs = []
        for key in ('cl', 'cd'):
            output = np.zeros_like(alpha, dtype=float)
            for section, weight in zip(self.tables, weights):
                aa, mm, zz = section[key]
                active = weight > 1e-12
                if strict and np.any(active & ((alpha < aa[0]) | (alpha > aa[-1]) | (mach < mm[0]) | (mach > mm[-1]))):
                    raise ValueError(f'Converged element lies outside the {key.upper()} alpha/Mach table domain.')
                # Root search may visit invalid trial states; final states are checked strictly.
                a, m = np.clip(alpha, aa[0], aa[-1]), np.clip(mach, mm[0], mm[-1])
                i = np.clip(np.searchsorted(aa, a)-1, 0, len(aa)-2)
                j = np.clip(np.searchsorted(mm, m)-1, 0, len(mm)-2)
                wa, wm = (a-aa[i])/(aa[i+1]-aa[i]), (m-mm[j])/(mm[j+1]-mm[j])
                value = (1-wa)*((1-wm)*zz[i,j]+wm*zz[i,j+1])+wa*((1-wm)*zz[i+1,j]+wm*zz[i+1,j+1])
                output += weight*value
            outputs.append(output)
        return tuple(outputs)
