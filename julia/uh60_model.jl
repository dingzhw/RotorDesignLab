using Interpolations, LinearAlgebra, Printf

VERSION == v"1.12.4" || error("This reference requires Julia 1.12.4 (found $VERSION)")

# The adapter reads the numeric MAT tables exported by SciPy in their original
# two-dimensional shape. This keeps MAT and plotting packages out of the solver.
const ROOT = dirname(@__DIR__)
struct NumericMat
    directory::String
end
matopen(path) = NumericMat(joinpath(ARGS[1], basename(path)))
Base.read(file::NumericMat, key::String) =
    reduce(vcat, permutedims.(map(line -> parse.(Float64, split(line, ',')),
                                readlines(joinpath(file.directory, key * ".csv")))))
Base.close(::NumericMat) = nothing

for name in ("control_mixing", "table_lookup", "stabSched", "atan2", "eqnmot",
             "interpp1", "interpp2", "linearize", "trimmer", "GenHel", "H60_constants")
    include(joinpath(ROOT, "src", name * ".jl"))
end

VXTRIM, VYTRIM, VZTRIM = 80 * 1.688, 0.0, 0.0
PSIDTRIM, PSITRIM, ALTTRIM, XNTRIM, YETRIM = zeros(5)
include(joinpath(ROOT, "src", "trimInit.jl"))
