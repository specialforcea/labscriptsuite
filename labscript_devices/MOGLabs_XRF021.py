#####################################################################
#                                                                   #
# /NovaTechDDS9M.py                                                 #
#                                                                   #
# Copyright 2013, Monash University                                 #
#                                                                   #
# This file is part of the module labscript_devices, in the         #
# labscript suite (see http://labscriptsuite.org), and is           #
# licensed under the Simplified BSD License. See the license.txt    #
# file in the root of the project for the full license.             #
#                                                                   #
#####################################################################
from labscript_devices import runviewer_parser, labscript_device, BLACS_tab, BLACS_worker

from labscript import IntermediateDevice, DDS, StaticDDS, Device, config, LabscriptError, set_passed_properties
# from labscript_utils.unitconversions import NovaTechDDS9mFreqConversion, NovaTechDDS9mAmpConversion

import numpy as np
import labscript_utils.h5_lock, h5py
import labscript_utils.properties

import time
import socket
import select
import struct
import collections

# Handles communication with devices
class MOGDevice:
    serial = None
    def __init__(self,addr,port=None,timeout=1,check=True,debug=False):
        self._DEBUG = debug
        # is it a COM port?
        if addr.startswith('COM') or addr == 'USB':
            if port is not None: addr = 'COM%d'%port
            addr = addr.split(' ',1)[0]
            self.connection = addr
            self.is_usb = True
        else:
            if not ':' in addr:
                if port is None: port=7802
                addr = '%s:%d'%(addr,port)
            self.connection = addr
            self.is_usb = False
        self.reconnect(timeout,check)

    def reconnect(self,timeout=1,check=True):
        "Reestablish connection with unit"
        if hasattr(self,'dev'): self.dev.close()
        if self.is_usb:
            import serial
            self.dev = serial.Serial(self.connection, baudrate=115200, bytesize=8, parity='N', stopbits=1, timeout=timeout, writeTimeout=0)
        else:
            self.dev = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.dev.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.dev.settimeout(timeout)
            addr, port = self.connection.split(':')
            self.dev.connect((addr,int(port)))
        # check the connection?
        if check:
            try:
                self.info = self.ask('info')
                self.serial = self.ask('get,serial')
            except Exception as E:
                print '!',E
                raise RuntimeError('Device did not respond to query')

    def versions(self):
        verstr = self.ask('version')
        if verstr == 'Command not defined':
            raise RuntimeError('Incompatible firmware')
        # does the version string define components?
        vers = {}
        if ':' in verstr:
            # old versions are LF-separated, new are comma-separated
            tk = ',' if ',' in verstr else '\n'
            for l in verstr.split(tk):
                if l.startswith('OK'): continue
                n,v = l.split(':',2)
                v = v.strip()
                if ' ' in v: v = v.rsplit(' ',2)[1].strip()
                vers[n.strip()] = v
        else:
            # just the micro
            vers['UC'] = verstr.strip()
        return vers

    def cmd(self,cmd):
        "Send the specified command, and check the response is OK"
        self.flush()
        self.send(cmd)
        resp = self.recv()
        if resp.startswith('OK'):
            return resp
        else:
            raise RuntimeError(resp)

    def ask(self,cmd):
        "Send followed by receive"
        # check if there's any response waiting on the line
        self.flush()
        self.send(cmd)
        resp = self.recv().strip()
        if resp.startswith('ERR:'):
            raise RuntimeError(resp[4:].strip())
        return resp

    def ask_dict(self,cmd):
        "Send a request which returns a dictionary response"
        resp = self.ask(cmd)
        # might start with "OK"
        if resp.startswith('OK'): resp = resp[3:].strip()
        # expect a colon in there
        if not ':' in resp: raise RuntimeError('Response to "%s" not a dictionary'%cmd)
        # response could be comma-delimited (new) or newline-delimited (old)
        vals = collections.OrderedDict()
        for entry in resp.split(',' if ',' in resp else '\n'):
            name, val = entry.split(':')
            vals[name.strip()] = val.strip()
        return vals

    def ask_bin(self,cmd):
        "Send a request which returns a binary response"
        self.send(cmd)
        head = self.recv_raw(4)
        print repr(head)
        # is it an error message?
        if head == 'ERR:': raise RuntimeError(head+self.recv())
        datalen = struct.unpack('<L',head)[0]
        data = self.recv_raw(datalen)
        if len(data) != datalen: raise RuntimeError('Binary response block has incorrect length')
        return data

    def send(self,cmd):
        "Send command, appending newline if not present"
        if not cmd.endswith('\r\n'): cmd += '\r\n'
        self.send_raw(cmd)

    def has_data(self,timeout=0):
        if self.is_usb:
            if self.dev.inWaiting(): return True
            if timeout == 0: return False
            time.sleep(timeout)
            return self.dev.inWaiting > 0
        else:
            return len(select.select([self.dev],[],[],timeout)[0]) > 0

    def flush(self,buffer=256):
        while self.has_data():
            dat = self.recv(buffer)
            if self._DEBUG: print 'FLUSHED', repr(dat)

    def recv(self,buffer=256):
        "A somewhat robust multi-packet receive call"
        if self.is_usb:
            data = self.dev.readline(buffer)
            if len(data):
                t0 = self.dev.timeout
                self.dev.timeout = 0 if data.endswith('\r\n') else 0.1
                while True:
                    segment = self.dev.readline(buffer)
                    if len(segment) == 0: break
                    data += segment
                self.dev.timeout = t0
            if len(data) == 0: raise RuntimeError('timed out')
        else:
            data = self.dev.recv(buffer)
            timeout = 0 if data.endswith('\r\n') else 0.1
            while self.has_data(timeout):
                try:
                    segment = self.dev.recv(buffer)
                except IOError:
                    if len(data): break
                    raise
                data += segment
        if self._DEBUG: print '<<',len(data),repr(data)
        return data

    def send_raw(self,cmd):
        "Send, without appending newline"
        if self._DEBUG and len(cmd) < 256: print '>>',repr(cmd)
        if self.is_usb:
            return self.dev.write(cmd)
        else:
            return self.dev.send(cmd)

    def recv_raw(self,size):
        "Receive exactly 'size' bytes"
        buffer = ''
        while size > 0:
            if self.is_usb:
                chunk = self.dev.read(size)
            else:
                chunk = self.dev.recv(size)
            buffer += chunk
            size -= len(chunk)
        if self._DEBUG:
            print '<< RECV_RAW got', len(buffer)
            print '<<', repr(buffer)
        return buffer

    def set_timeout(self,val):
        if self.is_usb:
            old = self.dev.timeout
            self.dev.timeout = val
            return old
        else:
            old = self.dev.gettimeout()
            self.dev.settimeout(val)
            return old

    def set_get(self,name,val):
        "Set specified name and then query it"
        self.cmd('set,'+name+','+str(val)+'\n')
        actualval = self.ask('get,'+name)
        if self._DEBUG: print 'SET',name,'=',repr(val),repr(actualval)
        return actualval

    def config_net(self,addr,mask,gw,port,dhcp):
        "Set values associated with network"
        self.set_get('ipaddr',enquote(addr))
        self.set_get('ipmask',enquote(mask))
        self.set_get('ipgw',enquote(gw))
        self.set_get('ipport',port)
        self.set_get('dhcp',dhcp)

    def flash_upload(self,dest,data,callback=None):
        assert len(data) > 0
        # initiate command
        line = self.cmd("flash,%x,%s"%(len(data),dest))
        # wait for flash erase
        nblocks = len(data)//0x20000 + 1
        remaining = nblocks
        timeout = time.time() + nblocks
        while remaining > 0 and not 'FLASH ERASE COMPLETE' in line:
            tprev = time.time()
            if tprev > timeout: raise RuntimeError('Timeout during flash erase')
            try:
                line = self.recv().strip()
                # new firmware responds with progress
                remaining = int(line)
            except:
                # on timeout, or conversion error (assume 1 sec per block)
                dt = (time.time()-tprev)//1000
                if dt > 0: remaining = remaining - dt
            if callback is not None: callback(0,nblocks-remaining,nblocks)
        if callback is not None: callback(0,nblocks,nblocks)
        # upload data
        nblocks = len(data)
        if callback is not None: callback(1,0,nblocks)
        self.send_raw(data)
        # wait for data to be received
        remaining = nblocks
        buffer = ''
        while 1:
            try:
                if not '\n' in buffer: buffer = buffer + self.recv()
                line, buffer = buffer.split('\n',1)
                line = line.strip()
                if len(line) == 0: continue
                if 'FLASH UPLOAD COMPLETE' in line:
                    remaining = 0
                    break
                if not ',' in line:
                    raise RuntimeError(line)
                done = int(line.rsplit(',',1)[1])
                remaining = nblocks - done
                if callback is not None: callback(1,done,nblocks)
            except ValueError:
                raise RuntimeError(line)
            except Exception as E:
                raise
        if callback is not None: callback(1,nblocks,nblocks)

