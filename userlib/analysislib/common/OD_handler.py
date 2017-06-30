from __future__ import division
from lyse import *
from time import time
from scipy.ndimage import interpolation, filters
#from matplotlib import pyplot as plt
import os
import pandas as pd
import numpy as np

class ODShot(object):
    'Handles OD data'
    pixel_size = 5.6e-6/3.15  # Divided by Magnification Factor

    def __init__(self, OD):
        self.OD = OD

    def rotate_OD(self, angle):
        rotated_OD = interpolation.rotate(self.OD, angle, reshape=True, prefilter=False)
        return rotated_OD

    def get_ROI(self, sniff=False, get_background=False):
        if sniff:
            pixel_size = 5.6e-6/3.15  # Divided by Magnification Factor
            done = False
            attempts = 0
            while not done:
                attempts += 1
                # First guess is Max
                try:
                    ROI_center_gx0, ROI_center_gy0  = (np.where(self.OD == np.amax(self.OD))[0][0],
                                                       np.where(self.OD == np.amax(self.OD))[1][0])
                # Always bound box to OD shape
                    x_min_dist = np.amin(np.array([ROI_center_gx0, np.abs(self.OD.shape[0]-ROI_center_gx0)]))
                    y_min_dist = np.amin(np.array([ROI_center_gy0, np.abs(self.OD.shape[1]-ROI_center_gy0)]))
                    x_bound, y_bound = np.amin(np.array([x_min_dist, 8])), np.amin(np.array([y_min_dist, 12]))
                except ValueError:  #Raised if empty.
                    pass
                # Select a box
                ROI_g0 = self.OD[ROI_center_gx0 - x_bound : ROI_center_gx0 + x_bound,
                                 ROI_center_gy0 - y_bound : ROI_center_gy0 + y_bound]
                # Get rid of weird values prior to sniffing
                ROI_g0[ROI_g0 == -np.inf] = np.nan
                ROI_g0[ROI_g0 <= -0.5] = np.nan
                # Sniff around to look for salt and pepper (noise)
                max_sniff = np.nanmax(ROI_g0)
                mean_sniff = np.nanmean(ROI_g0)
                std_sniff = np.nanstd(ROI_g0)
                salt_pepper_sniff = np.abs(mean_sniff-max_sniff)/np.abs(std_sniff-mean_sniff) > max_sniff
                #print "Found salt and pepper:", salt_pepper_sniff
                if salt_pepper_sniff:
                    done = False
                    print "ROI is sh*t, attempted", attempts,  "time(s)"
                    # Ban the sniffed ROI box by masking OD.
                    self.OD[ROI_center_gx0 - x_bound : ROI_center_gx0 + x_bound,
                            ROI_center_gy0 - y_bound : ROI_center_gy0 + y_bound] = np.zeros(ROI_g0.shape)
                # Break if too many attempts fail (good performance in less than 10 attempts!)
                elif not salt_pepper_sniff and attempts > 1000:
                    done = True
                    print "Failed to retrieve significant ROI, take better data next time!"
                    ROI = self.OD
                    break
                else:
                    done = True
                    print "**** Hawt Dawg! Found ROI ****"
                    ROI = self.OD[ROI_center_gx0 - x_bound : ROI_center_gx0 + x_bound,
                                  ROI_center_gy0 - y_bound : ROI_center_gy0 + y_bound]
            ROI_center = np.array([ROI_center_gx0, ROI_center_gy0])
            if get_background:
                OD_aux = self.OD
                OD_for_bck = np.copy(OD_aux)
                # Mask the OD array where ROI
                OD_for_bck[ROI_center_gx0 - x_bound : ROI_center_gx0 + x_bound,
                       ROI_center_gy0 - y_bound : ROI_center_gy0 + y_bound] = np.zeros(ROI.shape)
                # Check if background encloses ROI box
                encloses = True
                if encloses:
                    BCK_OD =(self.OD[ROI_center_gx0-x_bound-5:ROI_center_gx0+x_bound+5,
                                     ROI_center_gy0-y_bound-5:ROI_center_gy0+y_bound+5]-
                          OD_for_bck[ROI_center_gx0-x_bound-5:ROI_center_gx0+x_bound+5,
                                     ROI_center_gy0-y_bound-5:ROI_center_gy0+y_bound+5])
                    BCK_ROI = BCK_OD[ROI_center_gx0-x_bound-5:ROI_center_gx0+x_bound+5,
                                     ROI_center_gy0-y_bound-5:ROI_center_gy0+y_bound+5]
                    bck_area = np.count_nonzero(BCK_ROI)*(pixel_size**2)
                    background_level = BCK_ROI.sum()/bck_area
                    BCK = np.ones(ROI.shape)*background_level
                else:
                    raise Exception( 'Background does not include ROI... ')
                    ROI = ROI[~np.isnan(ROI)]
                return ROI, ROI_center, BCK
            else:
                ROI = ROI[~np.isnan(ROI)]
                return ROI, ROI_center
        elif not sniff:
            F_label, mF_label, ROIcoords, BCKcoords = np.load(r'C:\software\labscriptsuite\userlib\analysislib\ROI_temp.npy')
            Rx0, Rxm = np.amin([ROIcoords[0][0],ROIcoords[1][0]]), np.amax([ROIcoords[0][0],ROIcoords[1][0]])
            Ry0, Rym = np.amin([ROIcoords[0][1],ROIcoords[1][1]]), np.amax([ROIcoords[0][1],ROIcoords[1][1]])
            ROI = self.OD[Ry0:Rym, Rx0:Rxm]
            Bx0, Bxm = np.amin([BCKcoords[0][0],BCKcoords[1][0]]), np.amax([BCKcoords[0][0],BCKcoords[1][0]])
            By0, Bym = np.amin([BCKcoords[0][1],BCKcoords[1][1]]), np.amax([BCKcoords[0][1],BCKcoords[1][1]])
            BCK = self.OD[By0:Bym, Bx0:Bxm]
            return F_label[0], mF_label[0], ROI, BCK

    def slice_by_rot_OD(self, angle=0.0, center=None, slice_width=33):
        "Slices along angle segment, slice_width is in pixels,"
        "angle is taken counter-clockwise with respect to horizontal,"
        "center is default to array center unless specified"
        rad_angle = np.pi*angle/180
        np.ma.fix_invalid(self.OD, fill_value=0.0)
        OD_array = interpolation.rotate(self.OD, angle, reshape=False, prefilter=False)
        if (slice_width % 2 == 0):
            raise Exception('slice_width should be odd so that it'
                            'covers an evenly split range')
        if center is None:
            # Default to array center
            center_rot = ([np.int(OD_array.shape[0]/2), np.int(OD_array.shape[0]/2)])
        else:
            center_rot = np.array([np.int(center[1]*np.cos(rad_angle)-center[1]*np.sin(rad_angle)),
                                   np.int(center[0]*np.sin(rad_angle)+center[0]*np.cos(rad_angle))])
        # Slice
        sliced_OD = np.nanmean(OD_array[0:OD_array.shape[0],center_rot[0]-np.int((slice_width-1)/2):center_rot[0]+
                                     np.int((slice_width-1)/2)], axis=1)
        sliced_OD = sliced_OD[~np.isnan(sliced_OD)]
        slice_axis = np.linspace(0, np.amax(sliced_OD.shape), np.amax(sliced_OD.shape))
        return sliced_OD, slice_axis

    def slice_by_segment_OD(self, coord_a, coord_b, slice_width=3):
        "Slices along two point segment, slice_width is in pixels,"
        "coordinates are in pixel (array index), segment is A to B"
        np.ma.fix_invalid(self.OD, fill_value=0.0)
        if (slice_width % 2 == 0):
            raise Exception('slice_width should be odd so that it'
                            'covers an evenly split range')
        def check_for_bump(x_endpoint, y_endpoint):
            if x_endpoint > self.OD.shape[1] or x_endpoint < 0:
                if y_endpoint > self.OD.shape[0] or y_endpoint < 0:
                    raise Exception('Point is out of range')
                    check = False
            else:
                check = True
            return check
        # Bump check on input points A, B
        if check_for_bump(coord_a[1], coord_a[0]) and check_for_bump(coord_b[1], coord_b[0]):
            segment_length = np.int(np.hypot(coord_b[0]-coord_a[0], coord_b[1]-coord_a[1]))
            seg_x, seg_y = (np.linspace(coord_a[0], coord_b[0], segment_length),
                            np.linspace(coord_a[1], coord_b[1], segment_length))
            sliced_OD = np.array(self.OD[seg_x.astype(np.int), seg_y.astype(np.int)])[0]
            slice_axis = np.linspace(0, np.amax(sliced_OD.shape), np.amax(sliced_OD.shape))
        return sliced_OD, slice_axis

    def filter_OD(self, routine=None):
        OD_tilde = np.fft.fft2(self.OD)
        OD_fftshift = np.fft.fftshift(OD_tilde)
        ODlow = filters.gaussian_filter(np.abs(OD_fftshift), 2)
        OD_ifftshift = np.fft.ifftshift(OD_fftshift - ODlow)
        filtered_OD = np.abs(np.fft.ifft2(OD_ifftshift))
        return filtered_OD

    def mask_OD(self, shape='square'):
        # Not Implemented yet
        return masked_OD
