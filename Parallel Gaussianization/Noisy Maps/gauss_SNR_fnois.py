from astropy.io import fits
import numpy as np
import scipy.ndimage
from scipy import fftpack
import matplotlib as mpl
mpl.use('Agg')
import matplotlib.pyplot as plt
import sys
import scipy.special as SSp

np.seterr(divide = 'ignore', invalid = 'ignore')

def gaussianizepdf(denf,avgrepeats=True, sigmagauss = None,assumelognormal=True):
    denshape = denf.shape
    denff = denf.flatten()
    o_f = np.argsort(denff)
    gaussf = 0.*denff.astype(np.float)
    lenny = len(gaussf)

    if (sigmagauss == None):
        if assumelognormal:
            sigmagauss = np.sqrt(np.log1p(np.var(denff)))
        else:
            sigmagauss = np.std(denff)

    step = 1./lenny

    gaussf[o_f] = np.sqrt(2.)*sigmagauss*SSp.erfinv(2.*np.arange(0.5*step,1,step)-1.)

    # average together repeated elements
    if (avgrepeats):
        cuts = np.searchsorted(denff[o_f],np.unique(denff[o_f]))
        for i in range(len(cuts)-1):
            gaussf[o_f[cuts[i]:cuts[i+1]]] = np.mean(gaussf[o_f[cuts[i]:cuts[i+1]]])
        # get the last one
        gaussf[o_f[cuts[-1]:]]=np.mean(gaussf[o_f[cuts[-1]:]])

    gaussf = gaussf.reshape(denshape)

    return gaussf

def power1D(image, num_bins):
    
    y, x = np.indices(image.shape)
    center = np.array([(x.max() - x.min()) / 2., (x.max() - x.min()) / 2.])
    
    if image.shape[0] % 2 == 0:
        center += 0.5
    
    radii = np.hypot(x - center[0], y - center[1])
    
    sorted_radii_indices = np.argsort(radii.flat)
    sorted_radii = radii.flat[sorted_radii_indices]
    sorted_pixels = image.flat[sorted_radii_indices]
    
    bins = np.logspace(0, np.log10(image.shape[0]/2.), num_bins + 1)
    
    bin_weights = np.histogram(sorted_radii, bins)[0]
    bin_edges = np.cumsum(bin_weights)
    pixel_sums = np.cumsum(sorted_pixels, dtype=float)
    bin_totals = pixel_sums[bin_edges[1:] - 1] - pixel_sums[bin_edges[:-1] - 1]
    radial_prof = bin_totals/bin_weights[1:]
    
    return bins[1:], radial_prof

def PowerSpectrum(psd2D, sizedeg = 12.25, size = 37, bins = 50):
    
    ells, psd1D = power1D(psd2D, num_bins = 50)
    
    edge2center = lambda x: x[:-1]+0.5*(x[1:]-x[:-1])
    ells = edge2center(ells)
    
    ells *= 360. / np.sqrt(sizedeg)
    norm = ((2 * np.pi * np.sqrt(sizedeg) / 360.0) ** 2) / (size ** 2) ** 2
    powspec = ells * (ells + 1) / (2 * np.pi) * norm * psd1D
    
    last_nan = np.where(np.isnan(powspec))[0][-1]
    ells = ells[last_nan + 1:]
    powspec = powspec[last_nan + 1:]
    return ells, powspec

def SNR(powerspecs, covar):
    #Calculate Signal-to-Noise ratio given a set of powerspectra 
    
    powermean = np.mean(powerspecs, axis = 0) 
    powermeanmat = np.mat(powermean)    
    SNRsquare = powermeanmat * (covar.I * powermeanmat.T)
    
    return np.sqrt(SNRsquare), powermean

def corr_mat(covar):
    #Calculate the correlation matrix
    
    diag_sqrt = np.sqrt(np.diag(covar))
    X, Y = np.meshgrid(diag_sqrt, diag_sqrt)
    return covar / (X*Y)