def discover_ethernet(port=7802):
    "Search local subnet for moglabs devices, returns a MOGDevice instance"
    # determine host IP
    myip = socket.gethostbyname_ex(socket.gethostname())[2][0]
    ### try to broadcast (UDP)
    print 'Broadcasting for devices'
    bcast = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    bcast.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    bcast.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    bcast.settimeout(0.1)
    bcast.bind(('', port))
    bcast.sendto(myip+'\n', ('<broadcast>', port))
    # look for replies
    found = []
    timeout = time.time()+2
    while time.time() < timeout:
        try:
            msg, origin = bcast.recvfrom(32)
            addr, remote_port = origin
        except socket.timeout:
            break
        # ignore local response
        if addr == myip: continue
        found.append(addr)
        print 'Got', addr
        yield addr
    ### try to brute force (TCP)
    baseip = myip.rsplit(".",1)[0] + '.'
    print 'Testing addresses in '+baseip+'*'
    for j in range(2,256):
        testip = baseip + str(j)
        if testip in found: continue
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.01)
            s.connect((testip, port))
            s.close()
            yield testip
        except IOError:
            continue
    raise StopIteration

def discover_usb(byname = True):
    "Search COM ports for compatible devices, returns a MOGDevice instance"
    import serial
    from serial.tools import list_ports
    for portinfo in list_ports.comports():
        if byname and not 'STM' in portinfo[1]:
            continue
        try:
            # is the connection valid?
            serial.Serial(portinfo[0])
        except Exception as E:
            print '!!', E, portinfo
        else:
            yield portinfo[0]
    raise StopIteration

