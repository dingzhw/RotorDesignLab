function azimuth_average(rhs, derivative, state, controls, time)
    sample = copy(state)
    result = zeros(length(state))
    for index in 0:(NAZTRIM - 1)
        sample[IDXAZ] = state[IDXAZ] + index * 2pi / (NB * NAZTRIM)
        result .+= rhs(derivative, sample, controls, time) ./ NAZTRIM
    end
    return result
end

# Only the six rigid-body acceleration inputs feed back into GenHel!.
# Recompute them at each RK stage and check the implicit equation residual.
function coupled_rhs(rhs, state, controls, time, initial, count=6)
    guess = copy(initial)
    indices = 1:count
    for _ in 1:10
        value = rhs(guess, state, controls, time)
        all(isfinite, value) || error("Non-finite derivative at t=$time")
        residual = value[indices] - guess[indices]
        if norm(residual, Inf) <= 1e-10 * max(1.0, norm(value[indices], Inf))
            return value
        end
        matrix = Matrix{Float64}(I, count, count)
        for index in indices
            step = 1e-4 * max(1.0, abs(guess[index]))
            guess[index] += step
            trial = rhs(guess, state, controls, time)
            guess[index] -= step
            matrix[:, index] .-= (trial[indices] - value[indices]) / step
        end
        guess[indices] += matrix \ residual
    end
    error("Acceleration coupling did not converge at t=$time")
end

function open_loop(rhs, x, u, derivative, duration, step)
    # Smooth lateral pulse permits a step refinement check without an input
    # discontinuity at a Runge–Kutta stage boundary.
    function stage(state, time, seed)
        command = copy(u)
        command[1] += 2.0 * sinpi(time / duration)^2
        return coupled_rhs(rhs, state, command, time, seed)
    end
    times = range(0.0, duration; step)
    states = Matrix{Float64}(undef, length(times), length(x))
    states[1, :] = x
    for i in 1:(length(times) - 1)
        t = times[i]
        k1 = stage(x, t, derivative)
        k2 = stage(x + step/2*k1, t + step/2, k1)
        k3 = stage(x + step/2*k2, t + step/2, k2)
        k4 = stage(x + step*k3, t + step, k3)
        x = x + step/6*(k1 + 2*k2 + 2*k3 + k4)
        states[i+1, :] = x
        derivative = k4
    end
    return collect(times), states
end
