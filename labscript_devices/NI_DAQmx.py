#####################################################################
#                                                                   #
# /NI__DAQmx.py                                                  #
#                                                                   #
# Copyright 2013, Monash University                                 #
#                                                                   #
# This file is part of the module labscript_devices, in the         #
# labscript suite (see http://labscriptsuite.org), and is           #
# licensed under the Simplified BSD License. See the license.txt    #
# file in the root of the project for the full license.             #
#                                                                   #
#####################################################################

from labscript import LabscriptError, set_passed_properties, config
from labscript import IntermediateDevice, AnalogOut, StaticAnalogOut, DigitalOut, StaticDigitalOut, AnalogIn
from labscript_devices import labscript_device, BLACS_tab, BLACS_worker, runviewer_parser
import labscript_devices.NIBoard as parent

import numpy as np
import labscript_utils.h5_lock, h5py
import labscript_utils.properties

uint_map = {0:np.uint0, 8:np.uint8, 16:np.uint16, 32:np.uint32, 64:np.uint64}

@labscript_device
class NI_DAQmx(parent.NIBoard):
    """
    The "num_DO" initilization parameter is also interperted as follows
    0 -> np.uint0
    8 -> np.uint8
    16 -> np.uint16
    32 -> np.uint32
    
    This is because the JSON pasrser that writes this to file was unable
    to write these types
    """
    description = 'NI-DAQmx'
    
    @set_passed_properties(property_names = {
        "connection_table_properties":["clock_terminal", "num_AO", "range_AO", "static_AO", "num_DO", "static_DO", "num_AI", "clock_terminal_AI", "num_PFI", "DAQmx_waits_counter_bug_workaround"],
        "device_properties":["sample_rate_AO", "sample_rate_DO", "mode_AI"]}
        )
    def __init__(self, name, parent_device,
                 clock_terminal=None,
                 num_AO=0,
                 sample_rate_AO=1000,
                 range_AO=[-10.0,10.0],
                 static_AO=False,
                 num_DO=0,
                 static_DO=False,
                 sample_rate_DO=1000,
                 num_AI=0,
                 clock_terminal_AI=None,
                 mode_AI='labscript',
                 num_PFI=0,
                 DAQmx_waits_counter_bug_workaround=False,
                 **kwargs):
        """
        clock_termanal does not need to be specified for static outout
        """
        parent.NIBoard.__init__(self, name, parent_device, call_parents_add_device=False, **kwargs)

        if (clock_terminal is None) and not (static_AO and static_DO):
            raise LabscriptError("Clock terminal must be specified for dynamic outputs")

        # IBS: Now these are just defined at __init__ time
        self.allowed_children = []
        if num_AI > 0: self.allowed_children += [AnalogIn]
        if num_AO > 0 and static_AO: self.allowed_children += [StaticAnalogOut]
        if num_AO > 0 and not static_AO: self.allowed_children += [AnalogOut]
        if num_DO > 0 and static_DO: self.allowed_children += [StaticDigitalOut]
        if num_DO > 0 and not static_DO: self.allowed_children += [DigitalOut]
                
        self.num_AO = num_AO
        self.num_DO = num_DO
        self.static_DO = static_DO
        self.static_AO = static_AO
        self.clock_terminal = clock_terminal
        self.range_AO = range_AO
        if num_DO in uint_map.keys():
            self.dtype_DO = uint_map[num_DO]
        else:
            raise LabscriptError("%s number of DO channels must be one of (0,8,16,32)."%num_DO)
            
        self.num_AI = num_AI
        self.clock_terminal_AI = clock_terminal_AI
        self.num_PFI = num_PFI
        
        # Currently these two pieces of information are not independentally
        # used, but they could be if we wanted to independentaly trigger
        # the AO and DO ports
        self.clock_limit = np.minimum(sample_rate_AO, sample_rate_DO)
        
        # This is to instruct the wait monitor device to:
        # a) in labscript compilation: Use an 0.1 second duration for the wait
        # monitor trigger instead of a shorter one
        # b) In the BLACS waits worker process: skip the initial rising edge.
        # These are to work around what seems to be a bug in DAQmx. The initial
        #rising edge is not supposed to be detected, and clearly pulses of less
        # than 0.1 seconds ought to be detectable. However this workaround fixes
        # things for the affected devices, currenly the NI USB 6229 on NI DAQmx 15.0.
        self.DAQmx_waits_counter_bug_workaround = DAQmx_waits_counter_bug_workaround
        # Now call this to get the clock right
        self.parent_device.add_device(self)

    def generate_code(self, hdf5_file):

        IntermediateDevice.generate_code(self, hdf5_file)
        analogs = {}
        digitals = {}
        inputs = {}
        for device in self.child_devices:
            # TODO loop over allowed children rather than this case-by-case code
            if isinstance(device,AnalogOut) or isinstance(device,StaticAnalogOut):
                analogs[device.connection] = device
            elif isinstance(device,DigitalOut) or isinstance(device,StaticDigitalOut):
                digitals[device.connection] = device
            elif isinstance(device,AnalogIn):
                inputs[device.connection] = device
            else:
                raise Exception('Got unexpected device.')
        
        clockline = self.parent_device
        pseudoclock = clockline.parent_device
        times = pseudoclock.times[clockline]
        
        if  self.static_AO:
            analog_out_table = np.empty((1,len(analogs)), dtype=np.float32)
        else:
            analog_out_table = np.empty((len(times),len(analogs)), dtype=np.float32)
        analog_connections = analogs.keys()
        analog_connections.sort()
        analog_out_attrs = []
        for i, connection in enumerate(analog_connections):
            output = analogs[connection]
            if any(output.raw_output > self.range_AO[1] )  or any(output.raw_output < self.range_AO[0] ):
                # Bounds checking:
                raise LabscriptError('%s %s '%(output.description, output.name) +
                                  'can only have values between %e and %e Volts, ' + 
                                  'the limit imposed by %s.'%(self.range_AO[0], self.range_AO[1], self.name))
            if self.static_AO:
                 analog_out_table[0,i] = output.static_value
            else:
                analog_out_table[:,i] = output.raw_output
            analog_out_attrs.append(self.MAX_name +'/'+connection)
        
        input_connections = inputs.keys()
        input_connections.sort()
        input_attrs = []
        acquisitions = []
        for connection in input_connections:
            input_attrs.append(self.MAX_name+'/'+connection)
            for acq in inputs[connection].acquisitions:
                acquisitions.append((connection,acq['label'],acq['start_time'],acq['end_time'],acq['wait_label'],acq['scale_factor'],acq['units']))
        # The 'a256' dtype below limits the string fields to 256
        # characters. Can't imagine this would be an issue, but to not
        # specify the string length (using dtype=str) causes the strings
        # to all come out empty.
        acquisitions_table_dtypes = [('connection','a256'), ('label','a256'), ('start',float),
                                     ('stop',float), ('wait label','a256'),('scale factor',float), ('units','a256')]
        acquisition_table= np.empty(len(acquisitions), dtype=acquisitions_table_dtypes)
        for i, acq in enumerate(acquisitions):
            acquisition_table[i] = acq
        
        digital_out_table = []
        if digitals:
            if self.static_DO:
                digital_out_table = self.convert_bools_to_bytes(digitals.static_value)
            else:
                digital_out_table = self.convert_bools_to_bytes(digitals.values())
            
        grp = self.init_device_group(hdf5_file)
        if all(analog_out_table.shape): # Both dimensions must be nonzero
            grp.create_dataset('ANALOG_OUTS',compression=config.compression,data=analog_out_table)
            self.set_property('analog_out_channels', ', '.join(analog_out_attrs), location='device_properties')
        if len(digital_out_table): # Table must be non empty
            grp.create_dataset('DIGITAL_OUTS',compression=config.compression,data=digital_out_table)
            self.set_property('digital_lines', '/'.join((self.MAX_name,'port0','line0:%d'%(self.num_DO-1))), location='device_properties')
        if len(acquisition_table): # Table must be non empty
            grp.create_dataset('ACQUISITIONS',compression=config.compression,data=acquisition_table)
            self.set_property('analog_in_channels', ', '.join(input_attrs), location='device_properties')

        # I think this miscounts AO/DO/AI devices allowing me to have an odd 
        # number of a subset?
        if len(self.child_devices) % 2:
            raise LabscriptError('%s %s must have an even numer of analog outputs '%(self.description, self.name) +
                             'in order to guarantee an even total number of samples, which is a limitation of the DAQmx library. ' +
                             'Please add a dummy output device or remove an output you\'re not using, so that there are an even number of outputs. Sorry, this is annoying I know :).')


