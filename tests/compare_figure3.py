"""Digitize the vector paths on p. 11 of Saetti & Horn (AIAA 2022-2354)."""

import argparse
import csv
from hashlib import sha256
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pymupdf

# PDF coordinates in points. The x-axis is log10(omega), with the first and
# third major ticks at 0.1 and 1 rad/s. Each y-axis uses two printed ticks.
# Panel records are (paths, tick 1, tick 2); a tick is (PDF y, axis value).
PANELS = {
    "p_lateral": ((94.70448, 147.60294), (
        ((83, 85), (85.0034, 0), (137.6846, -50)),
        ((226, 228), (152.8499, 0), (194.2711, -300)),
        ((324,), (219.0741, 1), (269.0753, 0)),
    ), 0.1),
    "q_longitudinal": ((249.14549, 302.04395), (
        ((418, 420), (88.9502, -10), (133.8102, -70)),
        ((493, 495), (152.8486, 0), (194.2673, -300)),
        ((591,), (218.4935, 1), (269.9776, 0)),
    ), 0.1),
    "r_pedal": ((403.58548, 456.48394), (
        ((673, 675), (91.3622, 0), (129.9159, -40)),
        ((748, 750), (152.8458, 0), (194.2779, -300)),
        ((841,), (227.6675, 0.8), (268.9963, 0)),
    ), 0.0538),
}
COLORS = ((0.804, 0.2, 0.2), (0.706, 0.322, 0.804))
MODES = ("legacy", "corrected")
METHODS = ("fixed_azimuth", "azimuth_average")
GRID = np.geomspace(0.1, 30, 301)
SAMPLE = np.unique(np.r_[GRID, 0.2, 0.3, 1, 4, 10, 20])
SOURCE_SHA256 = "8f1d413b482470ed38267a91002f93c7d6e9183797e4704823c68683d7e9ec94"


def path_xy(drawing, x_ticks, tick1, tick2):
    items = drawing["items"]
    if any(item[0] != "l" for item in items):
        raise ValueError("Expected a piecewise linear Figure 3 path")
    segments = np.array([[(p.x, p.y) for p in item[1:]] for item in items])
    points = segments.reshape(-1, 2)
    if np.min(np.diff(points[:, 0])) < -0.001:
        raise ValueError("Figure 3 path x coordinates must be monotone")
    # A vertical PDF segment connects the two ends of a wrapped phase curve.
    # Keeping both ends lets unwrapping remove that 360-degree discontinuity.
    log_f = -1 + (points[:, 0] - x_ticks[0]) / (x_ticks[1] - x_ticks[0])
    y1, v1 = tick1
    y2, v2 = tick2
    value = v1 + (points[:, 1] - y1) * (v2 - v1) / (y2 - y1)
    return log_f, value


def interpolate(x, y, phase=False):
    if phase:
        y = np.rad2deg(np.unwrap(np.deg2rad(y)))
    query = np.log10(SAMPLE)
    # PDF coordinate rounding can put a printed endpoint a few ten-thousandths
    # of a decade inside the axis. Snap within that tolerance.
    query = np.where(np.abs(query - x[0]) < 0.0002, x[0], query)
    query = np.where(np.abs(query - x[-1]) < 0.0002, x[-1], query)
    return np.interp(query, x, y, left=np.nan, right=np.nan)


def figure_values(pdf):
    if sha256(pdf.read_bytes()).hexdigest() != SOURCE_SHA256:
        raise ValueError("The supplied PDF differs from the calibrated edition")
    with pymupdf.open(pdf) as doc:
        page = doc[10]
        if "On-axis frequency responses comparison" not in page.get_text():
            raise ValueError("Expected Figure 3 on page 11")
        drawings = {drawing["seqno"]: drawing for drawing in page.get_drawings()}
    for channel, (x_ticks, panels, _) in PANELS.items():
        values = {}
        for quantity, (paths, tick1, tick2) in zip(("magnitude", "phase", "coherence"), panels):
            names = ("full_order", "flight") if len(paths) == 2 else ("flight",)
            for path, name in zip(paths, names):
                drawing = drawings[path]
                color = COLORS[name == "flight"]
                if len(drawing["items"]) < 800 or not np.allclose(drawing["color"], color, atol=0.001):
                    raise ValueError(f"Unexpected path {path} for {channel} {name} {quantity}")
                x, y = path_xy(drawing, x_ticks, tick1, tick2)
                values[f"{name}_{quantity}"] = interpolate(x, y, phase=quantity == "phase")
        yield channel, values


def responses(directory, method, matrices):
    a, b = (np.loadtxt(directory / f"{method}_{key}.csv", delimiter=",", skiprows=1,
                       usecols=range(1, size + 1)) for key, size in zip(matrices, (37, 4)))
    systems = 1j * SAMPLE[:, None, None] * np.eye(37) - a
    return np.linalg.solve(systems, np.broadcast_to(b, (len(SAMPLE), 37, 4)))


