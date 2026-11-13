"""Replay the original four-blade airload equations with frozen local kinematics."""

from pathlib import Path

import numpy as np
from scipy.interpolate import RegularGridInterpolator
from scipy.io import loadmat

from .uh60 import ROOT


def compare_trace(path: Path):
    data = np.genfromtxt(path, delimiter=",", names=True)
    tables = loadmat(ROOT / "data" / "GHRotorData.mat")
    sb, cb = data["sin_flap"], data["cos_flap"]
    mx, my, mz = data["mux"], data["muy"], data["muz"]
    cc, ss = data["cos_az_lag"], data["sin_az_lag"]
    ca, sa = data["cos_az"], data["sin_az"]
    ps, qs = data["ps"], data["qs"]
    h, r, omega = data["hinge_ratio"], data["rseg"], data["omega_rad_s"]
    rate = data["rminusomega"]
    cos_lag = cc * ca + ss * sa
    sin_lag = ss * ca - cc * sa
    inflow = -(data["inflow_mean"] + data["inflow_cos"] * (h * ca + r * cc)
               + data["inflow_sin"] * (h * sa + r * ss))
    up = (-mx*sb*cc + my*sb*ss + mz*cb
          + h/omega * (cb*(qs*ca + ps*sa) - sb*sin_lag*rate)
          + r/omega * (-data["flap_rate"] + qs*cc + ps*ss) + inflow*cb)
    ut = (mx*ss + my*cc - h/omega*cos_lag*rate
          + r/omega * ((data["lag_rate"] - rate)*cb + (ps*cc - qs*ss)*sb))
    ur = (mx*cb*cc - my*cb*ss + mz*sb
          + h/omega * (sb*(qs*ca + ps*sa) + cb*sin_lag*rate)
          + inflow*sb)
    skew = np.abs(ut) / np.hypot(ut, ur)
    pitch_term = np.tan(data["theta_rad"])
    alpha = np.rad2deg(np.arctan2((ut * pitch_term + up) * skew, ut - up * pitch_term * skew**2))
    mach = np.hypot(up, ut) * data["omega_rad_s"] * data["radius_ft"] / data["sound_ft_s"]
    a0 = skew * alpha
    low = (alpha + 180) * skew - 180
    high = 180 + (alpha - 180) * skew
    a1 = ((1 - 11/90) * a0 - 11*(1-skew)) / (skew - 11/90)
    a2 = ((1 - 172/90) * high + 172*(1-skew)) / (2 - 172/90 - skew)
    a3 = ((1 - 5/90) * a0 + 5*(1-skew)) / (skew - 5/90)
    a4 = ((1 - 172/90) * low + 172*(1-skew)) / (2 - 172/90 - skew)
    lift_angle = (
        a0 * ((a0 <= 11) & (a0 >= -5) & (abs(alpha) < 90))
        + a1 * ((a0 > 11) & (alpha < 90))
        + np.where(high < 172, a2, high) * (alpha >= 90)
        + a3 * ((a0 < -5) & (alpha >= -90))
        + np.where(low > -172, a4, low) * (alpha < -90)
    )

    def coefficient(angle, bounded, full):
        axes = (np.arange(-32, 33, 2), np.linspace(0, 1, 11))
        values = tables[bounded].reshape((33, 11), order="F")
        query = np.column_stack((np.clip(angle, -32, 32), np.clip(mach, 0, 1)))
        inner = RegularGridInterpolator(axes, values)(query)
        outer = np.interp(angle, np.arange(-180, 181, 2), tables[full].ravel(order="F"))
        return np.where(np.abs(angle) <= 32, inner, outer)

    cl = coefficient(lift_angle, "CLR0BT", "CLR0UT")
    cd = coefficient(alpha, "CDR0BT", "CDR0UT") + 0.002
    factor = (0.5 * data["density_slug_ft3"] * data["omega_rad_s"]**2 * data["radius_ft"]**3
              * data["chord_ft"] * data["delseg"] * np.sqrt(up**2 + ut**2 + ur**2))
    fp = factor * (cl * ut / skew + cd * up)
    ft = factor * (cd * ut - cl * up * skew)
    fr = factor * (cd - cl * up * skew / ut) * ur
    fz = (-fr * data["sin_flap"] - fp * data["cos_flap"]).reshape(4, 10).sum(axis=1)
    expected = {
        "up": (up, data["up"]), "ut": (ut, data["ut"]), "ur": (ur, data["ur"]),
        "alpha_deg": (alpha, data["alpha_deg"]), "lookup_alpha_deg": (lift_angle, data["lookup_alpha_deg"]),
        "mach": (mach, data["mach"]), "cl": (cl, data["cl"]), "cd": (cd, data["cd"]),
        "fp_lbf": (fp, data["fp_lbf"]), "ft_lbf": (ft, data["ft_lbf"]), "fr_lbf": (fr, data["fr_lbf"]),
        "fz_lbf": (fz, data["fz_lbf"].reshape(4, 10)[:, 0]),
        "thrust_lbf": (-fz.sum(), data["thrust_lbf"][0]),
    }
    for name, (value, target) in expected.items():
        np.testing.assert_allclose(value, target, rtol=1e-10, atol=1e-9, err_msg=name)
    return {name: float(np.max(np.abs(value - target))) for name, (value, target) in expected.items()}
