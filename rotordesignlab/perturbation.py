"""One time-dependent control definition shared by both response models."""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class Perturbation:
    kind: str = 'step'
    amplitude_deg: float = .05
    start_s: float = 0.
    duration_s: float = .5

    def validate(self, window):
        if self.kind not in ('step', 'pulse', 'doublet'):
            raise ValueError('input_type须为step、pulse或doublet。')
        if not all(type(v) in (int, float) and math.isfinite(v)
                   for v in (self.amplitude_deg, self.start_s, self.duration_s, window)):
            raise ValueError('扰动幅值、起始时间、持续时间和观察窗口须为有限数值。')
        if not -2 <= self.amplitude_deg <= 2 or not 0 <= self.start_s < window or self.duration_s <= 0:
            raise ValueError('扰动幅值须在±2°内，起始时间位于观察窗口内，持续时间须大于0。')
        end = self.start_s + self.duration_s * (2 if self.kind == 'doublet' else 1)
        if self.kind != 'step' and end > window + 1e-12:
            raise ValueError('脉冲须在观察窗口内完成；双脉冲持续时间为每一段的时长。')
        return self

    def value_deg(self, time):
        phase = (time - self.start_s) / self.duration_s
        if time < self.start_s:
            return 0.
        if self.kind == 'step':
            return self.amplitude_deg
        if self.kind == 'pulse':
            return self.amplitude_deg * math.sin(math.pi * phase) ** 2 if time < self.start_s + self.duration_s else 0.
        if time < self.start_s + self.duration_s:
            return self.amplitude_deg
        return -self.amplitude_deg if time < self.start_s + 2 * self.duration_s else 0.

    def breakpoints(self):
        if self.kind == 'step':
            return [self.start_s]
        return [self.start_s, self.start_s + self.duration_s,
                *([self.start_s + 2 * self.duration_s] if self.kind == 'doublet' else [])]

    def metadata(self):
        return dict(type=self.kind, amplitude_deg=self.amplitude_deg, start_s=self.start_s,
                    duration_s=self.duration_s if self.kind != 'step' else None,
                    definition={'step': 'start后保持幅值', 'pulse': '单段sin²平滑脉冲',
                                'doublet': '等时长正负方波两段，之后归零'}[self.kind])


def from_case(case):
    """Absent waveform keys preserve historical step-at-zero semantics."""
    from .model_scope import RESPONSE_DURATION_BOUNDS
    wave = Perturbation(case.get('input_type', 'step'), case['amplitude_deg'],
                        case.get('input_start_s', 0.), case.get('input_duration_s', .5)).validate(case['duration_s'])
    if not RESPONSE_DURATION_BOUNDS[0] <= case['duration_s'] <= RESPONSE_DURATION_BOUNDS[1]:
        raise ValueError('响应时长须为0.05–10 s。')
    return wave
