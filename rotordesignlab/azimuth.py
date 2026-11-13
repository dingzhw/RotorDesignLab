"""Rigid blade elements in a right-handed rotor frame: z is positive thrust.

psi is measured geometrically from +x toward +y; dpsi/dt = sign * Omega.
Pitch/flap harmonics are [constant, cos(psi), sin(psi)], in radians.
Velocities are aircraft relative to still air, expressed in this frame.
"""
from dataclasses import dataclass
from math import pi
import numpy as np


@dataclass
class AzimuthRotor:
    rotor: object
    azimuth_stations: int = 36
    rotation_sign: int = 1
    hinge_offset_m: float = 0.
    pitch_flap_coupling: float = 0.

    def __post_init__(self):
        if type(self.azimuth_stations) is not int or not 12 <= self.azimuth_stations <= 720:
            raise ValueError('方位角站数必须为12–720的整数。')
        if self.rotation_sign not in (-1,1) or type(self.rotation_sign) is not int:
            raise ValueError('旋转符号必须为±1。')
        r,dr,chord,pitch=self.rotor.grid()
        if not 0 <= self.hinge_offset_m < self.rotor.geometry[0,0]*self.rotor.radius:
            raise ValueError('挥舞铰偏置必须在有效气动根部以内。')
        self.r,self.dr,self.chord=r,dr,chord
        self.twist=pitch-np.deg2rad(self.rotor.collective_deg)
        self.psi=np.arange(self.azimuth_stations)*2*pi/self.azimuth_stations
        self.harmonics=np.array([np.ones_like(self.psi),np.cos(self.psi),np.sin(self.psi)]).T
        self.er=np.column_stack((np.cos(self.psi),np.sin(self.psi),np.zeros_like(self.psi)))
        self.et=self.rotation_sign*np.column_stack((-np.sin(self.psi),np.cos(self.psi),np.zeros_like(self.psi)))

    def elements(self, controls, inflow, flap, velocity, *, strict=True, body_rates=(0,0,0)):
        """Return revolution-mean loads plus per-blade element diagnostics.

        No spanwise aerodynamic force, swirl, elastic twist or tip correction.
        Blade motion includes first-harmonic flap velocity, not a tilted-disk shortcut.
        """
        controls,inflow,flap,velocity=(np.asarray(v,dtype=float) for v in (controls,inflow,flap,velocity))
        if any(v.shape!=(3,) or not np.isfinite(v).all() for v in (controls,inflow,flap,velocity)):
            raise ValueError('旋翼操纵/入流/挥舞/速度均需三个有限数。')
        model=self.rotor;omega=model.omega;h=self.hinge_offset_m
        beta=self.harmonics@flap
        beta_dot=self.rotation_sign*omega*(-flap[1]*np.sin(self.psi)+flap[2]*np.cos(self.psi))
        beta_ddot=-omega**2*(flap[1]*np.cos(self.psi)+flap[2]*np.sin(self.psi))
        cb,sb=np.cos(beta),np.sin(beta)
        normal=-sb[:,None]*self.er;normal[:,2]=cb
        arm=h+cb[:,None]*(self.r-h)
        position=arm[:,:,None]*self.er[:,None,:]
        position[:,:,2]=sb[:,None]*(self.r-h)
        induced=omega*model.radius*(inflow[0]+inflow[1]*position[:,:,0]/model.radius+inflow[2]*position[:,:,1]/model.radius)
        relative=np.broadcast_to(velocity,position.shape).copy()
        relative+=np.cross(np.asarray(body_rates),position)
        relative+=omega*arm[:,:,None]*self.et[:,None,:]
        relative+=beta_dot[:,None,None]*(self.r-h)[None,:,None]*normal[:,None,:]
        relative[:,:,2]+=induced
        ut=np.einsum('ijk,ik->ij',relative,self.et)
        up=np.einsum('ijk,ik->ij',relative,normal)
        phi=np.arctan2(up,ut)
        pitch=(self.harmonics@controls)[:,None]+self.twist-self.pitch_flap_coupling*beta[:,None]
        alpha=(np.rad2deg(pitch-phi)+180)%360-180
        speed=np.hypot(ut,up);mach=speed/model.speed_of_sound
        if model.airfoil_grid is not None:
            cl,cd=model.airfoil_grid.coefficients(self.r/model.radius,alpha,mach,
                reynolds=model.density*speed*self.chord/model.dynamic_viscosity,strict=strict)
        else:
            if strict and (alpha.min()<model.polar[0,0] or alpha.max()>model.polar[-1,0]):
                raise ValueError('方位角叶素攻角超出翼型表；回流区需要四象限数据，禁止端点外推。')
            cl=np.interp(alpha,model.polar[:,0],model.polar[:,1])
            cd=np.interp(alpha,model.polar[:,0],model.polar[:,2])
        scale=.5*model.density*speed**2*self.chord*self.dr
        normal_force=scale*(cl*np.cos(phi)-cd*np.sin(phi))
        tangent_force=scale*(cl*np.sin(phi)+cd*np.cos(phi))
        force=normal_force[:,:,None]*normal[:,None,:]-tangent_force[:,:,None]*self.et[:,None,:]
        moment=np.cross(position,force)
        mean=lambda value:model.blades*np.mean(np.sum(value,axis=1),axis=0)
        F,M=mean(force),mean(moment)
        Q=-self.rotation_sign*M[2]
        return dict(force=F,moment=M,torque=float(Q),power=float(omega*Q),
            flap_moment=np.sum(normal_force*(self.r-h),axis=1),
            beta=beta,beta_dot=beta_dot,beta_ddot=beta_ddot,normal=normal,
            position=position,element_force=force,ut=ut,up=up,alpha_deg=alpha,mach=mach,
            cl=cl,cd=cd,induced_m_s=induced,pitch_deg=np.rad2deg(pitch),
            pressure_moments=np.array([mean(position[:,:,0]*force[:,:,2]),mean(position[:,:,1]*force[:,:,2])]),
            reverse_flow_fraction=float(np.mean(ut<0)))


def rotor_basis(axis, x_reference):
    """Columns transform rotor coordinates to body coordinates."""
    z=np.asarray(axis,dtype=float);ref=np.asarray(x_reference,dtype=float)
    if z.shape!=(3,) or ref.shape!=(3,) or not np.isfinite([z,ref]).all() or not np.isclose(np.linalg.norm(z),1,atol=1e-8,rtol=0):
        raise ValueError('旋翼轴须为有限单位向量，方位参考须为有限三维向量。')
    x=ref-z*np.dot(ref,z)
    if np.linalg.norm(x)<1e-8:raise ValueError('方位参考不能平行于旋翼轴。')
    x/=np.linalg.norm(x);y=np.cross(z,x)
    return np.column_stack((x,y,z))