def toPowspec(image_num):
    #print(image_num)
    image = np.load('/tigress/jialiu/CMBL_maps_46cosmo/noisy/reconMaps_Om0.296_Ol0.704_w-1.000_si0.786/recon_filtered_Om0.296_Ol0.704_w-1.000_si0.786_r' + '{:04d}'.format(image_num) + '.npy')
    #image = scipy.ndimage.filters.gaussian_filter(image, 9.75)
    #image = gaussianizepdf(image)
    F = fftpack.fftshift(fftpack.fft2(image))
    psd2D = np.abs(F)**2
    ells, powspec = PowerSpectrum(psd2D, sizedeg = 12.25, size = 37, bins = 50)

    return ells, powspec


image_range = np.arange(1, 1000)

from emcee.utils import MPIPool
pool = MPIPool()
if not pool.is_master():
    pool.wait()
    sys.exit(0)

results = np.array(pool.map(toPowspec, image_range))
pool.close()

ells = results[0, 0]
powspecs = np.array([r[1] for r in results])


covar = np.mat(np.cov(powspecs, rowvar = 0))
print("\nCovariance Matrix: ")
print(covar)

fig1 = plt.figure(figsize=(6, 3.4))

ax = fig1.add_subplot(111)
ax.set_title('Covariance Matrix Heat Map')
plt.imshow(np.array(covar), cmap = 'hot')
ax.set_aspect('equal')

cax = fig1.add_axes([0.12, 0.1, 0.78, 0.8])
cax.get_xaxis().set_visible(False)
cax.get_yaxis().set_visible(False)
cax.patch.set_alpha(0)
cax.set_frame_on(False)
plt.colorbar(orientation = 'vertical')

fig1.savefig("fnoisycovar.png")


correl = corr_mat(covar)
print("\nCorrelation Matrix: ")
print(correl)

fig2 = plt.figure(figsize=(6, 3.4))

ax = fig2.add_subplot(111)
ax.set_title('Correlation Matrix Heat Map - Noisy (Filtered), Ungaussianized')
plt.imshow(np.array(correl), cmap = 'hot')
ax.set_aspect('equal')

cax = fig2.add_axes([0.12, 0.1, 0.78, 0.8])
cax.get_xaxis().set_visible(False)
cax.get_yaxis().set_visible(False)
cax.patch.set_alpha(0)
cax.set_frame_on(False)
plt.colorbar(orientation = 'vertical')

fig2.savefig("fnoisycorrmat.png")



s2r, powermean = SNR(powspecs, covar)
print("\nSignal-to-Noise ratio: ")
print(s2r)



fig3 = plt.figure()
ax1 = fig3.add_subplot(111)

ax1.set_xscale("log", nonposx='clip')
ax1.set_yscale("log", nonposy='clip')

std_P = np.std(powspecs, axis = 0)
plt.errorbar(ells, powermean, std_P)

ax1.set_title("Mean Power Spectrum -- Noisy Maps (Filtered), Ungaussianized, Unsmoothed (7/27/17)")
ax1.set_ylabel(r'$\frac{\ell (\ell + 1) C_\ell}{2\pi}$', fontsize = 20)
ax1.set_xlabel(r'$\ell$', fontsize = 20)
ax1.set_xlim(1e2, 1e4)
fig3.savefig("fnoisypowermean.png", bbox_inches = 'tight')



fig4 = plt.figure()
for p in powspecs:
    plt.loglog(ells, p)
plt.title("All Power Spectra -- Noisy Maps (Filtered), Ungaussianized, Unsmoothed (7/27/17)")
plt.ylabel(r'$\frac{\ell (\ell + 1) C_\ell}{2\pi}$', fontsize = 20)
plt.xlabel(r'$\ell$', fontsize = 20)
fig4.savefig("fnoisypowerspecs.png", bbox_inches = 'tight')
