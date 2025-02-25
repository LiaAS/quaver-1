######
######
import os
import http
from astropy.coordinates.name_resolve import NameResolveError
#########
##########

import lightkurve as lk
import numpy as np
import re

#################
#################


#THE FOLLOWING STATEMENTS MAY BE NEEDED IF RUNNING IN WINDOWS LINUX ENVIRONMENT:
#(NOTE: adding these may cause a Tkinter deprecation warning, but should not affect performance.)

#import matplotlib
#import tkinter
#matplotlib.use("TkAgg")


####################
###################

import matplotlib.pyplot as plt
from astropy.coordinates import get_icrs_coordinates
from astroquery.skyview import SkyView
from astropy.coordinates import SkyCoord
from astropy.wcs import *
from astropy import units as u
import astropy.io.fits as pyfits
from copy import deepcopy
from matplotlib import gridspec
from matplotlib import patches
import sys

##################  TUNABLE PARAMETERS  ##########################

#Which method would you like to use?
#  1 = full hybrid reduction (see User's Guide)
#  2 = simple reduction using Principle Component Analysis

systematics_correction_method = 1

#Size of the TPF postage stamp to download and use for exraction and detrending.
tpf_width_height = 25

#Number of PCA Components in the Hybrid method and simple PCA correction.
additive_pca_num = 3
multiplicative_pca_num = 3
pca_only_num = 3

#Lowest DSS contour level, as fraction of peak brightness
#(For fields with bright stars, the default lowest level of 0.4 may be too high to see your faint source)
lowest_dss_contour = 0.4

#Acceptable threshold for systematics in additive components:
sys_threshold = 0.2

#Maximum number of cadence-mask regions allowed:
max_masked_regions = 5 #set maximum number of regions of the light curve that can be masked out.

#Which cadence of the TESSCut file is used for the aperture selection panel
#(It is best to avoid the first or last cadences as they are often hard to see due to systematics)
plot_index = 500


############################################
#Define function to record the positions of clicks in the pixel array image for the extraction mask.
def onclick(event):

    global ix,iy
    ix,iy = int(round(event.xdata)),int(round(event.ydata))

    global row_col_coords

    if (iy,ix) in row_col_coords:
        row_col_coords.remove((iy,ix))
        plt.plot(ix,iy,marker="x",color='red',markersize=9)
        fig.canvas.draw()

        print('removing'+str((ix,iy)))
    else:
        row_col_coords.append((iy,ix))
        plt.plot(ix,iy,marker=u"$\u2713$",color='limegreen',markersize=9)
        fig.canvas.draw()

        print('adding'+str((ix,iy)))

#############################################


############################################
#Define function to record the X-positions of the cadences to mask out if needed.
def onclick_cm(event):

    global ix_cm
    ix_cm = int(round(event.xdata))

    global masked_cadence_limits
    masked_cadence_limits.append(ix_cm)
    print(ix_cm)

        #plt.axvspan(masked_cadence_limits[0],masked_cadence_limits[1],color='r')
    plt.axvline(x=ix_cm,color='red')
    fig_cm.canvas.draw()

   # print('Masking cadences '+str(masked_cadence_limits[0])+" --> "+str(masked_cadence_limits[1]))


#############################################
#############################################
#Define target and obtain DSS image from coordinates.

try :
    target = input('Target Common Name: ')
    target_coordinates = target
    source_coordinates = get_icrs_coordinates(target)       #this requires that SIMBAD be up and working...
    print(source_coordinates)
    print("\n")

# If target is not found by name use Sky Coordinates
# Enter as glactic coordinates for simple reference to SIMBAD

except NameResolveError:
    print("\n"+"Could not find target by name provided. Try Sky Coordinates.\n")
    print("Input as ICRS: RA,Dec  (in Decimal Degrees, with no space)")

    input_coord_string = input('RA,Dec: ')
    input_coord_split = re.split("\s|[,]|[,\s]",input_coord_string)

    ra = float(input_coord_split[0])
    dec = float(input_coord_split[1])

    source_coordinates = SkyCoord(ra,dec,frame='icrs',unit='deg')

    target = input('Desired object name for output files: ')
    target_coordinates = str(ra)+" "+str(dec)

    print(source_coordinates)
    print("\n")
