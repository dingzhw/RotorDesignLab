"""Spanwise interpolation of original, independently gridded CL/CD tables."""
import json
from pathlib import Path

import numpy as np


class AirfoilGrid:
    def __init__(self, data):
        if (not isinstance(data, dict) or type(data.get('schema_version')) is not int or
                data['schema_version'] not in (1,2) or data.get('kind') != 'spanwise_airfoil' or
                data.get('span_boundary') != 'hold_endpoint'):
            raise ValueError('Invalid spanwise airfoil database or boundary policy.')
        self.data = data
        self.sections = data.get('sections', [])
        self.span = np.asarray([section['r_over_R'] for section in self.sections], dtype=float)
        if not len(self.span) or not np.isfinite(self.span).all() or not (np.diff(self.span) > 0).all() or not (0 <= self.span[0] <= self.span[-1] <= 1):
            raise ValueError('Airfoil radial anchors must be finite and strictly increasing within [0,1].')
        self.tables = []
        self.reynolds=[]
        for section in self.sections:
            slices=section.get('reynolds_slices') if data['schema_version']==2 else [section]
            if not isinstance(slices,list) or not slices:raise ValueError('Missing Reynolds slices.')
            re=np.array([s.get('reynolds',1.) for s in slices],dtype=float)
            if not np.isfinite(re).all() or np.any(re<=0) or np.any(np.diff(re)<=0):raise ValueError('Reynolds nodes must be positive and increasing.')
            self.reynolds.append(re)
            self.tables.append([self.parse_tables(s) for s in slices])

    @staticmethod
    def parse_tables(section):
        tables={}
        for key in ('cl','cd'):
                table=section[key]
                alpha, mach, values = (np.asarray(table[name], dtype=float) for name in ('alpha_deg', 'mach', 'values'))
                if (len(alpha) < 2 or len(mach) < 2 or values.shape != (len(alpha), len(mach)) or
                    not all(np.isfinite(array).all() for array in (alpha, mach, values)) or
                    not (np.diff(alpha) > 0).all() or not (np.diff(mach) > 0).all() or
                    mach[0] < 0 or alpha[0] >= 0 or alpha[-1] <= 0 or (key == 'cd' and (values < 0).any())):
                    raise ValueError('Invalid CL/CD table dimensions, domain, ordering or drag.')
                outer=table.get('outer_alpha')
                if outer is not None:
                    oa,ov=(np.asarray(outer[k],dtype=float) for k in ('alpha_deg','values'))
                    if (oa.ndim!=1 or ov.shape!=oa.shape or len(oa)<2 or not np.isfinite([oa,ov]).all() or
                        np.any(np.diff(oa)<=0) or oa[0]>alpha[0] or oa[-1]<alpha[-1] or
                        (key=='cd' and np.any(ov<0))):raise ValueError('Invalid full-angle branch.')
                    outer=(oa,ov)
                tables[key] = alpha, mach, values,outer
        return tables

    @classmethod
    def read(cls, path):
        try:
            return cls(json.loads(Path(path).read_text(encoding='utf-8-sig')))
        except (KeyError, TypeError, IndexError) as error:
            raise ValueError('Incomplete spanwise airfoil database.') from error

    def coefficients(self, span, alpha, mach, *, reynolds=None, strict=False):
        span, alpha, mach = np.broadcast_arrays(span, alpha, mach)
        if not all(np.isfinite(value).all() for value in (span, alpha, mach)):
            raise ValueError('Non-finite airfoil lookup coordinate.')
        weights = [np.interp(span, self.span, np.eye(len(self.span))[index]) for index in range(len(self.span))]
        if self.data['schema_version']==2:
            if reynolds is None:raise ValueError('Reynolds-dependent airfoils require local Reynolds number.')
            reynolds=np.broadcast_to(np.asarray(reynolds,dtype=float),alpha.shape)
            if not np.isfinite(reynolds).all() or np.any(reynolds<=0):raise ValueError('Reynolds number must be positive and finite.')
        outputs = []
        for key in ('cl', 'cd'):
            output = np.zeros_like(alpha, dtype=float)
            for slices, nodes,span_weight in zip(self.tables,self.reynolds,weights):
              if len(nodes)>1:
                if strict and np.any((span_weight>1e-12)&((reynolds<nodes[0])|(reynolds>nodes[-1]))):raise ValueError('Element outside Reynolds table domain.')
                re_weights=[np.interp(np.log(reynolds),np.log(nodes),np.eye(len(nodes))[i]) for i in range(len(nodes))]
              else:re_weights=[1.]
              for section,rw in zip(slices,re_weights):
                weight=span_weight*rw;aa,mm,zz,outer=section[key];active=weight>1e-12
                amin,amax=(aa[0],aa[-1]) if outer is None else (outer[0][0],outer[0][-1])
                if strict and np.any(active & ((alpha < amin) | (alpha > amax) | (mach < mm[0]) | (mach > mm[-1]))):
                    raise ValueError(f'Converged element lies outside the {key.upper()} alpha/Mach table domain.')
                # Root search may visit invalid trial states; final states are checked strictly.
                a, m = np.clip(alpha, aa[0], aa[-1]), np.clip(mach, mm[0], mm[-1])
                i = np.clip(np.searchsorted(aa, a)-1, 0, len(aa)-2)
                j = np.clip(np.searchsorted(mm, m)-1, 0, len(mm)-2)
                wa, wm = (a-aa[i])/(aa[i+1]-aa[i]), (m-mm[j])/(mm[j+1]-mm[j])
                value = (1-wa)*((1-wm)*zz[i,j]+wm*zz[i,j+1])+wa*((1-wm)*zz[i+1,j]+wm*zz[i+1,j+1])
                if outer is not None:value=np.where((alpha<aa[0])|(alpha>aa[-1]),np.interp(alpha,*outer),value)
                output += weight*value
            outputs.append(output)
        return tuple(outputs)