def load_script(filename):
    with open(filename,"r") as f:
        for linenum, line in enumerate(f):
            # remove comments
            line = line.split('#',1)[0]
            # trim spaces
            line = line.strip()
            if len(line) == 0: continue
            # return this info
            yield linenum+1, line


@labscript_device
class MOGLabs_XRF021(IntermediateDevice):
    """
    This class is initilzed with the key word argument
    'update_mode' -- synchronous or asynchronous\
    'baud_rate',  -- operaiting baud rate
    'default_baud_rate' -- assumed baud rate at startup
    """

    description = 'XRF021'
    allowed_children = [DDS]
    clock_limit = 1000000 # Each instruction must take at least 1us in simple table mode

    @set_passed_properties(
        property_names = {'connection_table_properties': ['addr', 'port']}
        )
    def __init__(self, name, parent_device, addr=None, port=7802, **kwargs):

        IntermediateDevice.__init__(self, name, parent_device, **kwargs)
        # # Get a device objsect
        # dev = MOGDevice(addr, port)
        # # print 'Device info:', dev.ask('info')
        self.BLACS_connection = '%s,%s'%(addr, str(port))

    def add_device(self, device):
        Device.add_device(self, device)
        # Minimum frequency is 20MHz:
        device.frequency.default_value = 20e6

    def generate_code(self, hdf5_file):
        DDSs = {}
        for output in self.child_devices:
            # get channels like in Novatech
            try:
                prefix, channel = output.connection.split()
                channel = int(channel)
            except:
                raise LabscriptError('%s %s has invalid connection string: \'%s\'. '%(output.description,output.name,str(output.connection)) +
                                     'Format must be \'channel n\' with n from 0 to 4.')
            DDSs[channel] = output

        # for connection in DDSs:
        #     if connection in range(2):
        #         # Dynamic DDS
        #         dds = DDSs[connection]
        #         print(dds.frequency.scale_factor)
        #     else:
        #         raise LabscriptError('%s %s has invalid connection string: \'%s\'. '%(dds.description,dds.name,str(dds.connection)) +
        #                              'Format must be \'channel n\' with n from 0 to 4.')

        dtypes = [('freq%d'%i,np.uint32) for i in range(2)] + \
                 [('phase%d'%i,np.uint16) for i in range(2)] + \
                 [('amp%d'%i,np.uint16) for i in range(2)]

        clockline = self.parent_clock_line
        pseudoclock = clockline.parent_device
        times = pseudoclock.times[clockline]

        out_table = np.zeros(len(times),dtype=dtypes)
        out_table['freq0'].fill(20)
        out_table['freq1'].fill(20)

        for connection in range(2):
            if not connection in DDSs:
                continue
            dds = DDSs[connection]
            # The last two instructions are left blank, for BLACS
            # to fill in at program time.
            out_table['freq%d'%connection][:] = dds.frequency.raw_output
            out_table['amp%d'%connection][:] = dds.amplitude.raw_output
            out_table['phase%d'%connection][:] = dds.phase.raw_output

        grp = self.init_device_group(hdf5_file)
        grp.create_dataset('TABLE_DATA',compression=config.compression,data=out_table)