#############################################
#############################################


dss_image = SkyView.get_images(position=source_coordinates,survey='DSS',pixels=str(400))
wcs_dss = WCS(dss_image[0][0].header)
dss_pixmin = np.min(dss_image[0][0].data)
dss_pixmax = np.max(dss_image[0][0].data)
dss_pixmean = np.mean(dss_image[0][0].data)

dss_head = dss_image[0][0].header
dss_ra = dss_head['CRVAL1']
dss_dec = dss_head['CRVAL2']


#Retrieve the available tesscut data for FFI-only targets.
sector_data = lk.search_tesscut(target_coordinates)
num_obs_sectors = len(sector_data)

if num_obs_sectors == 0:
    print("This object has not been observed by TESS.")

    sys.exit()


print(sector_data)
print('\n')
print('Table of Cycles by Sector:')
print('Cycle 1: Sectors 1-13')
print('Cycle 2: Sectors 14-26')
print('Cycle 3: Sectors 27-39')
print('Cycle 4: Sectors 40-55')

#Set cycle of interest, while making sure the chosen cycle corresponds to actual observed sectors:

check_cycle = False

while check_cycle == False:

    cycle = int(input('Enter Cycle: '))

    first_sectors = [1,14,27,40]
    last_sectors = [13,26,39,55]

    if cycle == 1:
        first_sector = first_sectors[0]
        last_sector = last_sectors[0]
    elif cycle ==2:
        first_sector = first_sectors[1]
        last_sector = last_sectors[1]
    elif cycle ==3:
        first_sector = first_sectors[2]
        last_sector = last_sectors[2]
    elif cycle==4:
        first_sector = first_sectors[3]
        last_sector = last_sectors[3]
    else:
        print('Invalid Cycle Number')


    list_observed_sectors = []
    list_observed_sectors_in_cycle = []
    list_sectordata_index_in_cycle = []

    for i in range(0,len(sector_data)):

        sector_number = int(sector_data[i].mission[0][12:14])       #This will need to change, Y2K style, if TESS ever has more than 100 sectors.
        list_observed_sectors.append(sector_number)

        if sector_number >= first_sector and sector_number <= last_sector:

            list_observed_sectors_in_cycle.append(sector_number)
            list_sectordata_index_in_cycle.append(i)

    check_cycle = any(i>=first_sector and i<=last_sector for i in list_observed_sectors)
    if check_cycle == False:
        print('Selected cycle does not correspond to any observed sectors. Try again.')


unstitched_lc_regression = []
unstitched_lc_pca = []

if num_obs_sectors == 0:
    print("This object has not been observed by TESS.")

    sys.exit()

