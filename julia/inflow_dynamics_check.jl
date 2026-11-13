# Frozen-flow PP derivative, original GenHel ciao coefficients [75pi/128,45pi/16,45pi/16].
using LinearAlgebra, DelimitedFiles
points=[0. 0. 0. .008 .0 .0 .05 .001 -.002 27.;.1 .03 .01 .008 .0001 -.0002 .04 .003 .001 30.;.25 -.02 .02 .006 -.0001 .0002 .02 .001 -.003 124.62]
rows=zeros(3,13)
for i=1:3
    ux,uy,uz,ct,gc,gs,l0,lc,ls,omega=points[i,:]
    mu=hypot(ux,uy);lo=0.;hi=1.
    for j=1:100
        mid=(lo+hi)/2
        if 2mid*hypot(mu,mid+uz)>ct;hi=mid;else;lo=mid;end
    end
    li=(lo+hi)/2;vt=hypot(mu,li+uz);vm=(mu^2+(li+uz)*(2li+uz))/vt
    x=tan(atan(mu,li+uz)/2);L=[.5 15pi/64*x 0.;-15pi/64*x 2(1-x*x) 0.;0. 0. 2(1+x*x)]
    angle=mu==0 ? 0. : atan(uy,ux);R=[1. 0. 0.;0. cos(angle) sin(angle);0. -sin(angle) cos(angle)]
    f=R*[ct,gc,gs];state=R*[l0,lc,ls]
    d=R'*(omega*Diagonal([75pi/128,45pi/16,45pi/16])*(f-L\(Diagonal([vt,vm,vm])*state)))
    rows[i,:]=[points[i,:]...,d...]
end
writedlm(ARGS[1],vcat(permutedims(["ux","uy","uz","ct","gc","gs","l0","lc","ls","omega","d0","dc","ds"]),rows),',')
