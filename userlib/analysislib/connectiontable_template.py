from __future__ import division
from lyse import *
from time import time
from scipy.ndimage import *
from scipy.optimize import *
from matplotlib.widgets import Cursor, Button, RadioButtons
import matplotlib.pyplot as plt
import os
import pandas as pd
import numpy as np

plt.rcParams['font.size'] = 16
plt.rcParams['figure.figsize'] = 8, 10

class cursors_ROI(object):
    def __init__(self, z, x = None, y = None, n_ROI=1):
        """
        Shows the calculated OD and
        allows user to set ROI and BCK
        coords. These are saved in the tmp_ROI
        array which can be accessed by single
        shot routines for use.

        Input : z; an OD 2D array.
                x, y coordinates are optional.
                n_ROI; number of ROI to be saved.
        Output: ROI, BCK; 1D arrays

        """
        if x==None:
            self.x=np.arange(z.shape[0])
        else:
            self.x=x
        if y==None:
            self.y=np.arange(z.shape[1])
        else:
            self.y=y
        self.z=z
        self.n_ROI = n_ROI
        global clickCounter
        clickCounter = 0
        self.ROIcoords = []
        self.BCKcoords = []
        self.F_attr, self.mF_attr = [2], [2]
        self.fig = plt.figure(figsize=(10, 9), frameon=False)
        #Layout for subplots:
        self.fig.subplots_adjust(left = 0.08, bottom = 0.08, right = 0.93,
                                        top = 0.93, wspace = 0.50, hspace = 0.50)
        self.shot = plt.subplot2grid((5,5), (0,0), rowspan = 4, colspan = 5)
        self.shot.pcolormesh(self.z, cmap = 'RdBu_r', vmin=-0.2, vmax=np.amax(self.z))
        self.shot.autoscale(1, 'both', 1)
        plt.title('Please RESET when Done')
        ax = plt.gca()
        ax.invert_yaxis()
        self.OD_subplot = [] #plt.subplot2grid((9,5), (0,3), rowspan = 3, colspan = 2)

        #Cursor widget
        cursor = Cursor(self.shot, useblit = True, color = 'k', linewidth = 2)
        #Button widget
        but_ax  = plt.subplot2grid((5,5), (4,4), colspan = 1)
        reset_button   = Button(but_ax,  'Reset')
        but_ax2 = plt.subplot2grid((5,5), (4,2), colspan = 2)
        set_ROI_button = Button(but_ax2, 'Set ROI')
        #Attribute button widget
        F_label_ax = plt.subplot2grid((5,5), (4,0), colspan = 1)
        F_label_radio = RadioButtons(F_label_ax, ('$F = 2$', '$F = 1$'), activecolor = 'deepskyblue')
        mF_label_ax = plt.subplot2grid((5,5), (4,1), colspan = 1)
        mF_label_radio = RadioButtons(mF_label_ax, ('$m_F = -2$', '$m_F = -1$', '$m_F = 0$', 
                                                                     '$m_F = 1$', '$m_F = 2$'), activecolor='crimson')
        # Widget List
        self._widgets = [cursor, reset_button, set_ROI_button, mF_label_radio, F_label_radio]

        #Connect events
        reset_button.on_clicked(self.clear_box)
        set_ROI_button.on_clicked(self.get_coords)
        F_label_radio.on_clicked(self.get_F_label)
        mF_label_radio.on_clicked(self.get_mF_label)
        self.fig.canvas.mpl_connect('button_press_event', self.click)

    def show_subplots(self, event):
        """Shows subplots"""
        for pl in [self.OD_subplot]:
            if len(pl.lines) > 0:
                pl.legend()
        plt.draw()

    def clear_box(self, event):
        """Clears ROI and BCK"""
        self.ROIcoords  = []
        self.BCKcoords  = []
        self.shot.lines    = []
        self.OD_subplot   = []
        global clickCounter
        clickCounter = 0
        plt.draw()

    def click(self, event):
        """
        What to do when a click on the figure happens:
            1. Set cursor
            2. Get coordinates
        """
        global clickCounter
        all_ROI_a_clicks, all_ROI_b_clicks = (1 + 4*np.arange(self.n_ROI),
                                              2 + 4*np.arange(self.n_ROI))
        all_BCK_a_clicks, all_BCK_b_clicks = (3 + 4*np.arange(self.n_ROI),
                                              4 + 4*np.arange(self.n_ROI))
        if clickCounter < 4*self.n_ROI:
            if event.inaxes == self.shot:
                clickCounter += 1
                xpos = np.argmin(np.abs(event.xdata - self.x))
                ypos = np.argmin(np.abs(event.ydata - self.y))
                if event.button:
                    if clickCounter in all_ROI_a_clicks or clickCounter in all_ROI_b_clicks:
                        #Plot ROI cursor
                        self.shot.axvline(self.x[xpos], color = 'r', lw = 2)
                        self.shot.axhline(self.y[ypos], color = 'r', lw = 2)
                        self.ROIcoords.append([xpos, ypos])
                        if clickCounter in all_ROI_a_clicks:
                            print 'ROI_a'
                        elif clickCounter in all_ROI_b_clicks:
                            print 'ROI_b'
                    elif clickCounter in all_BCK_a_clicks or clickCounter in all_BCK_b_clicks:
                        #Plot BCK cursor
                        self.shot.axvline(self.x[xpos], color = 'y', lw = 2)
                        self.shot.axhline(self.y[ypos], color = 'y', lw = 2)
                        self.BCKcoords.append([xpos, ypos])
                        if clickCounter in all_BCK_a_clicks:
                            print 'BCK_a'
                        elif clickCounter in all_BCK_b_clicks:
                            print 'BCK_b'
        elif clickCounter == 4*self.n_ROI:
            print 'Getting coordinates...'
            gathered_data = np.array([self.F_attr, self.mF_attr, self.ROIcoords, self.BCKcoords], dtype=object)
            np.save(r'C:\labscript_suite\userlib\analysislib\yuchen_analysis\ROI_temp.npy', gathered_data)
            print 'Data saved: ROI_temp.npy'
        plt.draw()

    def counter_tracker(self):
        global clickCounter
        self._counter = clickCounter
        return self._counter

    def get_coords(self, event):
        cBCK, cROI = self.BCKcoords, self.ROIcoords
        return cBCK, cROI

    def get_F_label(self, label):
        F_label = {'$F = 1$': 1, '$F = 2$': 2}
        self.F_attr[0] = F_label[label]
        return F_label[label]
        
    def get_mF_label(self, label):
        mF_label = {'$m_F = -2$': -2, '$m_F = -1$': -1, '$m_F = 0$': 0,  '$m_F = 1$': 1, '$m_F = 2$': 2}
        self.mF_attr[0] = mF_label[label]
        return mF_label[label]

        

