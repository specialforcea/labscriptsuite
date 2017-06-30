#####################################################################
#                                                                   #
# /__init__.py                                                      #
#                                                                   #
# Copyright 2013, Monash University                                 #
#                                                                   #
# This file is part of the program mise, in the labscript suite     #
# (see http://labscriptsuite.org), and is licensed under the        #
# Simplified BSD License. See the license.txt file in the root of   #
# the project for the full license.                                 #
#                                                                   #
#####################################################################

from __future__ import division
import os
from numbers import Number


from zprocess import zmq_get
from labscript_utils.labconfig import LabConfig, config_prefix
import socket

__version__ = '1.0.0'

_exp_config = LabConfig(os.path.join(config_prefix,'%s.ini'%socket.gethostname()))

class MiseParameter(object):
    def __init__(self, min, max, mutation_rate=None, log=False, initial = None):
    
        # Check for valid min and max
        if not isinstance(min, Number) or not isinstance(max, Number) or not max > min:
            raise ValueError('MiseParameter must have unequal numerical min and max values, with min < max.')
         
        # Set default mutation rate if unset:   
        if mutation_rate is None:
            mutation_rate = (max-min)/10
            
        # Check for valid mutation rate
        if not isinstance(mutation_rate ,Number):
            raise ValueError('mutation_rate must be a number')
            
        # Check for valid initial value:
        if initial is not None:
            if not isinstance(min, Number) or not isinstance(max, Number) or not max > min:
                raise ValueError('Initial must be a number between min and max.')
            
        # I'm being so anal about error checking and types here
        # because I really want the error to be raised in runmanager if
        # the user gives invalid input, rather than in mise.
        
        self.min = float(min)
        self.max = float(max)
        self.mutation_rate = abs(float(mutation_rate))
        self.log = bool(log)
        self.initial = None if initial is None else float(initial)
        
def report_fitness(individual_id, fitness, host='localhost'):
    port = int(_exp_config.get('ports','mise'))
    fitness = float(fitness)
    individual_id = int(individual_id)
    data = ('from lyse', individual_id, fitness)
    success, message = zmq_get(port, host, data, timeout=2)
    if not success:
        raise RuntimeError(message)