import time

from blacs.tab_base_classes import Worker, define_state
from blacs.tab_base_classes import MODE_MANUAL, MODE_TRANSITION_TO_BUFFERED, MODE_TRANSITION_TO_MANUAL, MODE_BUFFERED  
from blacs.device_base_class import DeviceTab

@BLACS_tab
class NI__DAQmxTab(DeviceTab):
    def initialise_GUI(self):
        # pull the following information out of the connection table        
        connection_object = self.settings['connection_table'].find_by_name(self.device_name)
        connection_table_properties = connection_object.properties
                
        # Capabilities
        num = {
            'num_AO': connection_table_properties["num_AO"],
            'num_DO': connection_table_properties["num_DO"],
            'num_PFI': connection_table_properties["num_PFI"]}
        
        base_units = {'AO':'V'}
        base_min = {'AO':connection_table_properties["range_AO"][0]}
        base_max = {'AO':connection_table_properties["range_AO"][1]}
        base_step = {'AO':0.1}
        base_decimals = {'AO':3}
        
        # Create the AO output objects
        # TODO: search through defined limits and fill if provided
        ao_prop = {}
        for i in range(num['num_AO']):
            ao_prop['ao%d'%i] = {'base_unit':base_units['AO'],
                                 'min':base_min['AO'],
                                 'max':base_max['AO'],
                                 'step':base_step['AO'],
                                 'decimals':base_decimals['AO']
                                }
        
        do_prop = {}
        for i in range(num['num_DO']):
            do_prop['port0/line%d'%i] = {}
                    
        # Create the output objects    
        self.create_analog_outputs(ao_prop)
        
        # Create widgets for analog outputs only
        dds_widgets,ao_widgets,do_widgets = self.auto_create_widgets()
        
        # now create the digital output objects
        self.create_digital_outputs(do_prop)

        # manually create the digital output widgets so they are grouped separately
        do_widgets = self.create_digital_widgets(do_prop)
        
        def do_sort(channel):
            flag = channel.replace('port0/line','')
            flag = int(flag)
            return '%02d'%(flag)
                    
        # and auto place the widgets in the UI
        self.auto_place_widgets(("Analog Outputs",ao_widgets),("Digital Outputs",do_widgets,do_sort))
        
        # Store the Measurement and Automation Explorer (MAX) name
        self.MAX_name = str(self.settings['connection_table'].find_by_name(self.device_name).BLACS_connection)
        
        # Create and set the primary worker
        self.create_worker("main_worker",Ni_DAQmxWorker,{'MAX_name':self.MAX_name, 'limits': [base_min['AO'],base_max['AO']], 'num':num})
        self.primary_worker = "main_worker"
        
        # using workaround? Default to False for backward compat with old connection table h5 files:
        DAQmx_waits_counter_bug_workaround = connection_table_properties.get("DAQmx_waits_counter_bug_workaround", False)
        self.create_worker("wait_monitor_worker",Ni_DAQmxWaitMonitorWorker,
                           {'MAX_name':self.MAX_name,
                            'DAQmx_waits_counter_bug_workaround': DAQmx_waits_counter_bug_workaround})
        self.add_secondary_worker("wait_monitor_worker")
        
        if connection_table_properties["num_AI"] > 0:
            self.create_worker("acquisition_worker",Ni_DAQmxAcquisitionWorker,{'MAX_name':self.MAX_name})
            self.add_secondary_worker("acquisition_worker")

        # Set the capabilities of this device
        self.supports_remote_value_check(False)
        self.supports_smart_programming(False) 
    
