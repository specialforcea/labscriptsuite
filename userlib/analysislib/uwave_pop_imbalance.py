from __future__ import division
from lyse import *
from time import time
from matplotlib import pyplot as plt
from common.OD_handler import ODShot
from analysislib.spinor.aliases import *
import os
import pandas as pd
import numpy as np
import matplotlib.gridspec as gridspec
from matplotlib import cm
from matplotlib.patches import Circle, Wedge, Rectangle

""" plot_imb_gauge based on the matplotlib gauge drawing from
    http://nicolasfauchereau.github.io/climatecode/posts/drawing-a-gauge-with-matplotlib/ 
    which I found really awesome"""

# Parameters
pixel_size = 5.6e-6/3.44# Divided by Magnification Factor
            # 5.6e-6/5.33 for z in situ                        # Yuchen and Paco: 08/19/2016
            #5.6e-6/3.44 for z TOF                           # Yuchen and Paco: 08/19/2016
            #5.6e-6/2.72 for x-in situ                        # Paco: 05/06/2016
            
# Time stamp
print '\nRunning %s' % os.path.basename(__file__)
t = time()

# Load dataframe
run = Run(path)

# Methods
def print_time(text):
    print 't = %6.3f : %s' % ((time()-t), text)

def u_wave_raw_to_OD(fpath):
    with h5py.File(fpath) as h5_file:
        image_group = {}
        # Safe to assume uwave lock is *only* along z-insitu
        if  '/data/imagesXY_2_Flea3' in h5_file:
            image_group['imagesXY_2_Flea3'] = 'z-insitu'
            Isat = 395      # In counts // Paco:04/20/2016
            alpha= 1 #4.3
        atoms1, atoms2, probe, bckg, div1, div2, OD1, OD2 = [], [], [], [], [] ,[], [], []
        # Check if data is present
        if len(h5_file['data']['imagesXY_2_Flea3']['Raw'][:]) != 0:
            probe= (np.array(h5_file['data']['imagesXY_2_Flea3']['Raw'])[0])
            atoms1 = (np.array(h5_file['data']['imagesXY_2_Flea3']['Raw'])[1])
            atoms2 = (np.array(h5_file['data']['imagesXY_2_Flea3']['Raw'])[2])
            bckg =  (np.array(h5_file['data']['imagesXY_2_Flea3']['Raw'])[3])
            div1 = np.ma.masked_less_equal(np.ma.masked_invalid((atoms1 - bckg)/(probe-bckg)), 0.)
            div2 = np.ma.masked_less_equal(np.ma.masked_invalid((atoms2 - bckg)/(probe-bckg)), 0.)
            another_term1, another_term2 = (probe-atoms1)/(Isat),  (probe-atoms2)/(Isat)
            OD1, OD2 = (np.matrix(-alpha*np.log(div1)+0*another_term1), 
                              np.matrix(-alpha*np.log(div2)+0*another_term2))
        return OD1, OD2

def degree_range(n): 
    start = np.linspace(0,180,n+1, endpoint=True)[0:-1]
    end = np.linspace(0,180,n+1, endpoint=True)[1::]
    mid_points = start + ((end-start)/2.)
    return np.c_[start, end], mid_points

def rot_text(ang): 
    rotation = np.degrees(np.radians(ang) * np.pi / np.pi - np.radians(90))
    return rotation
    