else:

    for i in range(0,len(list_sectordata_index_in_cycle)):

        try:

            tpf = sector_data[list_sectordata_index_in_cycle[i]].download(cutout_size=(tpf_width_height, tpf_width_height)) #gets earliest sector

            sector_number = tpf.get_header()['SECTOR']
            sec = str(sector_number)
            ccd = tpf.get_header()['CCD']
            cam = tpf.get_header()['CAMERA']



            print("Generating pixel map for sector "+sec+".\n")

            #Check that this object is actually on silicon and getting data (not always the case just because TESSCut says so).
            #By making a light curve from a dummy aperture of the middle 5x5 square and seeing if its mean flux is zero.

            aper_dummy = np.zeros(tpf[0].shape[1:], dtype=bool) #blank
            aper_dummy[int(tpf_width_height/2-3):int(tpf_width_height/2+3),int(tpf_width_height/2-3):int(tpf_width_height/2+3)] = True
            lc_dummy = tpf.to_lightcurve(aperture_mask=aper_dummy)

            if np.mean(lc_dummy.flux) == 0:
                print("This object is not actually on silicon, and its download was a mistake by TESSCut.")
                sys.ext()

            else:

                hdu = tpf.get_header(ext=2)

                #Get WCS information and flux stats of the TPF image.
                tpf_wcs = WCS(tpf.get_header(ext=2))

                pixmin = np.min(tpf.flux[plot_index]).value
                pixmax = np.max(tpf.flux[plot_index]).value
                pixmean = np.mean(tpf.flux[plot_index]).value

                temp_min = float(pixmin)
                # print(temp_min)
                temp_max = float(1e-3*pixmax+pixmean)
                # print(temp_max)

                #Create a blank boolean array for the aperture, which will turn to TRUE when pixels are selected.

                aper = np.zeros(tpf[0].shape[1:], dtype=bool) #blank
                aper_mod = aper.copy()       #For the source aperture
                aper_buffer = aper.copy()    #For the source aperture plus a buffer region to exclude from both additive and mult. regressors

                aper_width = tpf[0].shape[1]
                #Plot the TPF image and the DSS contours together, to help with aperture selection, along with the starter aperture.

                if lowest_dss_contour == 0.4:
                    dss_levels = [0.4*dss_pixmax,0.5*dss_pixmax,0.75*dss_pixmax]
                else:
                    dss_levels = [lowest_dss_contour*dss_pixmax,0.4*dss_pixmax,0.5*dss_pixmax,0.75*dss_pixmax]

                fig = plt.figure(figsize=(8,8))
                ax = fig.add_subplot(111,projection=tpf_wcs)
                # ax.imshow(tpf.flux[200],vmin=pixmin,vmax=1e-3*pixmax+pixmean)
                ax.imshow(tpf.flux[plot_index],vmin=temp_min,vmax=temp_max)
                ax.contour(dss_image[0][0].data,transform=ax.get_transform(wcs_dss),levels=dss_levels,colors='white',alpha=0.9)
                ax.scatter(aper_width/2.0,aper_width/2.0,marker='x',color='k',s=8)

                ax.set_xlim(-0.5,aper_width-0.5)  #This section is needed to fix the stupid plotting issue in Python 3.
                ax.set_ylim(-0.5,aper_width-0.5)

                plt.title('Define extraction pixels:')
                row_col_coords = []
                cid = fig.canvas.mpl_connect('button_press_event',onclick)

                plt.show()
                plt.close(fig)

                fig.canvas.mpl_disconnect(cid)

                buffer_pixels = []      #Define the buffer pixel region.

                if len(row_col_coords) == 0:
                    print('No mask selected; skipping this Sector.')

                else:

                    for i in range(0,len(row_col_coords)):

                        aper_mod[row_col_coords[i]] = True

                        row_same_up_column = (row_col_coords[i][0],row_col_coords[i][1]+1)
                        row_same_down_column = (row_col_coords[i][0],row_col_coords[i][1]-1)
                        column_same_down_row = (row_col_coords[i][0]-1,row_col_coords[i][1])
                        column_same_up_row = (row_col_coords[i][0]+1,row_col_coords[i][1])

                        bottom_left_corner = (row_col_coords[i][0]-1,row_col_coords[i][1]-1)
                        top_right_corner = (row_col_coords[i][0]+1,row_col_coords[i][1]+1)
                        top_left_corner = (row_col_coords[i][0]+1,row_col_coords[i][1]-1)
                        bottom_right_corner = (row_col_coords[i][0]-1,row_col_coords[i][1]+1)

                        buffer_line = (row_same_up_column,row_same_down_column,column_same_up_row,column_same_down_row,top_left_corner,top_right_corner,bottom_left_corner,bottom_right_corner)
                        buffer_pixels.append(buffer_line)

                        for coord_set in buffer_line:
                                aper_buffer[coord_set[0],coord_set[1]]=True



                    #Create a mask that finds all of the bright, source-containing regions of the TPF.
                    #Need to change to prevent requiring contiguous mask:
                    '''
                    thumb = np.nanpercentile(tpf.flux, 95, axis=0)
                    thumb -= np.nanpercentile(thumb, 20)
                    allbright_mask = thumb > np.percentile(thumb, 40)
                    '''
                    allbright_mask = tpf.create_threshold_mask(threshold=1.5,reference_pixel=None)
                    allfaint_mask = ~allbright_mask

                    allbright_mask &= ~aper_buffer
                    allfaint_mask &= ~aper_buffer

                    #Remove any empty flux arrays from the downloaded TPF before we even get started:

                    boolean_orignans = []

                    for i in range(0,len(tpf.flux)):

                        if np.sum(tpf.flux[i] == 0) or np.isnan(np.sum(tpf.flux[i])) == True:

                            nanflag = True

                        else:

                            nanflag = False

                        boolean_orignans.append(nanflag)

                    boolean_orignans_array = np.array(boolean_orignans)
                    tpf = tpf[~boolean_orignans_array]

                    #New attempt to get the additive background first:

                    additive_hybrid_pcas = additive_pca_num

                    additive_bkg = lk.DesignMatrix(tpf.flux[:, allfaint_mask]).pca(additive_hybrid_pcas)
                    additive_bkg_and_constant = additive_bkg.append_constant()

                    #Add a module to catch possible major systematics that need to be masked out before continuuing:

                    if np.max(np.abs(additive_bkg.values)) > sys_threshold:   #None of the normally extracted objects has additive components with absolute values over 0.2 ish.

                        redo_with_mask = input('Additive trends in the background indicate major systematics; add a cadence mask (Y/N) ?')

                        if redo_with_mask == 'Y' or redo_with_mask=='y' or redo_with_mask=='YES' or redo_with_mask=='yes':

                            number_masked_regions = 1 #set to 1 at first, for this mask.

                            fig_cm = plt.figure()
                            ax_cm = fig_cm.add_subplot()
                            ax_cm.plot(additive_bkg.values)

                            plt.title('Select first and last cadence to define mask region:')
                            masked_cadence_limits = []
                            cid_cm = fig_cm.canvas.mpl_connect('button_press_event',onclick_cm)

                            plt.show()
                            plt.close(fig_cm)

                            if len(masked_cadence_limits) != 0:

                                if masked_cadence_limits[0] >= 0:
                                    first_timestamp = tpf.time[masked_cadence_limits[0]].value
                                else:
                                    first_timestamp = 0
                                if masked_cadence_limits[1] < len(tpf.time) -1:
                                    last_timestamp = tpf.time[masked_cadence_limits[1]].value
                                else:
                                    last_timestamp = tpf.time[-1].value

                                cadence_mask = ~((tpf.time.value >= first_timestamp) & (tpf.time.value <= last_timestamp))

                                tpf = tpf[cadence_mask]

                                additive_bkg = lk.DesignMatrix(tpf.flux[:, allfaint_mask]).pca(additive_hybrid_pcas)
                                additive_bkg_and_constant = additive_bkg.append_constant()

                                print(np.max(np.abs(additive_bkg.values)))


                                for i in range(0,max_masked_regions):

                                    if np.max(np.abs(additive_bkg.values)) > sys_threshold  and number_masked_regions <= max_masked_regions:

                                        number_masked_regions += 1

                                        print('Systematics remain; define the next masked region.')
                                        print(np.max(np.abs(additive_bkg.values)))
                                        fig_cm = plt.figure()
                                        ax_cm = fig_cm.add_subplot()
                                        ax_cm.plot(additive_bkg.values)

                                        plt.title('Select first and last cadence to define mask region:')
                                        masked_cadence_limits = []
                                        cid_cm = fig_cm.canvas.mpl_connect('button_press_event',onclick_cm)

                                        plt.show()
                                        plt.close(fig_cm)

                                        if len(masked_cadence_limits) != 0:


                                            if masked_cadence_limits[0] >= 0:
                                                first_timestamp = tpf.time[masked_cadence_limits[0]].value
                                            else:
                                                first_timestamp = 0
                                            if masked_cadence_limits[1] < len(tpf.time) -1:
                                                last_timestamp = tpf.time[masked_cadence_limits[1]].value
                                            else:
                                                last_timestamp = tpf.time[-1].value


                                            cadence_mask = ~((tpf.time.value >= first_timestamp) & (tpf.time.value <= last_timestamp))

                                            tpf = tpf[cadence_mask]

                                            additive_bkg = lk.DesignMatrix(tpf.flux[:, allfaint_mask]).pca(additive_hybrid_pcas)
                                            additive_bkg_and_constant = additive_bkg.append_constant()

                                        else:

                                            number_masked_regions = max_masked_regions+1    #stops the loop if the user no longer wishes to add more regions.

                    # Now we correct all the bright pixels EXCLUDING THE SOURCE by the background, so we can find the remaining multiplicative trend

                    r = lk.RegressionCorrector(lk.LightCurve(time=tpf.time, flux=tpf.time.value*0))

                    corrected_pixels = []
                    for idx in range(allbright_mask.sum()):
                        r.lc.flux = tpf.flux[:, allbright_mask][:, idx]
                        r.correct(additive_bkg_and_constant)
                        corrected_pixels.append(r.corrected_lc.flux)


                    #Getting the multiplicative effects now from the bright pixels.

                    multiplicative_hybrid_pcas = multiplicative_pca_num
                    multiplicative_bkg = lk.DesignMatrix(np.asarray(corrected_pixels).T).pca(multiplicative_hybrid_pcas)

                    #Now we make a fancy hybrid design matrix that has both orders of the additive effects and the multiplicative ones.
                    #This is not currently used, because it tends to over-fit the low-frequency behavior against the scattered light.
                    #However, it can be used to study the high-frequency behavior in detail if needed.
                    #Create a higher order version of the additive effects:
                    '''
                    additive_bkg_squared = deepcopy(additive_bkg)
                    additive_bkg_squared.df = additive_bkg_squared.df**2


                    dm = lk.DesignMatrixCollection([additive_bkg_and_constant, additive_bkg_squared, multiplicative_bkg])
                    '''

                    #Create a design matrix using the multiplicative components determined from the additively-corrected bright sources:
                    dm_mult = multiplicative_bkg
                    dm_mult = dm_mult.append_constant()

                    #Now get the raw light curve.
                    lc = tpf.to_lightcurve(aperture_mask=aper_mod)
                #  lc = lc[lc.flux_err > 0]        #This was suggested by an error message to prevent the "flux uncertainties" problem.

                    median_flux_precorr = np.median(lc.flux.value) #Calculate the median flux before the background subtraction upcoming.

                    #Perform simple background subtraction to handle additive effects:
                    lc_bg = tpf.to_lightcurve(method='sap',corrector=None,aperture_mask = allfaint_mask)

                    num_pixels_faint = np.count_nonzero(allfaint_mask)
                    num_pixels_mask = np.count_nonzero(aper_mod)
                    percent_of_bg_in_src = num_pixels_mask / num_pixels_faint

                    lc_bg_time = lc_bg.time.value
                    lc_bg_flux = lc_bg.flux.value
                    lc_bg_fluxerr = lc_bg.flux_err.value

                    lc_bg_scaled = lc_bg_flux - (1-percent_of_bg_in_src)*lc_bg_flux

                    lc.flux = lc.flux.value - lc_bg_scaled

                    #Replace any errors that are zero or negative with the mean error:

                    mean_error = np.mean(lc.flux_err[np.isfinite(lc.flux_err)])
                    lc.flux_err = np.where(lc.flux_err == 0,mean_error,lc.flux_err)
                    lc.flux_err = np.where(lc.flux_err < 0,mean_error,lc.flux_err)

                    #And correct regressively for the multiplicative effects:

                    corrector_1 = lk.RegressionCorrector(lc)
                    clc = corrector_1.correct(dm_mult)

                    #The background subtraction can sometimes cause fluxes below the source's median
                    #to be slightly negative; this enforces a minimum of zero, but can be ignored.

                    if np.min(clc.flux.value) < 0:

                        dist_to_zero = np.abs(np.min(clc.flux.value))
                        clc.flux = clc.flux.value + dist_to_zero

                    #Now, we provide an optional rescaling, in order that the final light curve has a median flux similar to the pre-subtracted flux.
                    #This should be used with caution, as they affect the percent variability of the source

                    median_flux_postsub = np.median(clc.flux.value)

                    ######### OPTIONAL ADDITIVE CORRECTION BACK TO ORIGINAL MEDIAN ########
                    additive_rescale_factor = median_flux_precorr - median_flux_postsub
                    #clc.flux = clc.flux.value + additive_rescale_factor    #uncomment if you want to use this.

                    var_amplitude = np.max(clc.flux.value) - np.min(clc.flux.value)
                    percent_variability = (var_amplitude / median_flux_precorr)*100

                    #Now we begin the simpler method of using PCA components of all non-source pixels.

                    raw_lc_OF = tpf.to_lightcurve(aperture_mask=aper_mod)

                    #Replace any errors that are zero or negative with the mean error:
                    raw_lc_OF.flux_err = np.where(raw_lc_OF.flux_err == 0,mean_error,raw_lc_OF.flux_err)
                    raw_lc_OF.flux_err = np.where(raw_lc_OF.flux_err < 0,mean_error,raw_lc_OF.flux_err)
                    raw_lc_OF.flux_err = np.where(np.isnan(raw_lc_OF.flux_err)==True,mean_error,raw_lc_OF.flux_err)

                #    raw_lc_OF = raw_lc_OF[raw_lc_OF.flux_err > 0]   #This was suggested by an error message to prevent the "flux uncertainties" problem.
                    regressors_OF = tpf.flux[:,~aper_mod]

                    number_of_pcas = pca_only_num

                    dm_OF = lk.DesignMatrix(regressors_OF,name='regressors')
                    dm_pca_OF = dm_OF.pca(pca_only_num)
                    dm_pca_OF = dm_pca_OF.append_constant()

                    corrector_pca_OF = lk.RegressionCorrector(raw_lc_OF)
                    corrected_lc_pca_OF = corrector_pca_OF.correct(dm_pca_OF)

                    #AND PLOT THE CORRECTED LIGHT CURVE.

                    fig2 = plt.figure(figsize=(12,8))
                    gs = gridspec.GridSpec(ncols=3, nrows=3,wspace=0.5,hspace=0.5,width_ratios=[1,1,2])
                    f_ax1 = fig2.add_subplot(gs[0, :])
                    f_ax1.set_title(target+': Corrected Light Curve')
                    f_ax2 = fig2.add_subplot(gs[1, :-1])
                    if systematics_correction_method == 1:
                        f_ax2.set_title('Additive Components')
                        f_ax3 = fig2.add_subplot(gs[2:,:-1])
                        f_ax3.set_title('Multiplicative Components')
                        f_ax4 = fig2.add_subplot(gs[1:,-1])
                    elif systematics_correction_method == 2:
                        f_ax2.set_title('Principal Components')
                        f_ax4 = fig2.add_subplot(gs[1:,-1])


                    if systematics_correction_method == 1:
                        clc.plot(ax=f_ax1)
                    elif systematics_correction_method == 2:
                        corrected_lc_pca_OF.plot(ax=f_ax1)

                    if systematics_correction_method == 1:
                        f_ax2.plot(additive_bkg.values)
                        f_ax3.plot(multiplicative_bkg.values + np.arange(multiplicative_bkg.values.shape[1]) * 0.3)
                    elif systematics_correction_method == 2:
                        f_ax2.plot(dm_pca_OF.values[:,0:-1])

                    tpf.plot(ax=f_ax4,aperture_mask=aper_mod,title='Aperture')

                    ## This section creates individual directories for each object in which the quaver procesed light curve data is stored
                    ##  then saves the corrected lightcurves along with additive and multiplicative components as well as the aperture selection

    ###############################################################################
    ##############################################################################
                    directory = str(target).replace(" ","")
                    target_safename = target.replace(" ","")
                    try:
                        os.makedirs('quaver_output/'+target_safename)
                        print("Directory '% s' created\n" % directory)
                        if systematics_correction_method == 1:
                            plt.savefig('quaver_output/'+target_safename+'/'+target_safename+'_hybrid_sector'+sec+'.pdf',format='pdf')
                            plt.show()
                        elif systematics_correction_method == 2:
                            plt.savefig('quaver_output/'+target_safename+'/'+target_safename+'_PCA_sector'+sec+'.pdf',format='pdf')
                            plt.show()

                    except FileExistsError:
                        print("Saving to folder '% s'\n" % directory)
                        if systematics_correction_method == 1:
                            plt.savefig('quaver_output/'+target_safename+'/'+target_safename+'_hybrid_sector'+sec+'.pdf',format='pdf')
                            plt.show()
                        elif systematics_correction_method == 2:
                            plt.savefig('quaver_output/'+target_safename+'/'+target_safename+'_PCA_sector'+sec+'.pdf',format='pdf')
                            plt.show()
    ##################################################################################
    ###############################################################################



                    regression_corrected_lc = np.column_stack((clc.time.value,clc.flux.value,clc.flux_err.value))
                    pca_corrected_lc = np.column_stack((corrected_lc_pca_OF.time.value,corrected_lc_pca_OF.flux.value,corrected_lc_pca_OF.flux_err.value))

                    unstitched_lc_regression.append(regression_corrected_lc)
                    unstitched_lc_pca.append(pca_corrected_lc)

                    np.savetxt('quaver_output/'+target_safename+'/'+target_safename+'_cycle'+str(cycle)+'_sector'+sec+'_hybrid_lc.dat',regression_corrected_lc)
                    np.savetxt('quaver_output/'+target_safename+'/'+target_safename+'_cycle'+str(cycle)+'_sector'+sec+'_PCA_lc.dat',pca_corrected_lc)

                    print("Sector, CCD, camera: ")
                    print(sector_number,ccd,cam)

                    print("Percent variability before background subtraction: "+str(round(percent_variability,2))+"%")

    #############################################
    #############################################
                    print("\nMoving to next sector.\n")
    #############################################
    #############################################

        # If target coordinates are too close to edge on approach, this will skip that sector and read the next.
        # If target coordinates are too close to edge on exit, this will skip that sector and break on the next loop.
        ## WARNING: May also occur if connection to HEASARC could not be made. Check website and/or internet connection.

