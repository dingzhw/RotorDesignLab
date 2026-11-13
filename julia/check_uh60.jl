using Test, LinearAlgebra, Printf
include(joinpath(@__DIR__, "..", "src", "linearize.jl"))
include(joinpath(@__DIR__, "..", "src", "trimmer.jl"))
include("uh60_numerics.jl")

NSTATES = NCTRLS = NB = NAZTRIM = IDXAZ = 1
TRIMTARG = TRIMVARS = [1]
XSCALE = [1.0]
DELXLIN = DELCLIN = [1e-4]

@testset "Headless reference numerics" begin
    rhs(dx, x, u, t) = -x + 0.2dx + u
    F, G, M, A, B = linearize(rhs, [1.0], [0.0], [-1.25], 0.0)
    @test only(F) ≈ -1.0
    @test only(G) ≈ 1.0
    @test only(M) ≈ 0.8
    @test only(A) ≈ -1.25
    @test only(B) ≈ 1.25
    @test only(coupled_rhs(rhs, [1.0], [0.0], 0.0, [0.0], 1)) ≈ -1.25
    bad_rhs(dx, x, u, t) = [NaN]
    @test last(trimmer(bad_rhs, [0.0], [0.0], [0.0], 0.0)) == 0
end