import time

from blacs.tab_base_classes import Worker, define_state
from blacs.tab_base_classes import MODE_MANUAL, MODE_TRANSITION_TO_BUFFERED, MODE_TRANSITION_TO_MANUAL, MODE_BUFFERED

from blacs.device_base_class import DeviceTab

@BLACS_tab
class MOGLabs_XRF021Tab(DeviceTab):
    def initialise_GUI(self):
        # Capabilities
        self.base_units =    {'freq':'MHz',          'amp':'dBm',   'phase':'Degrees'}
        self.base_min =      {'freq':20.0,           'amp':-50,       'phase':0}
        self.base_max =      {'freq':400.0, 'amp':7,       'phase':360}
        self.base_step =     {'freq':1.0,         'amp':1., 'phase':1}
        self.base_decimals = {'freq':6,             'amp':2,       'phase':3} # TODO: find out what the phase precision is!
        self.num_DDS = 2

        # Create DDS Output objects
        dds_prop = {}
        for i in range(self.num_DDS): # 4 is the number of DDS outputs on this device
            dds_prop['channel %d'%i] = {}
            for subchnl in ['freq', 'amp', 'phase']:
                dds_prop['channel %d'%i][subchnl] = {'base_unit':self.base_units[subchnl],
                                                     'min':self.base_min[subchnl],
                                                     'max':self.base_max[subchnl],
                                                     'step':self.base_step[subchnl],
                                                     'decimals':self.base_decimals[subchnl]
                                                    }
        # Create the output objects
        self.create_dds_outputs(dds_prop)
        # Create widgets for output objects
        dds_widgets,ao_widgets,do_widgets = self.auto_create_widgets()
        # and auto place the widgets in the UI
        self.auto_place_widgets(("DDS Outputs",dds_widgets))

        connection_object = self.settings['connection_table'].find_by_name(self.device_name)
        connection_table_properties = connection_object.properties

        self.addr = connection_table_properties['addr']
        self.port = connection_table_properties['port']

        # Create and set the primary worker
        self.create_worker("main_worker",MOGLabs_XRF021Worker,{'addr':self.addr,
                                                              'port': self.port})
        self.primary_worker = "main_worker"

        # Set the capabilities of this device
        self.supports_remote_value_check(True)
        self.supports_smart_programming(True)
        

