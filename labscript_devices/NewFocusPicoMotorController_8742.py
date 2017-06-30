#####################################################################
#                                                                   #
# labscript_devices/NewFocusPicoMotorController.py                  #
#                                                                   #
# Copyright 2016, Joint Quantum Institute                           #
#                                                                   #
# This file is part of labscript_devices, in the labscript suite    #
# (see http://labscriptsuite.org), and is licensed under the        #
# Simplified BSD License. See the license.txt file in the root of   #
# the project for the full license.                                 #
#                                                                   #
#####################################################################

from labscript_devices import labscript_device, BLACS_tab, BLACS_worker, runviewer_parser
from labscript import StaticAnalogQuantity, Device, LabscriptError, set_passed_properties
import numpy as np

class NewFocus8742Motor(StaticAnalogQuantity):
    #For Relative and Target Positions
    minval=-2147483648
    maxval=2147483647
    description = 'PicoMotor'
    
@labscript_device
class NewFocusPicoMotorController_8742(Device):
    allowed_children = [NewFocus8742Motor]
    generation = 0
    
    @set_passed_properties(
    )
                                             
    def __init__(self, name, 
                 host = "", port=23, **kwargs):
            
        Device.__init__(self, name, None, None, None)
        self.BLACS_connection = '%s' %(host)
                
        
    def generate_code(self, hdf5_file):
        data_dict = {}
        for motor in self.child_devices:
            # Call these functions to finalise the motor, they are standard functions of all subclasses of Output:
            ignore = motor.get_change_times()
            motor.make_timeseries([])
            motor.expand_timeseries()
            connection = [int(s) for s in motor.connection.split() if s.isdigit()][0]
            value = motor.raw_output[0]
            if not motor.minval <= value <= motor.maxval:
                # error, out of bounds
                raise LabscriptError('%s %s has value out of bounds. Set value: %s Allowed range: %s to %s.'%(motor.description,motor.name,str(value),motor(motor.minval),str(motor.maxval)))
            if not connection > 0 and not connection < 5:
                # error, invalid connection number
                raise LabscriptError('%s %s has invalid connection number: %s'%(motor.description,motor.name,str(motor.connection)))
            data_dict[str(motor.connection)] = value
        dtypes = [(conn, int) for conn in data_dict]
        data_array = np.zeros(1, dtype=dtypes)
        for conn in data_dict:
            data_array[0][conn] = data_dict[conn] 
        grp = hdf5_file.create_group('/devices/'+self.name)
        grp.create_dataset('static_values', data=data_array)
        
import time

from blacs.tab_base_classes import Worker, define_state
from blacs.tab_base_classes import MODE_MANUAL, MODE_TRANSITION_TO_BUFFERED, MODE_TRANSITION_TO_MANUAL, MODE_BUFFERED  

from blacs.device_base_class import DeviceTab

@BLACS_tab
class NewFocusPicoMotorControllerTab(DeviceTab):
    def initialise_GUI(self):
        # Capabilities
        self.base_units = 'steps'
        self.base_min = -2147483648
        self.base_step = 10
        self.base_decimals = 0
        
        self.device = self.settings['connection_table'].find_by_name(self.device_name)
        self.num_motors = len(self.device.child_list)
        
        # Create the AO output objects
        ao_prop = {}
        for child_name in self.device.child_list:
            motor_type = self.device.child_list[child_name].device_class
            connection = self.device.child_list[child_name].parent_port
            if motor_type == "NewFocus8742Motor":
                base_max = 2147483647
            else:
                base_max = 2147483647
            
            ao_prop[connection] = {'base_unit':self.base_units,
                                   'min':self.base_min,
                                   'max':base_max,
                                   'step':self.base_step,
                                   'decimals':self.base_decimals
                                  }
                                
        # Create the output objects    
        self.create_analog_outputs(ao_prop)        
        # Create widgets for output objects
        dds_widgets,ao_widgets,do_widgets = self.auto_create_widgets()
        # and auto place the widgets in the UI
        self.auto_place_widgets(("Target Position",ao_widgets))
        
        # Store the address
        self.host = str(self.settings['connection_table'].find_by_name(self.device_name).BLACS_connection)
        
        # Set the capabilities of this device
        self.supports_remote_value_check(False)
        self.supports_smart_programming(False) 
    
    def initialise_workers(self):
        # Create and set the primary worker
        self.create_worker("main_worker",NewFocusPicoMotorControllerWorker,{'host':self.host})
        self.primary_worker = "main_worker"

@BLACS_worker    
class NewFocusPicoMotorControllerWorker(Worker):
    def init(self):
        global socket; import socket
        global zprocess; import zprocess
        global h5py; import labscript_utils.h5_lock, h5py
        global time; import time
        
        self.port = 23
        
    def check_connectivity(self, host):
        try:
            response = self.initialise_sockets(self.host, self.port)
        except:
            raise Exception("sockets are not initialised")
        print response
        if '8742' in response:
            return True
        else:
            raise Exception('invalid response from host: ' + str(response))
        
    def initialise_sockets(self, host, port):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        assert port, 'No port number supplied.'
        assert host, 'No hostname supplied.'
        s.settimeout(5)
        s.connect((host, int(port)))
        time.sleep(0.1)
        s.send("*IDN?"+'\n')
        time.sleep(0.1)
        response = s.recv(1024)
        time.sleep(0.005)
        s.close()
        return response
        
    def program_manual(self, front_panel_values):
        try:
            self.check_connectivity(self.host)
            # For each motor
            for axis in range(1,5):
                self.program_static(axis, int(front_panel_values["%s" %axis]))
                time.sleep(0.01)
            return {}
        except:
            raise Exception("server not responding, check connectivity failed")

    
    def program_static(self, axis, value):
        # Target Position ONLY
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        time.sleep(0.1)
        assert self.port, 'No port number supplied.'
        assert self.host, 'No hostname supplied.'
        s.settimeout(5)
        s.connect((self.host, int(self.port)))
        command = "xxPAnn"
        axis_command = command.replace("xx", str(axis))
        full_command = axis_command.replace("nn", str(value))
        print full_command
        s.send(full_command +'\n')
        time.sleep(0.1)
        print s.recv(1024)
        time.sleep(0.005)
        s.close()
    
    def transition_to_buffered(self,device_name,h5file,initial_values,fresh):
        return_data = {}
        with h5py.File(h5file) as hdf5_file:
            group = hdf5_file['/devices/'+device_name]
            if 'static_values' in group:
                data = group['static_values'][:][0]
        self.program_manual(data)
        
        for motor in data.dtype.names:
            return_data[motor] = data[motor]

        return return_data
    
    def transition_to_manual(self):
        #self.program_manual(self.initial_values)
        return True
    
    def abort_buffered(self):
        return True
        
    def abort_transition_to_buffered(self):
        return True
    
    def shutdown(self):
        self.s.close()
            