def plot_imb_gauge(labels=['-1.0','-0.5','0.0','0.5','1.0'], \
          colors='jet_r', arrow=1, title='', fname=False):  
    """ some sanity checks first """
    N = len(labels)
    if arrow > N: 
        raise Exception("\n\nThe category ({}) is greated than \
        the length\nof the labels ({})".format(arrow, N))
    """if colors is a string, we assume it's a matplotlib colormap
    and we discretize in N discrete colors """
    if isinstance(colors, str):
        cmap = cm.get_cmap(colors, N)
        cmap = cmap(np.arange(N))
        colors = cmap[::-1,:].tolist()
    if isinstance(colors, list): 
        if len(colors) == N:
            colors = colors[::-1]
        else: 
            raise Exception("\n\nnumber of colors {} not equal \
            to number of categories{}\n".format(len(colors), N))
    """ begins the plotting """
    fig = plt.figure(figsize=(8, 5), frameon=False)
    gs = gridspec.GridSpec(2, 2, width_ratios=[1,1], height_ratios=[1,1])
    ax0 = plt.subplot(gs[0])
    ax0.imshow(_ODa_, vmin=0., vmax=1.0, cmap='Reds_r', aspect='auto', interpolation='none')
    ax1 = plt.subplot(gs[1])
    ax1.imshow(_ODb_, vmin=0., vmax=1.0, cmap='Blues_r', aspect='auto', interpolation='none')
    ax2 = plt.subplot(gs[2])
    ang_range, mid_points = degree_range(N)
    labels = labels[::-1]
    """plots the sectors and the arcs """
    patches = []
    for ang, c in zip(ang_range, colors): 
        # sectors
        patches.append(Wedge((0.,0.), .4, *ang, facecolor='w', lw=2))
        # arcs
        patches.append(Wedge((0.,0.), .4, *ang, width=0.10, facecolor=c, lw=2, alpha=0.5))
    [ax2.add_patch(p) for p in patches]
    """set the labels"""
    for mid, lab in zip(mid_points, labels): 
        ax2.text(0.35 * np.cos(np.radians(mid)), 0.35 * np.sin(np.radians(mid)), lab, \
            horizontalalignment='center', verticalalignment='center', fontsize=14, \
            rotation = rot_text(mid))
    """set the bottom banner and the title"""
    r = Rectangle((-0.4,-0.1),0.8,0.1, facecolor='w', lw=2)
    ax2.add_patch(r) 
    ax2.text(0, -0.05, title, horizontalalignment='center', \
         verticalalignment='center', fontsize=16)
    """ plots the arrow """
    pos = mid_points[abs(arrow - N)]
    ax2.arrow(0, 0, 0.225 * np.cos(np.radians(pos)), 0.225 * np.sin(np.radians(pos)), \
                    width=0.02, head_width=0.06, head_length=0.1, fc='k', ec='k')
    ax2.add_patch(Circle((0, 0), radius=0.02, facecolor='k'))
    ax2.add_patch(Circle((0, 0), radius=0.01, facecolor='w', zorder=11))
    """ removes frame and ticks, and makes axis equal and tight """
    ax2.set_frame_on(False)
    ax2.axes.set_xticks([])
    ax2.axes.set_yticks([])
    ax2.axis('equal')
    plt.tight_layout()
    plt.show()
        
        
# Main
try:
    with h5py.File(path) as h5_file:
        if '/data' in h5_file:
        # Get OD
            _ODa_, _ODb_ = u_wave_raw_to_OD(path)
            ODa, ODb = ODShot(_ODa_), ODShot(_ODb_)
            Fa, mFa, _ROIa_, BCKa_a =  ODa.get_ROI(sniff=False, get_background=False) 
            Fb, mFb, _ROIb_, BCKb_a =  ODb.get_ROI(sniff=False, get_background=False) 
            BCKa, BCKb = np.mean(BCKa_a)*np.ones(_ROIa_.shape), np.mean(BCKb_a)*np.ones(_ROIb_.shape)
            # Compute number imbalance
            Na, Nb = (np.sum((_ROIa_-BCKa)/sigma0)*pixel_size**2), (np.sum((_ROIb_-BCKb)/sigma0)*pixel_size**2)
            N_imb = Na-Nb
            run.save_result(('Imbalance_(' + str(Fa) +',' +str(mFa)+')'), N_imb)
            plot_imb_gauge(labels=['-1.0','-0.5','0.0','0.5','1.0'], colors='RdBu', arrow=5, title='Imbalance', fname=False)
except Exception as e:
    print '%s' %e +  os.path.basename(path)
    print '\n ********** Not Successful **********\n\n'
            
            
            
            

            
