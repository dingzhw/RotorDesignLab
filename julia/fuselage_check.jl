# Independent original GenHel fuselage equations, imperial inputs.
using DelimitedFiles, LinearAlgebra
source, output = ARGS
data = readdlm(joinpath(source,"fuselage-source.csv"),',',Float64;skipstart=1)
function tab(group, column, angle)
    rows=data[data[:,1].==group,:];x=rows[:,2];y=rows[:,column]
    i=clamp(searchsortedlast(x,angle),1,length(x)-1)
    a=clamp(angle,x[1],x[end]);y[i]+(a-x[i])*(y[i+1]-y[i])/(x[i+1]-x[i])
end
points=[20. 0 2;30. 3 -4;10. -2 5]
answer=zeros(3,9)
for i=1:3
    u,v,w=points[i,:]./0.3048;rho=1.225/(14.59390294/0.3048^3)
    a=atan(w/max(abs(u),1e-6))*180/pi
    plane=max(u^2+w^2,1e-6);c=u/sqrt(plane);s=w/sqrt(plane)
    b=atan(v/sqrt(plane));q=0.5*rho*(v^2+plane)
    T=[c*cos(b) c*sin(b) -s;sin(b) -cos(b) 0;s*cos(b) s*sin(b) c]
    cd=tab(1,3,a)+tab(3,3,abs(b*180/pi))
    cl=tab(1,4,a)+tab(2,4,-b*180/pi);cy=tab(2,3,-b*180/pi)
    cm=tab(1,5,a)+tab(3,5,abs(b*180/pi))
    cr=tab(2,5,-b*180/pi);cn=tab(2,6,-b*180/pi)
    force=T*(-q*[cd,cy,cl])
    # Reference CG FS360.4/WL247.2, fuselage FS345.5/WL234.
    arm=[(360.4-345.5)/12,0,(247.2-234)/12]
    moment=T*(q*[cr,-cm,cn])+cross(arm,force)
    answer[i,:]=[points[i,:]...,(force.*(14.59390294*.3048))...,(moment.*(14.59390294*.3048^2))...]
end
writedlm(output,vcat(permutedims(["u","v","w","fx","fy","fz","mx","my","mz"]),answer),',')