# Time stamp
print '\nRunning %s' % os.path.basename(__file__)
t = time()

# Load dataframe
df = data()
path = df['filepath'].values[:,0][0]

def raw_to_OD(fpath):
    with h5py.File(fpath) as h5_file:
        image_group = {}
        if False:#'/data/imagesXY_1_Flea3' in h5_file:
            image_group['imagesXY_1_Flea3'] = 'z-TOF'
            Isat = 297          # In counts // Paco:04/21/2016
            alpha = 1 #1.645
        if  '/data/imagesXY_2_Flea3' in h5_file:
            image_group['imagesXY_2_Flea3'] = 'z-insitu'
            Isat = 395      # In counts // Paco:04/20/2016
            alpha= 1 #4.3
        if '/data/imagesYZ_1_Flea3' in h5_file:
            image_group['imagesYZ_1_Flea3'] = 'x-insitu'
            Isat = 2248     # In counts // Paco:05/06/2016
            alpha = 1 #0.441
        atoms, probe, bckg, div, calculated_OD = {}, {}, {}, {}, {}
        for appended, id in image_group.iteritems():
            # Check if data is present
            if len(h5_file['data'][appended]['Raw'][:]) != 0:
                atoms[id] = (np.array(h5_file['data'][appended]['Raw'])[1])
                probe[id] = (np.array(h5_file['data'][appended]['Raw'])[0])
                bckg[id] =  (np.array(h5_file['data'][appended]['Raw'])[3])
                div[id] = np.ma.masked_invalid((atoms[id] - bckg[id])/(probe[id]-bckg[id]))
                div[id] = np.ma.masked_less_equal(div[id], 0.)
                another_term = (probe[id]-atoms[id])/(Isat)
                calculated_OD[id] = np.matrix(-alpha*np.log(div[id])+0*another_term)
        return calculated_OD

_OD_ = raw_to_OD(path)
for stored, shot in _OD_.iteritems():
    ODarr = np.array(shot)
    fig = cursors_ROI(ODarr, n_ROI=1)
    clk = fig.counter_tracker()
    print 'Select ROI and BCK'