@BLACS_worker
class Ni_DAQmxWorker(Worker):
    def init(self):
        exec 'from PyDAQmx import Task, DAQmxGetSysNIDAQMajorVersion, DAQmxGetSysNIDAQMinorVersion, DAQmxGetSysNIDAQUpdateVersion, DAQmxResetDevice' in globals()
        exec 'from PyDAQmx.DAQmxConstants import *' in globals()
        exec 'from PyDAQmx.DAQmxTypes import *' in globals()
        global pylab; import pylab
        global numpy; import numpy
        global h5py; import labscript_utils.h5_lock, h5py

        # check version of PyDAQmx
        major = uInt32()
        minor = uInt32()
        patch = uInt32()
        DAQmxGetSysNIDAQMajorVersion(major)
        DAQmxGetSysNIDAQMinorVersion(minor)
        DAQmxGetSysNIDAQUpdateVersion(patch)

        if major.value == 14 and minor.value < 2:
            version_exception_message = 'There is a known bug with buffered shots using NI DAQmx v14.0.0. This bug does not exist on v14.2.0. You are currently using v%d.%d.%d. Please ensure you upgrade to v14.2.0 or higher.'%(major.value, minor.value, patch.value)
            raise Exception(version_exception_message)

        import zprocess.locking
        import socket
        
        # Setup lock for NIDAQmx_calls on this machine
        key = socket.gethostname() + '-NI_DAQ_API'
        self.NIDAQ_API_lock = zprocess.locking.Lock(key)
        
        with self.NIDAQ_API_lock:
            # Reset Device
            DAQmxResetDevice(self.MAX_name)
            
            # Create task
            self.ao_task = Task()
            self.ao_read = int32()
            self.ao_data = numpy.zeros((self.num['num_AO'],), dtype=numpy.float64)
            
            # Create DO task:
            self.do_task = Task()
            self.do_read = int32()
            self.do_data = numpy.zeros(self.num['num_DO'],dtype=numpy.uint8)
            
            self.setup_static_channels()            
            
            # DAQmx Start Code        
            self.ao_task.StartTask()
            self.do_task.StartTask()  
        
    def setup_static_channels(self):
        #setup AO channels
        for i in range(self.num['num_AO']): 
            self.ao_task.CreateAOVoltageChan(self.MAX_name+"/ao%d"%i,"",self.limits[0],self.limits[1],DAQmx_Val_Volts,None)
        
        # TODO: Currently labscript only supports one DO port, easy to add more
        # by passing a suitable structure of DO ports
        # I verified above that num['num_DO'] is a factor of 8
        for i in range(self.num['num_DO']/8):
            self.do_task.CreateDOChan(self.MAX_name+"/port0/line%d:%d"%(8*i,8*i+7),"", DAQmx_Val_ChanForAllLines)
        
        # currently do not allow direct access to PFI ports.  In the future can refer to NU_USB6346 code for an example

                
    def shutdown(self):        
        self.ao_task.StopTask()
        self.ao_task.ClearTask()
        self.do_task.StopTask()
        self.do_task.ClearTask()
        
    def program_manual(self,front_panel_values):
        for i in range(self.num['num_AO']):
            self.ao_data[i] = front_panel_values['ao%d'%i]
        self.ao_task.WriteAnalogF64(1,True,1,DAQmx_Val_GroupByChannel,self.ao_data,byref(self.ao_read),None)
        
        for i in range(self.num['num_DO']):
            self.do_data[i] = front_panel_values['port0/line%d'%i]
        self.do_task.WriteDigitalLines(1,True,1,DAQmx_Val_GroupByChannel,self.do_data,byref(self.do_read),None)
     
        # TODO: return coerced/quantised values
        return {}
        
    def transition_to_buffered(self,device_name,h5file,initial_values,fresh):
        # Store the initial values in case we have to abort and restore them:
        self.initial_values = initial_values
            
        with h5py.File(h5file,'r') as hdf5_file:
            group = hdf5_file['devices/'][device_name]
            device_properties = labscript_utils.properties.get(hdf5_file, device_name, 'device_properties')
            connection_table_properties = labscript_utils.properties.get(hdf5_file, device_name, 'connection_table_properties')
            clock_terminal = connection_table_properties['clock_terminal']
            self.static_AO = connection_table_properties['static_AO']
            self.static_DO = connection_table_properties['static_DO']
            h5_data = group.get('ANALOG_OUTS')
            if h5_data:
                self.buffered_using_analog = True
                ao_channels = device_properties['analog_out_channels']
                # We use all but the last sample (which is identical to the
                # second last sample) in order to ensure there is one more
                # clock tick than there are samples. The 6733 requires this
                # to determine that the task has completed.
                ao_data = np.array(h5_data,dtype=float64)
            else:
                self.buffered_using_analog = False
                
            h5_data = group.get('DIGITAL_OUTS')
            if h5_data:
                self.buffered_using_digital = True
                do_channels = device_properties['digital_lines']
                # See comment above for ao_channels
                do_bitfield = numpy.array(h5_data,dtype=numpy.uint32)
            else:
                self.buffered_using_digital = False
                
        final_values = {} 
        with self.NIDAQ_API_lock:
            # We must do digital first, so as to make sure the manual mode task is stopped, or reprogrammed, by the time we setup the AO task
            # this is because the clock_terminal PFI must be freed!
            if self.buffered_using_digital:
                # Expand each bitfield int into self.num['num_DO']
                # individual ones and zeros:
                do_write_data = numpy.zeros((do_bitfield.shape[0], self.num['num_DO']),dtype=numpy.uint8)
                for i in range(self.num['num_DO']):
                    do_write_data[:,i] = (do_bitfield & (1 << i)) >> i
                    
                self.do_task.StopTask()
                self.do_task.ClearTask()
                self.do_task = Task()
                do_read = int32()
                self.do_task.CreateDOChan(do_channels,"",DAQmx_Val_ChanPerLine)
                
                if self.static_DO:
                    self.do_task.StartTask()
                    self.do_task.WriteDigitalLines(1,True,10.0,DAQmx_Val_GroupByChannel,do_write_data,do_read,None)
                else:
                    # We use all but the last sample (which is identical to the
                    # second last sample) in order to ensure there is one more
                    # clock tick than there are samples. The 6733 requires this
                    # to determine that the task has completed.

                    do_write_data = do_write_data[:-1,:]
                    self.do_task.CfgSampClkTiming(
                                    clock_terminal,
                                    device_properties['sample_rate_DO'],
                                    DAQmx_Val_Rising,
                                    DAQmx_Val_FiniteSamps,
                                    do_write_data.shape[0]
                                    )
                    self.do_task.WriteDigitalLines(
                                    do_write_data.shape[0],
                                    False,
                                    10.0,
                                    DAQmx_Val_GroupByScanNumber,
                                    do_write_data,
                                    do_read,
                                    None)
                    self.do_task.StartTask()
                
                for i in range(self.num['num_DO']):
                    final_values['port0/line%d'%i] = do_write_data[-1,i]
            else:
                # We still have to stop the task to make the 
                # clock flag available for buffered analog output, or the wait monitor:
                self.do_task.StopTask()
                self.do_task.ClearTask()
                
            if self.buffered_using_analog:
                self.ao_task.StopTask()
                self.ao_task.ClearTask()
                self.ao_task = Task()
                ao_read = int32()
                self.ao_task.CreateAOVoltageChan(ao_channels,"",self.limits[0],self.limits[1],DAQmx_Val_Volts,None)

                if self.static_AO:
                    self.ao_task.StartTask()
                    self.ao_task.WriteAnalogF64(1, True, 10.0, DAQmx_Val_GroupByChannel, ao_data, ao_read, None)
                else:
                    # We use all but the last sample (which is identical to the
                    # second last sample) in order to ensure there is one more
                    # clock tick than there are samples. The 6733 requires this
                    # to determine that the task has completed.
                    ao_data = ao_data[:-1,:]
    
                    self.ao_task.CfgSampClkTiming(
                                    clock_terminal,
                                    device_properties['sample_rate_AO'],
                                    DAQmx_Val_Rising,
                                    DAQmx_Val_FiniteSamps, 
                                    ao_data.shape[0]
                                    )   
                    self.ao_task.WriteAnalogF64(
                                    ao_data.shape[0],
                                    False,
                                    10.0,
                                    DAQmx_Val_GroupByScanNumber,
                                    ao_data,
                                    ao_read,
                                    None)
                    self.ao_task.StartTask()   
                
                # Final values here are a dictionary of values, keyed by channel:
                channel_list = [channel.split('/')[1] for channel in ao_channels.split(', ')]
                for channel, value in zip(channel_list, ao_data[-1,:]):
                    final_values[channel] = value
            else:
                # we should probabaly still stop the task (this makes it easier to setup the task later)
                self.ao_task.StopTask()
                self.ao_task.ClearTask()
                
        return final_values
        
    def transition_to_manual(self,abort=False):
        # if aborting, don't call StopTask since this throws an
        # error if the task hasn't actually finished!

        # We are throwing an error here involving not enough triggers (buffer non-empty).  Maybe
        # use the functions
        # int32 __CFUNC DAQmxGetWriteCurrWritePos(TaskHandle taskHandle, uInt64 *data);
        # int32 __CFUNC DAQmxGetWriteTotalSampPerChanGenerated(TaskHandle taskHandle, uInt64 *data);
        # 
        # to establish the size of the buffer
        #

        if self.buffered_using_analog:
            if not abort:
                if not self.static_AO:
                    CurrentPos = uInt64()
                    TotalSamples = uInt64()
                    self.ao_task.GetWriteCurrWritePos(CurrentPos)
                    self.ao_task.GetWriteTotalSampPerChanGenerated(TotalSamples)
                    
                    self.logger.debug('NI_DAQmx Closing AO: at Sample %d of %d'%(CurrentPos.value, TotalSamples.value))

                self.ao_task.StopTask()
            self.ao_task.ClearTask()
        if self.buffered_using_digital:
            if not abort:
                if not self.static_DO:
                    CurrentPos = uInt64()
                    TotalSamples = uInt64()
                    self.do_task.GetWriteCurrWritePos(CurrentPos)
                    self.do_task.GetWriteTotalSampPerChanGenerated(TotalSamples)
    
                    self.logger.debug('NI_DAQmx Closing DO: at Sample %d of %d'%(CurrentPos.value, TotalSamples.value))
        
                self.do_task.StopTask()
            self.do_task.ClearTask()
        
        
        self.ao_task = Task()
        self.do_task = Task()
        self.setup_static_channels()
        self.ao_task.StartTask()
        self.do_task.StartTask()
        if abort:
            # Reprogram the initial states:
            self.program_manual(self.initial_values)
            
        return True
        
    def abort_transition_to_buffered(self):
        # TODO: untested
        return self.transition_to_manual(True)
        
    def abort_buffered(self):
        # TODO: untested
        return self.transition_to_manual(True)    

        