#############################################
#############################################
        except (http.client.IncompleteRead):

            print("Unable to download FFI cutout. Desired target coordinates may be too near the edge of the FFI.\n")
            print("Could be inability to connect to HEASARC. Check website availability and/or internet connection.\n")

            if i != num_obs_sectors-1:

              print("\nMoving to next sector.\n")

            continue

#############################################
#############################################

print("No more observed sectors in this cycle.")

if len(unstitched_lc_regression)==0 and len(unstitched_lc_pca)==0:
    print("No light curve data extracted, exiting program.")

    sys.exit()

else:
    print("Stitching light curves together.\n")

    #Loop for stitching the light curves together


    for j in range(0,len(unstitched_lc_regression)):
        if j==0:
            print("First observed sector")
        else:
            sector = str(j+1)
            print('Stitching '+sector+' sectors')

        lc_reg = unstitched_lc_regression[j]
        lc_pca = unstitched_lc_pca[j]

        t_reg = lc_reg[:,0]
        f_reg = lc_reg[:,1]
        err_reg = lc_reg[:,2]

        t_pca = lc_pca[:,0]
        f_pca = lc_pca[:,1]
        err_pca = lc_pca[:,2]

        if j == 0:

            full_lc_flux_reg = f_reg
            full_lc_flux_pca = f_pca

            full_lc_time_reg = t_reg
            full_lc_time_pca = t_pca

            full_lc_err_reg = err_reg
            full_lc_err_pca = err_pca

        else:

            first_flux_reg = np.mean(f_reg[:10])
            first_flux_pca = np.mean(f_pca[:10])

            last_flux_reg = np.mean(full_lc_flux_reg[-10:])
            last_flux_pca = np.mean(full_lc_flux_pca[-10:])

            scale_factor_reg = first_flux_reg - last_flux_reg
            scale_factor_pca = first_flux_pca - last_flux_pca

            if scale_factor_reg > 0:

                scaled_flux_reg = f_reg - abs(scale_factor_reg)

            if scale_factor_reg < 0:

                scaled_flux_reg = f_reg + abs(scale_factor_reg)

            if scale_factor_pca > 0:

                scaled_flux_pca = f_pca - abs(scale_factor_pca)

            if scale_factor_pca < 0:

                scaled_flux_pca = f_pca + abs(scale_factor_pca)


            full_lc_flux_reg = np.append(full_lc_flux_reg,scaled_flux_reg)
            full_lc_flux_pca = np.append(full_lc_flux_pca,scaled_flux_pca)

            full_lc_time_reg = np.append(full_lc_time_reg,t_reg)
            full_lc_time_pca = np.append(full_lc_time_pca,t_pca)

            full_lc_err_reg = np.append(full_lc_err_reg,err_reg)
            full_lc_err_pca = np.append(full_lc_err_pca,err_pca)



    #Remove single-cadence jumps greater than 1% of the flux on either side from both finished light curves

    for i in range(0,1-len(full_lc_time_reg)):

        if i !=0 and i != len(full_lc_flux_reg)-1 and full_lc_flux_reg[i] > (0.01 * full_lc_flux_reg[i-1]+full_lc_flux_pca[i-1]) and full_lc_flux_pca[i] > (0.01 * full_lc_flux_pca[i+1]+full_lc_flux_pca[i+1]):

            full_lc_flux_reg = np.delete(full_lc_flux_reg,i)
            full_lc_time_reg = np.delete(full_lc_time_reg,i)

    for i in range(0,1-len(full_lc_time_pca)):

        if i !=0 and i != len(full_lc_flux_reg)-1 and full_lc_flux_pca[i] > (0.01 * full_lc_flux_pca[i-1]+full_lc_flux_pca[i-1]) and full_lc_flux_pca[i] > (0.01 * full_lc_flux_pca[i+1]+full_lc_flux_pca[i+1]):

            full_lc_flux_pca = np.delete(full_lc_flux_pca,i)
            full_lc_time_pca = np.delete(full_lc_time_pca,i)

    for i in range(0,1-len(full_lc_time_reg)):

        if i !=0 and i != len(full_lc_flux_reg)-1 and full_lc_flux_reg[i] < (full_lc_flux_pca[i-1]-0.01 * full_lc_flux_reg[i-1]) and full_lc_flux_pca[i] < (full_lc_flux_pca[i+1]-0.01 * full_lc_flux_pca[i+1]):

            full_lc_flux_reg = np.delete(full_lc_flux_reg,i)
            full_lc_time_reg = np.delete(full_lc_time_reg,i)

    for i in range(0,1-len(full_lc_time_pca)):

        if i !=0 and i != len(full_lc_flux_reg)-1 and full_lc_flux_pca[i] < (full_lc_flux_pca[i-1]-0.01 * full_lc_flux_pca[i-1]) and full_lc_flux_pca[i] > (full_lc_flux_pca[i+1]-0.01 * full_lc_flux_pca[i+1]):

            full_lc_flux_pca = np.delete(full_lc_flux_pca,i)
            full_lc_time_pca = np.delete(full_lc_time_pca,i)

    #Compile and save the corrected light curves.

    regression_lc = np.column_stack((full_lc_time_reg,full_lc_flux_reg,full_lc_err_reg))
    pca5_lc = np.column_stack((full_lc_time_pca,full_lc_flux_pca,full_lc_err_pca))

    if systematics_correction_method == 1:
        np.savetxt('quaver_output/'+target_safename+'/'+target_safename+'_cycle'+str(cycle)+'_hybrid_lc.dat',regression_lc)
    elif systematics_correction_method == 2:
        np.savetxt('quaver_output/'+target_safename+'/'+target_safename+'_cycle'+str(cycle)+'_PCA_lc.dat',pca5_lc)



    #Plot the corrected light curves and save image.
    if systematics_correction_method == 1:
        plt.errorbar(full_lc_time_reg,full_lc_flux_reg,yerr = full_lc_err_reg,marker='o',markersize=1,color='b',linestyle='none')
    elif systematics_correction_method == 2:
        plt.errorbar(full_lc_time_pca,full_lc_flux_pca,yerr = full_lc_err_pca,marker='o',markersize=1,color='orange',linestyle='none')



    for i in range(0,len(unstitched_lc_regression)):

        last_time = unstitched_lc_regression[i][:,0][-1]

        plt.axvline(x=last_time,color='k',linestyle='--')
    if systematics_correction_method == 1:
        plt.savefig('quaver_output/'+target_safename+'/'+target_safename+'_cycle'+str(cycle)+'_stitched_hybrid_corr_lc.pdf',format='pdf')
    elif systematics_correction_method == 2:
        plt.savefig('quaver_output/'+target_safename+'/'+target_safename+'_cycle'+str(cycle)+'_stitched_PCA_corr_lc.pdf',format='pdf')

    plt.show()
    print ("Done!")
