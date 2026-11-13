using CCBlade

# stdin-independent CSV exchange with Python; same section radii, pitch and polar.
rows(path) = [parse.(Float64, split(line, ',')) for line in readlines(path)[2:end]]
root, radius, blades, axial, omega, density, target = parse.(Float64, ARGS[3:9])
grid, polar = rows(ARGS[1]), rows(ARGS[2])
angles, lift, drag = eachrow(reduce(hcat, polar))
function airfoil(alpha, reynolds, mach)
    degrees = clamp(rad2deg(alpha), first(angles), last(angles))
    i = min(searchsortedlast(angles, degrees), length(angles) - 1)
    weight = (degrees - angles[i]) / (angles[i+1] - angles[i])
    return lift[i] + weight*(lift[i+1]-lift[i]), drag[i] + weight*(drag[i+1]-drag[i])
end

rotor = Rotor(root, radius, Int(blades))
function loads(offset_deg)
    thrust = torque = 0.0
    for (r, c, pitch, width) in grid
        section = Section(r, c, pitch + deg2rad(offset_deg), airfoil)
        point = OperatingPoint(axial, omega * r, density, 0.0, 1.0, 1.0)
        out = solve(rotor, section, point)
        first(angles) <= rad2deg(out.alpha) <= last(angles) ||
            error("CCBlade returned an angle outside the supplied polar")
        thrust += out.Np * width
        torque += out.Tp * r * width
    end
    return blades * thrust, blades * torque
end

function match_thrust()
    lo, hi = -8.0, 8.0
    first(loads(lo)) < target < first(loads(hi)) || error("CCBlade same-thrust root not bracketed")
    for _ in 1:30
        offset = (lo + hi) / 2
        thrust, torque = loads(offset)
        abs(thrust - target) <= 1e-5 * target && return offset, thrust, torque
        if thrust < target
            lo = offset
        else
            hi = offset
        end
    end
    error("CCBlade same-thrust iteration did not converge")
end

same_thrust, same_torque = loads(0.0)
offset, matched_thrust, matched_torque = match_thrust()
open(ARGS[10], "w") do file
    println(file, "comparison,pitch_offset_deg,thrust_n,torque_nm,power_w")
    println(file, "same_collective,0.0,$same_thrust,$same_torque,$(same_torque * omega)")
    println(file, "same_thrust,$offset,$matched_thrust,$matched_torque,$(matched_torque * omega)")
end