class Ni_DAQmxAcquisitionWorker(Worker):
    def init(self):
        #exec 'import traceback' in globals()
        exec 'from PyDAQmx import Task' in globals()
        exec 'from PyDAQmx.DAQmxConstants import *' in globals()
        exec 'from PyDAQmx.DAQmxTypes import *' in globals()
        global h5py; import labscript_utils.h5_lock, h5py
        global numpy; import numpy
        global threading; import threading
        global zprocess; import zprocess
        global logging; import logging
        global time; import time
                
        self.task_running = False
        self.daqlock = threading.Condition()
        # Channel details
        self.channels = []
        self.rate = 1000.
        self.samples_per_channel = 1000
        self.ai_start_delay = 25e-9
        self.h5_file = ""
        self.buffered_channels = []
        self.buffered_rate = 0
        self.buffered = False
        self.buffered_data = None
        self.buffered_data_list = []
        
        self.task = None
        self.abort = False
        
        # And event for knowing when the wait durations are known, so that we may use them
        # to chunk up acquisition data:
        self.wait_durations_analysed = zprocess.Event('wait_durations_analysed')
        
        self.daqmx_read_thread = threading.Thread(target=self.daqmx_read)
        self.daqmx_read_thread.daemon = True
        self.daqmx_read_thread.start()

    def shutdown(self):
        if self.task_running:
            self.stop_task()
        
    def daqmx_read(self):
        logger = logging.getLogger('BLACS.%s_%s.acquisition.daqmxread'%(self.device_name,self.worker_name))
        logger.info('Starting')
        #first_read = True
        try:
            while True:
                with self.daqlock:
                    logger.debug('Got daqlock')
                    while not self.task_running:
                        logger.debug('Task isn\'t running. Releasing daqlock and waiting to reacquire it.')
                        self.daqlock.wait()
                    #logger.debug('Reading data from analogue inputs')
                    if self.buffered:
                        chnl_list = self.buffered_channels
                    else:
                        chnl_list = self.channels
                    try:
                        error = "Task did not return an error, but it should have"
                        acquisition_timeout = 5
                        error = self.task.ReadAnalogF64(self.samples_per_channel,
                                                        acquisition_timeout,
                                                        DAQmx_Val_GroupByChannel,
                                                        self.ai_data,
                                                        self.samples_per_channel*len(chnl_list),
                                                        byref(self.ai_read),
                                                        None)
                        # logger.debug('Reading complete')
                        if error is not None and error != 0:
                            if error < 0:
                                raise Exception(error)
                            if error > 0:
                                logger.warning(error)
                    except Exception as e:
                        logger.exception('acquisition error')
                        if self.abort:
                            # If an abort is in progress, then we expect an exception here. Don't raise it.
                            logger.debug('ignoring error since an abort is in progress.')
                            # Ensure the next iteration of this while loop
                            # doesn't happen until the task is restarted.
                            # The thread calling self.stop_task() is
                            # also setting self.task_running = False
                            # right about now, but we don't want to rely
                            # on it doing so in time. Doing it here too
                            # avoids a race condition.
                            self.task_running = False
                            continue
                        else:
                            # Error was likely a timeout error...some other device might be bing slow 
                            # transitioning to buffered, so we haven't got our start trigger yet. 
                            # Keep trying until task_running is False:
                            continue
                # send the data to the queue
                if self.buffered:
                    # rearrange ai_data into correct form
                    data = numpy.copy(self.ai_data)
                    self.buffered_data_list.append(data)
                    
                    #if len(chnl_list) > 1:
                    #    data.shape = (len(chnl_list),self.ai_read.value)              
                    #    data = data.transpose()
                    #self.buffered_data = numpy.append(self.buffered_data,data,axis=0)
                else:
                    pass
                    # Todo: replace this with zmq pub plus a broker somewhere so things can subscribe to channels
                    # and get their data without caring what process it came from. For the sake of speed, this
                    # should use the numpy buffer interface and raw zmq messages, and not the existing event system
                    # that zprocess has.
                    # self.result_queue.put([self.t0,self.rate,self.ai_read.value,len(self.channels),self.ai_data])
                    # self.t0 = self.t0 + self.samples_per_channel/self.rate
        except:
            message = traceback.format_exc()
            logger.error('An exception happened:\n %s'%message)
            #self.to_parent.put(['error', message])
            # TODO: Tell the GUI process that this has a problem some how (status check?)
            
    def setup_task(self):
        self.logger.debug('setup_task')
        #DAQmx Configure Code
        with self.daqlock:
            self.logger.debug('setup_task got daqlock')
            if self.task:
                self.task.ClearTask()##
            if self.buffered:
                chnl_list = self.buffered_channels
                rate = self.buffered_rate
            else:
                chnl_list = self.channels
                rate = self.rate
                
            if len(chnl_list) < 1:
                return

            if rate < 1000:
                self.samples_per_channel = int(rate)
            else:
                self.samples_per_channel = 1000
                
            if rate < 1e2:
                self.buffer_per_channel = 1000
            elif rate < 1e4:
                self.buffer_per_channel = 10000
            elif rate < 1e6:
                self.buffer_per_channel = 100000
            else:
                self.buffer_per_channel = 1000000
                
            try:
                self.task = Task()
            except Exception as e:
                self.logger.error(str(e))
            self.ai_read = int32()
            self.ai_data = numpy.zeros((self.samples_per_channel*len(chnl_list),), dtype=numpy.float64)   
            
            for chnl in chnl_list:
                self.task.CreateAIVoltageChan(chnl,"",DAQmx_Val_RSE,-10.0,10.0,DAQmx_Val_Volts,None)
                
            self.task.CfgSampClkTiming("", rate, DAQmx_Val_Rising, DAQmx_Val_ContSamps, self.samples_per_channel)
            
            # Suggested in https://github.com/jlblancoc/mrpt/blob/master/libs/hwdrivers/src/CNationalInstrumentsDAQ.cpp            
            self.task.CfgInputBuffer(self.buffer_per_channel)            
            
            # Currently no difference
            if self.buffered:
                if self.mode_AI == 'gated':
                    # setup gated mode
                    self.task.CfgDigEdgeStartTrig(self.clock_terminal, DAQmx_Val_Rising)
                else:
                    #set up start on digital trigger
                    self.task.CfgDigEdgeStartTrig(self.clock_terminal, DAQmx_Val_Rising)
            
            #DAQmx Start Code
            self.task.StartTask()
            # TODO: Need to do something about the time for buffered acquisition. Should be related to when it starts (approx)
            # How do we detect that?
            self.t0 = time.time() - time.timezone
            self.task_running = True
            self.daqlock.notify()
        self.logger.debug('finished setup_task')
        
    def stop_task(self):
        self.logger.debug('stop_task')
        with self.daqlock:
            self.logger.debug('stop_task got daqlock')
            if self.task_running:
                self.task_running = False
                # ignore errors that are thrown by stop task?  such as buffer full errors?
                # Add a try here at stop task?
                self.task.StopTask()
                self.task.ClearTask()
            self.daqlock.notify()
        self.logger.debug('finished stop_task')
        
    def transition_to_buffered(self,device_name,h5file,initial_values,fresh):
        # TODO: Do this line better!
        self.device_name = device_name
        
        self.logger.debug('transition_to_buffered')
        # stop current task
        self.stop_task()
        
        self.buffered_data_list = []
        
        # Save h5file path (for storing data later!)
        self.h5_file = h5file
        # read channels, acquisition rate, etc from H5 file
        h5_chnls = []
        with h5py.File(h5file,'r') as hdf5_file:
            device_properties = labscript_utils.properties.get(hdf5_file, device_name, 'device_properties')
            connection_table_properties = labscript_utils.properties.get(hdf5_file, device_name, 'connection_table_properties')

        self.clock_terminal = connection_table_properties['clock_terminal_AI']
        self.mode_AI = device_properties['mode_AI']
        
        if 'analog_in_channels' in device_properties:
            h5_chnls = device_properties['analog_in_channels'].split(', ')
            self.buffered_rate = device_properties['sample_rate_AI']
        else:
           self.logger.debug("no input channels")
        # combine static channels with h5 channels (using a set to avoid duplicates)
        self.buffered_channels = set(h5_chnls)
        self.buffered_channels.update(self.channels)
        # Now make it a sorted list:
        self.buffered_channels = sorted(list(self.buffered_channels))
        
        # setup task (rate should be from h5 file)
        # Possibly should detect and lower rate if too high, as h5 file doesn't know about other acquisition channels?
        
        if self.buffered_rate <= 0:
            self.buffered_rate = self.rate
        
        self.buffered = True
        if len(self.buffered_channels) == 1:
            self.buffered_data = numpy.zeros((1,),dtype=numpy.float64)
        else:
            self.buffered_data = numpy.zeros((1,len(self.buffered_channels)),dtype=numpy.float64)
        
        self.setup_task()   

        return {}
    
    def transition_to_manual(self,abort=False):    
        self.logger.debug('transition_to_static')
        # Stop acquisition (this should really be done on a digital edge, but that is for later! Maybe use a Counter)
        # Set the abort flag so that the acquisition thread knows to expect an exception in the case of an abort:
        #
        # TODO: This is probably bad because it shortly get's overwritten to False
        # However whether it has an effect depends on whether daqmx_read thread holds the daqlock 
        # when self.stop_task() is called
        self.abort = abort 
        self.stop_task()
        # Reset the abort flag so that unexpected exceptions are still raised:        
        self.abort = False
        self.logger.info('transitioning to static, task stopped')
        # save the data acquired to the h5 file
        if not abort:
            with h5py.File(self.h5_file,'a') as hdf5_file:
                data_group = hdf5_file['data']
                data_group.create_group(self.device_name)

            dtypes = [(chan.split('/')[-1],numpy.float32) for chan in sorted(self.buffered_channels)]

            start_time = time.time()
            if self.buffered_data_list:
                self.buffered_data = numpy.zeros(len(self.buffered_data_list)*1000,dtype=dtypes)
                for i, data in enumerate(self.buffered_data_list):
                    data.shape = (len(self.buffered_channels),self.ai_read.value)              
                    for j, (chan, dtype) in enumerate(dtypes):
                        self.buffered_data[chan][i*1000:(i*1000)+1000] = data[j,:]
                    if i % 100 == 0:
                        self.logger.debug( str(i/100) + " time: "+str(time.time()-start_time))
                self.extract_measurements(self.device_name)
                self.logger.info('data written, time taken: %ss' % str(time.time()-start_time))
            
            self.buffered_data = None
            self.buffered_data_list = []
            
            # Send data to callback functions as requested (in one big chunk!)
            #self.result_queue.put([self.t0,self.rate,self.ai_read,len(self.channels),self.ai_data])
        
        # return to previous acquisition mode
        self.buffered = False
        self.setup_task()
        
        return True
        
    def extract_measurements(self, device_name):
        self.logger.debug('extract_measurements')
        with h5py.File(self.h5_file,'a') as hdf5_file:
            waits_in_use = len(hdf5_file['waits']) > 0
        if waits_in_use:
            # There were waits in this shot. We need to wait until the other process has
            # determined their durations before we proceed:
            self.wait_durations_analysed.wait(self.h5_file)

        with h5py.File(self.h5_file,'a') as hdf5_file:
            if waits_in_use:
                # get the wait start times and durations
                waits = hdf5_file['/data/waits']
                wait_times = waits['time']
                wait_durations = waits['duration']
            try:
                acquisitions = hdf5_file['/devices/'+device_name+'/ACQUISITIONS']
            except:
                # No acquisitions!
                return
            try:
                measurements = hdf5_file['/data/traces']
            except:
                # Group doesn't exist yet, create it:
                measurements = hdf5_file.create_group('/data/traces')
            for connection,label,start_time,end_time,wait_label,scale_factor,units in acquisitions:
                if waits_in_use:
                    # add durations from all waits that start prior to start_time of acquisition
                    start_time += wait_durations[(wait_times < start_time)].sum()
                    # compare wait times to end_time to allow for waits during an acquisition
                    end_time += wait_durations[(wait_times < end_time)].sum()
                start_index = numpy.ceil(self.buffered_rate*(start_time-self.ai_start_delay))
                end_index = numpy.floor(self.buffered_rate*(end_time-self.ai_start_delay))
                # numpy.ceil does what we want above, but float errors can miss the equality
                if self.ai_start_delay + (start_index-1)/self.buffered_rate - start_time > -2e-16:
                    start_index -= 1
                # We actually want numpy.floor(x) to yield the largest integer < x (not <=) 
                if end_time - self.ai_start_delay - end_index/self.buffered_rate < 2e-16:
                    end_index -= 1
                acquisition_start_time = self.ai_start_delay + start_index/self.buffered_rate
                acquisition_end_time = self.ai_start_delay + end_index/self.buffered_rate
                times = numpy.linspace(acquisition_start_time, acquisition_end_time, 
                                       end_index-start_index+1,
                                       endpoint=True)
                values = self.buffered_data[connection][start_index:end_index+1]
                dtypes = [('t', numpy.float64),('values', numpy.float32)]
                data = numpy.empty(len(values),dtype=dtypes)
                data['t'] = times
                data['values'] = values
                measurements.create_dataset(label, data=data)
            
    def abort_buffered(self):
        #TODO: test this
        return self.transition_to_manual(True)
        
    def abort_transition_to_buffered(self):
        #TODO: test this
        return self.transition_to_manual(True)   
    
    def program_manual(self,values):
        return {}
    
