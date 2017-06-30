from __future__ import division
from lyse import *
from time import time
from matplotlib import pyplot as plt
from common.OD_handler import ODShot
# from analysislib.spinor.aliases import *
import os
import pandas as pd
import numpy as np
import matplotlib.cm as cm




# def raw_to_OD(fpath):
    # with h5py.File(fpath) as h5_file:
        # image_group = {}
        #Safe to assume uwave lock is *only* along z-insitu
        # if  '/data/imagesXY_2_Flea3' in h5_file:
            # image_group['imagesXY_2_Flea3'] = 'z-insitu'
            # Isat = 395      # In counts // Paco:04/20/2016
            # alpha= 1 #4.3
         
        #Check if data is present
        # if len(h5_file['data']['imagesXY_2_Flea3']['Raw'][:]) != 0:
			# atoms = np.array(h5_file['data']['imagesXY_2_Flea3']['Raw'])[0]
			# probe = (np.array(h5_file['data']['imagesXY_2_Flea3']['Raw'])[1])
			# bckg = (np.array(h5_file['data']['imagesXY_2_Flea3']['Raw'])[2])
			# div = np.ma.masked_less_equal(np.ma.masked_invalid((atoms - bckg)/(probe-bckg)), 0.)
			# another_term = (probe-atoms)/(Isat)
			# OD = np.matrix(-alpha*np.log(div)+0*another_term)
			# return  atoms
			
			
            
			

# try:
with h5py.File(path) as h5_file:
	if '/data' in h5_file:
		
		atoms = np.array(h5_file['data']['imagesXY_1_Flea3']['Raw'][0])
		probe = (np.array(h5_file['data']['imagesXY_1_Flea3']['Raw'])[1])
		bckg = (np.array(h5_file['data']['imagesXY_1_Flea3']['Raw'])[2])
		div = np.ma.masked_less_equal(np.ma.masked_invalid((atoms - bckg)/(probe-bckg)), 0.)
		#another_term = (probe-atoms)/(Isat)
		OD = np.matrix(-np.log(div))
		print np.shape(atoms)
		# plt.imshow(_OD_,cmap = cm.gist_rainbow)
		# print ("success")
			
			
# except Exception as e:
    # print '%s' %e +  os.path.basename(path)
    # print '\n ********** Not Successful **********\n\n'