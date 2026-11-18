"""Generate a separately named synthetic A2 aircraft; never edit old templates."""
from copy import deepcopy
from pathlib import Path
import json
from rotordesignlab import designs
from rotordesignlab.mass_partition import MODEL


def synthetic():
    design = designs.from_template(next(iter(designs.TEMPLATES)))
    aircraft = design['aircraft']
    aircraft['id'] = 'synthetic-a2-mass-partition'
    aircraft['name'] = '200 kg 合成机 · A2质量分账与动态挥舞'
    aircraft['dynamics'] = dict(model=MODEL, mass_reference='total_at_reference_flap',
        reference_flap_deg={'main': [0., 0., 0.], 'tail': [0., 0., 0.]},
        provenance='合成验证：总质量200 kg、参考CG[0,0,0] m、总惯量diag(30,45,60) kg m²包含全部桨叶及旋转桨毂；两旋翼零锥度方位平均。不是实测机型。')
    main, tail = aircraft['rotors']
    main['blade_mass'] = dict(mass_kg=2.5, first_mass_moment_kg_m=1.5, inertia_kg_m2=1.2,
        provenance='合成两质量点：距铰0.2 m处15/14 kg，0.9 m处10/7 kg；与历史一阶/二阶矩一致。')
    tail['blade_mass'] = dict(mass_kg=.1, first_mass_moment_kg_m=.0135, inertia_kg_m2=.00219,
        provenance='合成均匀线质量：每片0.1 kg，距铰0.03至0.24 m；未采用实测资料。')
    tail['flight']['flapping'].update(first_mass_moment_kg_m=.0135, inertia_kg_m2=.00219)
    main['hub'] = dict(mass_kg=1., cg_rotor_m=[0., 0., 0.], inertia_cg_kg_m2=[[.005,0.,0.],[0.,.005,0.],[0.,0.,.008]],
                       provenance='合成轴对称旋转桨毂；质量和惯量为数值验证假设。')
    tail['hub'] = dict(mass_kg=.05, cg_rotor_m=[0., 0., 0.], inertia_cg_kg_m2=[[.0001,0.,0.],[0.,.0001,0.],[0.,0.,.00015]],
                       provenance='合成轴对称尾桨桨毂；数值验证假设。')
    return design


if __name__ == '__main__':
    destination = Path('examples/templates/a2')
    destination.mkdir(exist_ok=True)
    design = synthetic()
    for name, text in design['assets'].items():
        (destination/name).write_text(text, encoding='utf-8')
    (destination/'synthetic.json').write_text(json.dumps(design['aircraft'], ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
