#####################################################################
#                                                                   #
# linear_coil_driver.py                                             #
#                                                                   #
# Copyright 2016, University of Maryland                            #
#                                                                   #
# This file is part of the labscript suite (see                     #
# http://labscriptsuite.org) and is licensed under the Simplified   #
# BSD License. See the license.txt file in the root of the project  #
# for the full license.                                             #
#                                                                   #
#####################################################################

from __future__ import division

from UnitConversionBase import *
from numpy import int16

class LinearVoltage(UnitConversion):
    base_unit = 'V'
    derived_units = ['Vs']

    def __init__(self, calibration_parameters=None):
        # These parameters are loaded from a globals.h5 type file automatically
        self.parameters = calibration_parameters

        # I[A] = slope * V[V] + shift
        # Saturates at saturation Volts
        self.parameters.setdefault('slope', 1) # A/V
        self.parameters.setdefault('shift', 0) # A
        self.parameters.setdefault('saturation', 10) # V

        UnitConversion.__init__(self,self.parameters)
        # We should probably also store some hardware limits here, and use them accordingly
        # (or maybe load them from a globals file, or specify them in the connection table?)

    def Vs_to_base(self,vscaled):
        #here is the calibration code that may use self.parameters
        volts = (vscaled - self.parameters['shift']) / self.parameters['slope']
        return volts

    def Vs_from_base(self,volts):
        volts = min(volts, self.parameters['saturation']) # FIXME this doesn't work with ndarrays
        vscaled = self.parameters['slope'] * volts + self.parameters['shift']
        return vscaled
