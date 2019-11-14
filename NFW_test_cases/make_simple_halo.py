import os
import pdb
import scipy
import mass_conc
import numpy as np
from matplotlib import rc
from astropy import units as u
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
from astropy.cosmology import WMAP7, z_at_value
from halotools.empirical_models import NFWProfile
rc('text', usetex=True)

class simple_halo:
    def __init__(self, m200c, z, cosmo=None, sim_maxZ=200, sim_steps=500):
        """
        Class for generating test-case input files for the ray tracing modules supplied in
        the directory above. This class is constructed with a halo mass, redshift, and 
        cosmological model, and builds a HaloTools NFWProfile object. The methods provided here 
        can then populate the profile with a particle distribution realization in 3 dimensions, 
        and output the result in the form expected by the raytracing modules.
        
        Parameters
        ----------
        m200c : float
            The mass of the halo within a radius containing 200*rho_crit, in M_sun/h
        redshift : float 
            The redshift of the halo.
        c : float, optional 
            The concentration of the halo. If not given, samples from a Gaussian 
            with location and scale suggested by the M-c relation of Child+2018
        cosmo : object, optional
            An AstroPy cosmology object. Defaults to WMAP7.
        sim_maxZ : float, optional
            The maximum redshift of a hypothetical simulation run, from which to compute
            the lightcone shell equivalent to the input redshift
        sim_steps : int, optional
            The number of timesteps from sim_maxZ to z=0, from which to compute
            the lightcone shell equivalent to the input redshift
        
        Methods
        -------
        populate_halo(r)
            Uses HaloTools to generate a MonteCarlo realization of discrete tracers of the density
            profile (particles)
        output_particles():
            Writes out the particle positions generated by make_ball() to a form that is prepped 
            for input to the ray tracing modules of this package.
            """
        
        self.redshift = z
        self.m200c = m200c
        if(cosmo is None): cosmo=WMAP7
        self.cosmo = cosmo
        self.profile = NFWProfile(cosmology=self.cosmo, redshift=self.redshift, mdef = '200c')
        self.r200c = self.profile.halo_mass_to_halo_radius(self.m200c)

        # find simulation step equivalent to halo z (needed for bookkeeping by raytrace)
        a = np.linspace(1/(sim_maxZ+1), 1, sim_steps)
        zz = 1/a-1
        # -10 steps here for buffer (halo must not be at shell boundary)
        self.shell = (500 - np.searchsorted(zz, 0.3, sorter=np.argsort(zz))) - 10
         
        # these to be filled by populate_halo()
        self.profile_particles = None
        self.mpp = None

        # draw a concentration from gaussian with scale and location defined by Child+2018
        c_u, c_sig = mass_conc.child2018(m200c)
        self.c = np.random.normal(loc=c_u, scale=c_sig)


    def populate_halo(self, N=10000, rfrac=1):
        """
        Generates a 3-dimensional relization of the discreteley-sampled NFW mass distribution for
        this halo. The radial positions are obtained with the HaloTools 
        mc_generate_nfw_radial_positions module. The angular positions are drawn from a uniform 
        random distribution, the azimuthal coordiante ranging from 0 to 2pi, and the coaltitude 
        from 0 to pi.

        Parameters
        ----------
        N : int
            The number of particles to drawn
        rfac: float, optional
            Multiplier of r200c which sets the maximum scale of the population
            (concentration will be scaled as well, as c=r200c/r_s). Defaults to 1
        """
       
        # the radial positions in comoving Mpc/h
        
        r = self.profile.mc_generate_nfw_radial_positions(num_pts = N, conc = rfac*self.c, 
                                                          halo_radius = rfac*self.r200c)
        self.profile_particles = r
        self.mpp = self.m200c / N
         
        
    def output_particles(self, output_dir='./nfw_particle_realization', vis_debug=False):
        """
        Computes three dimensional quantities for particles sampled along radial dimension. Each 
        quantity is output as little-endian binary files (expected input for ray-tracing modules
        in this package). The output quantities are x, y, z, theta, phi, redshift. In 
        cartesian space, the distribution is placed at a distance along the x-axis computed as 
        the comoving distance to the haklo redshift by the input cosmology.

        Parameters
        ----------
        output_dir : string
            The desired output location for the binary files
        vis_debug : bool
            If True, display a 3d plot of the particles to be output for visual inspection
        """
       
        output_dir = '{}/Cutout{}'.format(output_dir, self.shell)
        if not os.path.exists(output_dir):
                os.makedirs(output_dir, exist_ok=True)

        r = self.profile_particles
        phi = np.random.uniform(low=0, high=np.pi*2, size = len(r))
        theta = np.random.uniform(low=0, high=np.pi, size = len(r))
        
        # the radial positions are in Mpc/h, though astropy expects Mpc, so modify the argument
        # multiply the h back through after computing
        self.halo_r = self.cosmo.comoving_distance(self.redshift).value*self.cosmo.h
        x = r *  np.sin(theta) * np.cos(phi) + self.halo_r
        y = r *  np.sin(theta) * np.sin(phi)
        z = r *  np.cos(theta)
        # now find projected positions wrt origin after pushing halo down x-axis (Mpc/h and arcsec)
        r_sky = np.linalg.norm([x,y,z], axis=0)
        theta_sky = np.arccos(z/r_sky) * 180/np.pi * 3600
        phi_sky = np.arctan(y/x) * 180/np.pi * 3600
        
        # this also expects Mpc rather than Mpc/h
        zmin = z_at_value(self.cosmo.comoving_distance, ((x.min()-0.1)*u.Mpc)/self.cosmo.h)
        zmax = z_at_value(self.cosmo.comoving_distance, ((x.max()+0.1)*u.Mpc)/self.cosmo.h)
        z_samp = np.linspace(zmin, zmax, 10)
        x_samp = self.cosmo.comoving_distance(z_samp).value
        invfunc = scipy.interpolate.interp1d(x_samp, z_samp)
        redshift = invfunc(x/self.cosmo.h)

        if(vis_debug):
            f = plt.figure(figsize=(12,6))
            ax = f.add_subplot(121, projection='3d')
            ax2 = f.add_subplot(122)

            ax.scatter(x, y, z, c='k', alpha=0.25)
            ax.set_xlabel(r'$x\>[Mpc/h]$')
            ax.set_ylabel(r'$y\>[Mpc/h]$')
            ax.set_zlabel(r'$z\>[Mpc/h]$')

            ax2.scatter(theta_sky, phi_sky, c='k', alpha=0.25)
            ax2.set_xlabel(r'$\theta\>[Mpc/h]$')
            ax2.set_ylabel(r'$\phi\>[Mpc/h]$')
            plt.show()

        # write out all to binary
        x.astype('f').tofile('{}/x.{}.bin'.format(output_dir, self.shell))
        y.astype('f').tofile('{}/y.{}.bin'.format(output_dir, self.shell))
        z.astype('f').tofile('{}/z.{}.bin'.format(output_dir, self.shell))
        theta_sky.astype('f').tofile('{}/theta.{}.bin'.format(output_dir, self.shell))
        phi_sky.astype('f').tofile('{}/phi.{}.bin'.format(output_dir, self.shell))
        redshift.astype('f').tofile('{}/redshift.{}.bin'.format(output_dir, self.shell))
        self._write_prop_file(output_dir)


    def _write_prop_file(self, output_dir='./nfw_particle_realization'):
        """
        Writes a csv file contining the halo properties needed by this package's  ray tracing modules
        A few values are arbitrary here, since we have a free NFW ball floating in space  with no 
        LOS structure-- the boxRadius is set to be 500arcsec, which corresponds to a physical scale 
        of ~3.4 comoving Mpc/h. The halo_lc_shell is needed for bookkeeping purposes in the raytracing
        input processing module, and is computed in the constructor according to an OuterRim-like
        setup (by default).

        Parameters
        ----------
        output_dir : string
            The desired output location for the property file 
        """
        cols = '#halo_redshift, halo_lc_shell, sod_halo_mass, sod_halo_radius, '\
               'sod_halo_cdelta, sod_halo_cdelta_error, halo_lc_x, halo_lc_y, halo_lc_z, '\
               'boxRadius_Mpc, boxRadius_arcsec, mpp'
        props = np.array([self.redshift, self.shell, self.m200c, self.r200c, self.c, 
                          0, 0, 0, self.halo_r, 3.42311, 500, self.mpp])
        np.savetxt('{}/../properties.csv'.format(output_dir), [props], 
                   fmt='%.6f,%i,%.6f,%.6f,%.6f,%.6f,%.6f,%.6f,%.6f,%.6f,%.6f,%.6f', 
                   delimiter=',',header=cols)
        



if __name__ == '__main__':
    hh = simple_halo(m200c = 1e14, z=0.3)
    hh.populate_halo(N=10000, rfrac=5)
    hh.output_particles(vis_debug=False)
