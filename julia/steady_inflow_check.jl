# Independent algebraic check of the PP no-curvature steady operator.
# Reordered from src/GenHel.jl: [0,s,c] -> [0,c,s], upstream +x.
using LinearAlgebra, DelimitedFiles
points = [(0.,0.,.008,.0,.0),(.1,.01,.008,.0001,-.0002),(.25,.02,.006,-.0001,.0002)]
rows = Matrix{Float64}(undef,length(points),8)
for (i,(mu,uz,ct,gc,gs)) in enumerate(points)
    lo,hi=0.,1.
    for j=1:100
        mid=(lo+hi)/2
        if 2mid*sqrt(mu^2+(mid+uz)^2)>ct;hi=mid;else;lo=mid;end
    end
    li=(lo+hi)/2;vt=hypot(mu,li+uz);vm=(mu^2+(li+uz)*(2li+uz))/vt
    x=tan(atan(mu,li+uz)/2)
    L=[.5 15pi/64*x 0.;-15pi/64*x 2(1-x*x) 0.;0. 0. 2(1+x*x)]
    states=Diagonal([vt,vm,vm])\(L*[ct,gc,gs])
    rows[i,:]=[mu,uz,ct,gc,gs,states...]
end
writedlm(ARGS[1],vcat(permutedims(["mu","uz","ct","gc","gs","lambda0","lambdac","lambdas"]),rows),',')