class Ni_DAQmxWaitMonitorWorker(Worker):
    def init(self):
        exec 'import ctypes' in globals()
        exec 'from PyDAQmx import Task' in globals()
        exec 'from PyDAQmx.DAQmxConstants import *' in globals()
        exec 'from PyDAQmx.DAQmxTypes import *' in globals()
        global h5py; import labscript_utils.h5_lock, h5py
        global numpy; import numpy        
        global threading; import threading
        global zprocess; import zprocess
        global logging; import logging
        global time; import time
    
        self.task_running = False
        self.daqlock = threading.Lock() # not sure if needed, access should be serialised already
        self.h5_file = None
        self.task = None
        self.abort = False
        self.all_waits_finished = zprocess.Event('all_waits_finished',type='post')
        self.wait_durations_analysed = zprocess.Event('wait_durations_analysed',type='post')
    
    def shutdown(self):
        self.logger.info('Shutdown requested, stopping task')
        if self.task_running:
            self.stop_task()    
    
    #def read_one_half_period(self, timeout, readarray = numpy.empty(1)):
    def read_one_half_period(self, timeout, save=True):
        readarray = numpy.empty(1)
        try:
            with self.daqlock:
                self.acquisition_task.ReadCounterF64(1, timeout, readarray, len(readarray), ctypes.c_long(1), None)
                if save:
                    self.half_periods.append(readarray[0])
            return readarray[0]
        except Exception:
            if self.abort:
                raise
            # otherwise, it's a timeout:
            return None
    
    def wait_for_edge(self, timeout=None, save=True):
        if timeout is None:
            while True:
                half_period = self.read_one_half_period(1, save)
                if half_period is not None:
                    return half_period
        else:
            return self.read_one_half_period(timeout, save)
                
    def daqmx_read(self):
        logger = logging.getLogger('BLACS.%s_%s.read_thread'%(self.device_name, self.worker_name))
        logger.info('Starting')
        with self.kill_lock:
            try:
                # Wait for the end of the first pulse indicating the start of the experiment:
                if self.DAQmx_waits_counter_bug_workaround:
                    ignored = self.wait_for_edge(save=False)
                current_time = pulse_width = self.wait_for_edge()
                # alright, we're now a short way into the experiment.
                for wait in self.wait_table:
                    # How long until this wait should time out?
                    timeout = wait['time'] + wait['timeout'] - current_time
                    timeout = max(timeout, 0) # ensure non-negative
                    # Wait that long for the next pulse:
                    half_period = self.wait_for_edge(timeout)
                    # Did the wait finish of its own accord?
                    if half_period is not None:
                        # It did, we are now at the end of that wait:
                        current_time = wait['time']
                        # Wait for the end of the pulse:
                        current_time += self.wait_for_edge()
                    else:
                        # It timed out. Better trigger the clock to resume!.
                        self.send_resume_trigger(pulse_width)
                        # Wait for it to respond to that:
                        self.wait_for_edge()
                        # Alright, *now* we're at the end of the wait.
                        current_time = wait['time']
                        # And wait for the end of the pulse:
                        current_time += self.wait_for_edge()

                # Inform any interested parties that waits have all finished:
                self.all_waits_finished.post(self.h5_file)
            except Exception:
                if self.abort:
                    return
                else:
                    raise
    
    def send_resume_trigger(self, pulse_width):
        written = int32()
        # go high:
        self.timeout_task.WriteDigitalLines(1,True,1,DAQmx_Val_GroupByChannel,numpy.ones(1, dtype=numpy.uint8),byref(written),None)
        assert written.value == 1
        # Wait however long we observed the first pulse of the experiment to be:
        time.sleep(pulse_width)
        # go high:
        self.timeout_task.WriteDigitalLines(1,True,1,DAQmx_Val_GroupByChannel,numpy.ones(1, dtype=numpy.uint8),byref(written),None)
        assert written.value == 1
        
    def stop_task(self):
        self.logger.debug('stop_task')
        with self.daqlock:
            self.logger.debug('stop_task got daqlock')
            if self.task_running:
                self.task_running = False
                self.acquisition_task.StopTask()
                self.acquisition_task.ClearTask()
                self.timeout_task.StopTask()
                self.timeout_task.ClearTask()
        self.logger.debug('finished stop_task')
        
    def transition_to_buffered(self,device_name,h5file,initial_values,fresh):
        self.logger.debug('transition_to_buffered')
        # Save h5file path (for storing data later!)
        self.h5_file = h5file
        self.is_wait_monitor_device = False # Will be set to true in a moment if necessary
        self.logger.debug('setup_task')
        with h5py.File(h5file, 'r') as hdf5_file:
            dataset = hdf5_file['waits']
            if len(dataset) == 0:
                # There are no waits. Do nothing.
                self.logger.debug('There are no waits, not transitioning to buffered')
                self.waits_in_use = False
                self.wait_table = numpy.zeros((0,))
                return {}
            self.waits_in_use = True
            acquisition_device = dataset.attrs['wait_monitor_acquisition_device']
            acquisition_connection = dataset.attrs['wait_monitor_acquisition_connection']
            timeout_device = dataset.attrs['wait_monitor_timeout_device']
            timeout_connection = dataset.attrs['wait_monitor_timeout_connection']
            self.wait_table = dataset[:]
        # Only do anything if we are in fact the wait_monitor device:
        if timeout_device == device_name or acquisition_device == device_name:
            if not timeout_device == device_name and acquisition_device == device_name:
                raise NotImplementedError("Ni_DAQmx worker must be both the wait monitor timeout device and acquisition device." +
                                          "Being only one could be implemented if there's a need for it, but it isn't at the moment")
            
            self.is_wait_monitor_device = True
            # The counter acquisition task:
            self.acquisition_task = Task()
            acquisition_chan = '/'.join([self.MAX_name,acquisition_connection])
            self.acquisition_task.CreateCISemiPeriodChan(acquisition_chan, '', 100e-9, 200, DAQmx_Val_Seconds, "")    
            self.acquisition_task.CfgImplicitTiming(DAQmx_Val_ContSamps, 1000)
            self.acquisition_task.StartTask()
            # The timeout task:
            self.timeout_task = Task()
            timeout_chan = '/'.join([self.MAX_name,timeout_connection])
            self.timeout_task.CreateDOChan(timeout_chan,"",DAQmx_Val_ChanForAllLines)
            self.task_running = True
                
            # An array to store the results of counter acquisition:
            self.half_periods = []
            self.read_thread = threading.Thread(target=self.daqmx_read)
            # Not a daemon thread, as it implements wait timeouts - we need it to stay alive if other things die.
            self.read_thread.start()
            self.logger.debug('finished transition to buffered')
            
        return {}
    
    def transition_to_manual(self,abort=False):
        self.logger.debug('transition_to_static')
        self.abort = abort
        self.stop_task()
        # Reset the abort flag so that unexpected exceptions are still raised:        
        self.abort = False
        self.logger.info('transitioning to static, task stopped')
        # save the data acquired to the h5 file
        if not abort:
            if self.is_wait_monitor_device and self.waits_in_use:
                # Let's work out how long the waits were. The absolute times of each edge on the wait
                # monitor were:
                edge_times = numpy.cumsum(self.half_periods)
                # Now there was also a rising edge at t=0 that we didn't measure:
                edge_times = numpy.insert(edge_times,0,0)
                # Ok, and the even-indexed ones of these were rising edges.
                rising_edge_times = edge_times[::2]
                # Now what were the times between rising edges?
                periods = numpy.diff(rising_edge_times)
                # How does this compare to how long we expected there to be between the start
                # of the experiment and the first wait, and then between each pair of waits?
                # The difference will give us the waits' durations.
                resume_times = self.wait_table['time']
                # Again, include the start of the experiment, t=0:
                resume_times =  numpy.insert(resume_times,0,0)
                run_periods = numpy.diff(resume_times)
                wait_durations = periods - run_periods
                waits_timed_out = wait_durations > self.wait_table['timeout']
            with h5py.File(self.h5_file,'a') as hdf5_file:
                # Work out how long the waits were, save em, post an event saying so 
                dtypes = [('label','a256'),('time',float),('timeout',float),('duration',float),('timed_out',bool)]
                data = numpy.empty(len(self.wait_table), dtype=dtypes)
                if self.is_wait_monitor_device and self.waits_in_use:
                    data['label'] = self.wait_table['label']
                    data['time'] = self.wait_table['time']
                    data['timeout'] = self.wait_table['timeout']
                    data['duration'] = wait_durations
                    data['timed_out'] = waits_timed_out
                if self.is_wait_monitor_device:
                    hdf5_file.create_dataset('/data/waits', data=data)
            if self.is_wait_monitor_device:
                self.wait_durations_analysed.post(self.h5_file)
        
        return True
    
    def abort_buffered(self):
        #TODO: test this
        return self.transition_to_manual(True)
        
    def abort_transition_to_buffered(self):
        #TODO: test this
        return self.transition_to_manual(True)   
    
    def program_manual(self,values):
        return {}

 
    
@runviewer_parser
class RunviewerClass(parent.RunviewerClass):

    def __init__(self, *args, **kwargs):
        parent.RunviewerClass.__init__(self, *args, **kwargs)