@BLACS_worker
class MOGLabs_XRF021Worker(Worker):
    def init(self):
        global h5py; import labscript_utils.h5_lock, h5py
        self.smart_cache = {'TABLE_DATA': ''}

        # Get a device object
        self.dev = MOGDevice(self.addr, self.port)
        # info = dev.ask('info')
        # raise(info)
        # TODO wrap ask cmnds with error checking

        # Flush any junk from the buffer
        self.dev.flush()
        # and turn both channels on
        for i in range(2):
            self.dev.cmd('on,%d'%(i+1))

        #return self.get_current_values()

    def check_remote_values(self):
        # Get the currently output values:
        results = {}
        for i in range(2):
            results['channel %d'%i] = {}
            freq = float(self.dev.ask('FREQ,%d'%(i+1)).split()[0])
            amp = float(self.dev.ask('POW,%d'%(i+1)).split()[0])
            phase = float(self.dev.ask('PHASE,%d'%(i+1)).split()[0])

            results['channel %d'%i]['freq'] = freq
            results['channel %d'%i]['amp'] = amp
            results['channel %d'%i]['phase'] = phase
        # print(results)
        return results

    def program_manual(self,front_panel_values):
        # TODO: Optimise this so that only items that have changed are reprogrammed by storing the last programmed values
        # For each DDS channel,
        for i in range(2):
            # self.dev.cmd('FREQ,%d,20MHz'%(i+1))
            # self.dev.cmd('POW,%d,0 dBm'%(i+1))
            # self.dev.cmd('PHASE,%d,0deg'%(i+1))

            # and for each subchnl in the DDS,
            for subchnl in ['freq','amp','phase']:
                # print('f', front_panel_values['channel %d'%i][subchnl])
                self.program_static(i, subchnl,
                                    front_panel_values['channel %d'%i][subchnl])
        return self.check_remote_values()

    def program_static(self,channel,type,value):
        if type == 'freq':
            # print(value)
            command = 'FREQ,%d,%fMHz'%(channel+1,value)
            self.dev.cmd(command)
        elif type == 'amp':
            # print(value)
            command = 'POW,%d,%f dBm'%(channel+1,value)
            self.dev.cmd(command)
            # self.dev.cmd('POW,%d,0 dBm'%(channel+1))
        elif type == 'phase':
            # print(value)
            command = 'PHASE,%d,%fdeg'%(channel+1,value)
            self.dev.cmd(command)
            # self.dev.cmd('PHASE,%d,0deg'%(channel+1))
        else:
            raise TypeError(type)
        # Now that a static update has been done, we'd better invalidate the saved STATIC_DATA:
        # self.smart_cache['STATIC_DATA'] = None

    def transition_to_buffered(self,device_name,h5file,initial_values,fresh):

        # Store the initial values in case we have to abort and restore them:
        self.initial_values = initial_values
        # Store the final values to for use during transition_to_static:
        self.final_values = {}
        # static_data = None

        table_data = None
        with h5py.File(h5file) as hdf5_file:
            group = hdf5_file['/devices/'+device_name]
            # If there are values to set the unbuffered outputs to, set them now:
            # if 'STATIC_DATA' in group:
            #     static_data = group['STATIC_DATA'][:][0]
            # Now program the buffered outputs:
            if 'TABLE_DATA' in group:
                table_data = group['TABLE_DATA'][:]

        # both channels go to table mode
        self.dev.cmd('mode,1,tsb')
        self.dev.cmd('mode,2,tsb')

        # Now program the buffered outputs:
        if table_data is not None:
            data = table_data
            for i, line in enumerate(data):
                st = time.time()
                oldtable = self.smart_cache['TABLE_DATA']
                for ddsno in range(2):
                    if fresh or i >= len(oldtable) or (line['freq%d'%ddsno],line['phase%d'%ddsno],line['amp%d'%ddsno]) != (oldtable[i]['freq%d'%ddsno],oldtable[i]['phase%d'%ddsno],oldtable[i]['amp%d'%ddsno]):
                        command = 'table,entry,%d,%d,%fMHz,%fdBm,%fdeg,1,trig'%(ddsno+1,i+1,line['freq%d'%ddsno],line['amp%d'%ddsno],line['phase%d'%ddsno])
                        self.dev.cmd(command)
                et = time.time()
                tt=et-st
                self.logger.debug('Time spent on line %s: %s'%(i,tt))
            # Store the table for future smart programming comparisons:
            try:
                self.smart_cache['TABLE_DATA'][:len(data)] = data
                self.logger.debug('Stored new table as subset of old table')
            except: # new table is longer than old table
                self.smart_cache['TABLE_DATA'] = data
                self.logger.debug('New table is longer than old table and has replaced it.')

            # Get the final values of table mode so that the GUI can
            # reflect them after the run:
            self.final_values['channel 0'] = {}
            self.final_values['channel 1'] = {}
            self.final_values['channel 0']['freq'] = data[-1]['freq0']
            self.final_values['channel 1']['freq'] = data[-1]['freq1']
            self.final_values['channel 0']['amp'] = data[-1]['amp0']
            self.final_values['channel 1']['amp'] = data[-1]['amp1']
            self.final_values['channel 0']['phase'] = data[-1]['phase0']
            self.final_values['channel 1']['phase'] = data[-1]['phase1']

            # Transition to table mode:
            # Set the number of entries for each channel
            self.dev.cmd('table,entries,1,%d'%len(data))
            self.dev.cmd('table,entries,2,%d'%len(data))

            # arm for both channels
            self.dev.cmd('table,arm,1')
            self.dev.cmd('table,arm,2')

        #import time
        #time.sleep(1)
        return self.final_values

    def abort_transition_to_buffered(self):
        return self.transition_to_manual(True)

    def abort_buffered(self):
        # TODO: untested
        return self.transition_to_manual(True)

    def transition_to_manual(self,abort=False):

        # stop table for both channels
        self.dev.cmd('table,stop,1')
        self.dev.cmd('table,stop,2')

        # both channels go to manual mode
        self.dev.cmd('mode,1,nsb')
        self.dev.cmd('mode,2,nsb')

        if abort:
            pass
            # If we're aborting the run, then we need to reset DDSs 2 and 3 to their initial values.
            # 0 and 1 will already be in their initial values. We also need to invalidate the smart
            # programming cache for them.
            # values = self.initial_values
            # DDSs = [2,3]
            # self.smart_cache['STATIC_DATA'] = None
        else:
            # If we're not aborting the run, then we need to set DDSs 0 and 1 to their final values.
            # 2 and 3 will already be in their final values.
            values = self.final_values
            DDSs = [0,1]

        # only program the channels that we need to
        for ddsnumber in DDSs:
            channel_values = values['channel %d'%ddsnumber]
            for subchnl in ['freq','amp','phase']:
                self.program_static(ddsnumber,subchnl,channel_values[subchnl])

        # return True to indicate we successfully transitioned back to manual mode
        return True

    def shutdown(self):

        # turn both channels off
        for i in range(2):
            self.dev.cmd('off,%d'%(i+1))

        self.dev.close()



