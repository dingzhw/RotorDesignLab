include("uh60_model.jl")
include("uh60_numerics.jl")

const STATE_NAMES = [
    "u_ft_s", "v_ft_s", "w_ft_s", "p_rad_s", "q_rad_s", "r_rad_s",
    "roll_rad", "pitch_rad", "heading_rad", "north_ft", "east_ft", "down_ft",
    ["flap_" * mode * "_rad" for mode in ("mean", "alternating", "cos", "sin")]...,
    ["flap_" * mode * "_rad_s" for mode in ("mean", "alternating", "cos", "sin")]...,
    ["lag_" * mode * "_rad" for mode in ("mean", "alternating", "cos", "sin")]...,
    ["lag_" * mode * "_rad_s" for mode in ("mean", "alternating", "cos", "sin")]...,
    "inflow_mean", "inflow_sin", "inflow_cos", "azimuth_rad", "twist_filter_lbf",
    "wake_skew", "wake_curvature_cos", "wake_curvature_sin", "tail_inflow",
]
const CONTROL_NAMES = ["lateral_pct", "longitudinal_pct", "collective_pct", "pedal_pct"]

function write_csv(path, labels, rows)
    open(path, "w") do file
        println(file, join(labels, ','))
        for row in rows
            println(file, join(row, ','))
        end
    end
end

function write_linearization(directory, label, rhs, x, u, derivative)
    matrices = linearize(rhs, x, u, derivative, 0.0)
    for (name, matrix) in zip(("F", "G", "M", "A", "B"), matrices)
        labels = name in ("G", "B") ? CONTROL_NAMES : STATE_NAMES
        write_csv(joinpath(directory, "$(label)_$(name).csv"),
                  ["state", labels...], ([state, row...] for (state, row) in
                                          zip(STATE_NAMES, eachrow(matrix))))
    end
    return matrices[4:5]
end

function write_frequency(directory, label, A, B)
    frequencies = 10.0 .^ range(-1, log10(30); length=181)
    channels = (("p_lateral", 4, 1), ("q_longitudinal", 5, 2), ("r_pedal", 6, 4))
    rows = Vector{Float64}[]
    phase_previous = zeros(3)
    for (i, frequency) in enumerate(frequencies)
        response = (im*frequency*I - A) \ B
        row = [frequency]
        for (j, (_, output, input)) in enumerate(channels)
            value = response[output, input]
            phase = rad2deg(angle(value))
            if i > 1
                phase = phase_previous[j] + mod(phase - phase_previous[j] + 180, 360) - 180
            end
            phase_previous[j] = phase
            append!(row, (20*log10(abs(value)), phase))
        end
        push!(rows, row)
    end
    labels = ["frequency_rad_s"]
    for (name, _, _) in channels
        append!(labels, [name * "_db", name * "_phase_deg"])
    end
    write_csv(joinpath(directory, label * "_frequency.csv"), labels, rows)
end

function run_uh60(directory, mode, duration, step)
    legacy = mode == "legacy"
    rhs(dx, x, u, t) = GenHel!(dx, x, u, t; legacy_vertical=legacy)
    x, u, flag = trimmer(rhs, x0, u0, xdot_targ, 0.0)
    residuals = azimuth_average(rhs, xdot0, x, u, 0.0)[TRIMTARG] - xdot_targ
    scaled = abs.(residuals) ./ XSCALE[TRIMTARG]
    err = maximum(scaled)
    write_csv(joinpath(directory, "trim_residual.csv"), ["state", "residual", "scaled_abs"],
              zip(STATE_NAMES[TRIMTARG], residuals, scaled))
    write_csv(joinpath(directory, "trim_state.csv"), ["state", "value"], zip(STATE_NAMES, x))
    write_csv(joinpath(directory, "trim_controls.csv"), ["control", "value_pct"], zip(CONTROL_NAMES, u))
    flag == 1 && isfinite(err) && err <= 5e-4 || error("UH-60 trim failed (residual=$err)")

    average(dx, x, u, t) = azimuth_average(rhs, dx, x, u, t)
    for (label, linear_rhs) in (("fixed_azimuth", rhs), ("azimuth_average", average))
        A, B = write_linearization(directory, label, linear_rhs, x, u, xdot0)
        write_frequency(directory, label, A, B)
    end
    if legacy
        samples = []
        rhs_trace(trace) = push!(samples, trace)
        GenHel!(xdot0, x, u, 0.0; legacy_vertical=true, rotor_trace=rhs_trace)
        values = only(samples)
        labels = ["blade", "station", "up", "ut", "ur", "theta_rad", "rseg", "delseg", "chord_ft",
                  "omega_rad_s", "radius_ft", "density_slug_ft3", "sound_ft_s", "alpha_deg",
                  "lookup_alpha_deg", "mach", "cl", "cd", "fp_lbf", "ft_lbf", "fr_lbf",
                  "sin_flap", "cos_flap", "fz_lbf", "thrust_lbf", "hinge_ratio",
                  "mux", "muy", "muz", "ps", "qs", "rminusomega", "flap_rate",
                  "lag_rate", "cos_az_lag", "sin_az_lag", "cos_az", "sin_az",
                  "inflow_mean", "inflow_sin", "inflow_cos"]
        rows = ([i, j, values.Up[i,j], values.Ut[i,j], values.Ur[i,j], values.theta[i,j],
                 values.RSEG[j], values.delseg[j], values.CHORD[j], values.OMEGA, values.R,
                 values.RHO, values.VSOUND, values.alphay[i,j], values.atrans[i,j], values.Mach[i,j],
                 values.CL[i,j], values.CD[i,j], values.Fp[i,j], values.Ft[i,j], values.Fr[i,j],
                 values.sbeta[i], values.cbeta[i], values.Fza[i], values.Tha, values.e,
                 values.muxs, values.muys, values.muzs, values.ps, values.qs,
                 values.rminusO, values.beta_dot[i], values.zeta_dot[i], values.cpsizeta[i],
                 values.spsizeta[i], values.cpsi[i], values.spsi[i], values.lambda0,
                 values.lambda1s, values.lambda1c]
                for i in 1:NB for j in 1:NSEG)
        write_csv(joinpath(directory, "rotor_trace.csv"), labels, rows)
    else
        times, states = open_loop(rhs, x, u, xdot0, duration, step)
        write_csv(joinpath(directory, "open_loop.csv"), ["time_s", STATE_NAMES...],
                  ([t, row...] for (t, row) in zip(times, eachrow(states))))
    end
    @printf("Julia %s | %s | weighted trim residual %.16g\n", VERSION, mode, err)
end

run_uh60(ARGS[2], ARGS[3], parse(Float64, ARGS[4]), parse(Float64, ARGS[5]))