def wrap(phase):
    return (phase + 180) % 360 - 180


def broken_at_wrap(phase):
    values = phase.copy()
    values[1:][np.abs(np.diff(phase)) > 180] = np.nan
    return values


def metrics(error, mask):
    available = error[mask & np.isfinite(error)]
    return dict(n=len(available), mean=float(available.mean()),
                rms=float(np.sqrt(np.mean(available**2))),
                max_abs=float(np.max(np.abs(available))))


def write_rows(path, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def compare(pdf, runs, output):
    rows, stats = [], []
    models = {f"{mode}_{method}": responses(runs / mode, method, ("A", "B"))
              for mode in MODES for method in METHODS}
    models["legacy_main_FG"] = responses(runs / "legacy", "fixed_azimuth", ("F", "G"))
    figure, axes = plt.subplots(3, 3, figsize=(12, 7.8), sharex=True, layout="constrained")
    for column, (channel, values) in enumerate(figure_values(pdf)):
        full_db, full_phase = values["full_order_magnitude"], values["full_order_phase"]
        flight_db, flight_phase = values["flight_magnitude"], values["flight_phase"]
        coherence = values["flight_coherence"]
        # Exclude extra report frequencies from log-uniform aggregate statistics.
        uniform = np.isin(SAMPLE, GRID)
        bands = {"overlap": uniform,
                 "0.1-0.5": uniform & (SAMPLE < .5),
                 "0.5-10": uniform & (SAMPLE >= .5) & (SAMPLE <= 10)}
        for threshold in (.6, .8):
            bands[f"coherence>={threshold}"] = uniform & (coherence >= threshold)
        for name, response in models.items():
            value = response[:, 3 + column, (0, 1, 3)[column]] / PANELS[channel][2]
            db, phase = 20 * np.log10(np.abs(value)), np.rad2deg(np.angle(value))
            for target, target_db, target_phase in (
                ("paper_full_order", full_db, full_phase), ("flight_test", flight_db, flight_phase),
            ):
                delta_db, delta_phase = db - target_db, wrap(phase - target_phase)
                for band, mask in bands.items():
                    stats.append(dict(channel=channel, model=name, target=target, band=band,
                                      magnitude=metrics(delta_db, mask), phase=metrics(delta_phase, mask)))
                for w, m, p, c, tm, tp, dm, dp in zip(
                    SAMPLE, db, phase, coherence, target_db, target_phase, delta_db, delta_phase
                ):
                    if np.isfinite([m, p, tm, tp]).all():
                        rows.append(dict(channel=channel, model=name, target=target,
                                         omega_rad_s=w, model_db=m, model_phase_deg=wrap(p),
                                         reference_db=tm, reference_phase_deg=wrap(tp),
                                         delta_db=dm, delta_phase_deg=dp,
                                         flight_coherence=c if np.isfinite(c) else ""))
            if name.startswith("corrected"):
                fixed = name.endswith("fixed_azimuth")
                label = "Local fixed azimuth" if fixed else "Local azimuth average"
                style = "-" if fixed else ":"
                axes[0, column].plot(SAMPLE, db, style, label=label)
                axes[1, column].plot(SAMPLE, broken_at_wrap(wrap(phase - full_phase)), style)
        axes[0, column].plot(SAMPLE, full_db, "--", color="#b52530", label="Paper J-GenHel full order")
        axes[0, column].plot(SAMPLE, flight_db, "-", color="#9a54b3", alpha=.75, label="RASCAL flight")
        axes[1, column].plot(SAMPLE, broken_at_wrap(wrap(flight_phase - full_phase)),
                             "-", color="#9a54b3", alpha=.75)
        axes[2, column].plot(SAMPLE, coherence, color="#9a54b3")
        axes[2, column].axhline(.6, color="0.5", linestyle="--", linewidth=.8)
        axes[2, column].set_ylim(0, 1.05)
        axes[0, column].set_title(channel.replace("_", " / "))
        axes[2, column].set_xlabel("Frequency (rad/s)")
        for ax in axes[:, column]:
            ax.set_xscale("log")
            ax.set_xlim(.1, 30)
            ax.grid(alpha=.2)
    axes[0, 0].set_ylabel("Magnitude [dB, rad/s per in]")
    axes[1, 0].set_ylabel("Phase relative to paper model [deg]")
    axes[2, 0].set_ylabel("Flight coherence")
    axes[0, 0].legend(fontsize=7, loc="lower left")
    figure.suptitle("UH-60 at 80 kt | AIAA 2022-2354 Figure 3")
    output.mkdir(parents=True, exist_ok=True)
    figure.savefig(output / "figure3-comparison.png", dpi=180)
    plt.close(figure)
    write_rows(output / "figure3-comparison.csv", rows)
    (output / "figure3-metrics.json").write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("runs", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    compare(args.pdf, args.runs, args.output)