# @runviewer_parser
# class RunviewerClass(object):
#     def __init__(self, path, device):
#         self.path = path
#         self.name = device.name
#         self.device = device
#
#     def get_traces(self, add_trace, clock=None):
#         if clock is None:
#             # we're the master pseudoclock, software triggered. So we don't have to worry about trigger delays, etc
#             raise Exception('No clock passed to %s. The XRF021 must be clocked by another device.'%self.name)
#
#         times, clock_value = clock[0], clock[1]
#
#         clock_indices = np.where((clock_value[1:]-clock_value[:-1])==1)[0]+1
#         # If initial clock value is 1, then this counts as a rising edge (clock should be 0 before experiment)
#         # but this is not picked up by the above code. So we insert it!
#         if clock_value[0] == 1:
#             clock_indices = np.insert(clock_indices, 0, 0)
#         clock_ticks = times[clock_indices]
#
#         # get the data out of the H5 file
#         data = {}
#         with h5py.File(self.path, 'r') as f:
#             if 'TABLE_DATA' in f['devices/%s'%self.name]:
#                 table_data = f['devices/%s/TABLE_DATA'%self.name][:]
#                 for i in range(2):
#                     for sub_chnl in ['freq', 'amp', 'phase']:
#                         data['channel %d_%s'%(i,sub_chnl)] = table_data['%s%d'%(sub_chnl,i)][:]
#
#             if 'STATIC_DATA' in f['devices/%s'%self.name]:
#                 static_data = f['devices/%s/STATIC_DATA'%self.name][:]
#                 for i in range(2,4):
#                     for sub_chnl in ['freq', 'amp', 'phase']:
#                         data['channel %d_%s'%(i,sub_chnl)] = np.empty((len(clock_ticks),))
#                         data['channel %d_%s'%(i,sub_chnl)].fill(static_data['%s%d'%(sub_chnl,i)][0])
#
#
#         for channel, channel_data in data.items():
#             data[channel] = (clock_ticks, channel_data)
#
#         for channel_name, channel in self.device.child_list.items():
#             for subchnl_name, subchnl in channel.child_list.items():
#                 connection = '%s_%s'%(channel.parent_port, subchnl.parent_port)
#                 if connection in data:
#                     add_trace(subchnl.name, data[connection], self.name, connection)
#
#         return {}
