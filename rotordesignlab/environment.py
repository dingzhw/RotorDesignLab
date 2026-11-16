"""Dry-air engineering environment; old calls keep their exact ISA constants."""
from math import isfinite, sqrt

AIR_FIELDS = ('density_kg_m3', 'speed_of_sound_m_s', 'dynamic_viscosity_pa_s')


def finite(value, name, lower, upper):
    if type(value) not in (float, int) or not isfinite(value) or not lower <= value <= upper:
        raise ValueError(f'{name}须为{lower:g}至{upper:g}的有限数值。')
    return value


def standard(altitude, offset=0.):
    altitude = finite(altitude, '气压高度 / m', 0, 11000)
    offset = finite(offset, 'ISA温差 / K', -60, 60)
    reference = 288.15 - .0065 * altitude
    temperature = reference + offset
    pressure = 101325 * (reference / 288.15)**(9.80665 / (287.05287 * .0065))
    return dict(temperature_k=temperature, pressure_pa=pressure,
                density_kg_m3=pressure / (287.05287 * temperature),
                speed_of_sound_m_s=sqrt(1.4 * 287.05287 * temperature),
                dynamic_viscosity_pa_s=1.716e-5 * (temperature / 273.15)**1.5 * (273.15 + 110.4) / (temperature + 110.4))


def from_case(case):
    env = case.get('environment', {'mode': 'isa', 'isa_temperature_offset_k': 0.})
    if not isinstance(env, dict):
        raise ValueError('环境设置需要包含mode的对象。')
    if env.get('mode') == 'isa':
        if set(env) - {'mode', 'isa_temperature_offset_k'}:
            raise ValueError('ISA环境只接受温差；密度、声速、黏度由高度与温度联动。')
        return standard(case.get('altitude_m', 0.), env.get('isa_temperature_offset_k', 0.))
    if env.get('mode') == 'custom':
        if set(env) != {'mode', *AIR_FIELDS}:
            raise ValueError('自定义环境需完整填写密度、声速、动力黏度。')
        ranges = ((.05, 3), (250, 400), (1e-6, 1e-3))
        labels = ('密度 / (kg/m³)', '声速 / (m/s)', '动力黏度 / (Pa·s)')
        return {key: finite(env[key], label, *bounds) for key, label, bounds in zip(AIR_FIELDS, labels, ranges)}
    raise ValueError('环境模式请选择isa或custom。')
