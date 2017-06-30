#####################################################################
#                                                                   #
# /labscript_devices/Camera.py                                      #
#                                                                   #
# Copyright 2013, Monash University                                 #
#                                                                   #
# This file is part of labscript_devices, in the labscript suite    #
# (see http://labscriptsuite.org), and is licensed under the        #
# Simplified BSD License. See the license.txt file in the root of   #
# the project for the full license.                                 #
#                                                                   #
#####################################################################

try:
    from labscript_utils import check_version
except ImportError:
    raise ImportError('Require labscript_utils > 2.1.0')

check_version('labscript', '2.0.1', '3')

from labscript_devices import labscript_device, BLACS_tab, BLACS_worker
from labscript import TriggerableDevice, LabscriptError, set_passed_properties
import numpy as np

@labscript_device
class Tektronix_TDS2000(TriggerableDevice):
    description = 'Generic Camera'

    @set_passed_properties(
        property_names = {
            "connection_table_properties": ["zmq_port", "visa_resource"]}
        )
    def __init__(self, name, parent_device, connection,
                 zmq_port=8675, visa_resource='', **kwargs):

        self.visa_resource = visa_resource
        self.BLACS_connection = zmq_port
        self.captures = []

        TriggerableDevice.__init__(self, name, parent_device, connection, **kwargs)


    def capture(self, name, t, duration):
        # Duration is just the trigger duration

        if not duration > 0:
            raise LabscriptError("duration must be > 0, not %s"%str(duration))
        # Only ask for a trigger if one has not already been requested by
        # another scope attached to the same trigger:
        already_requested = False
        for scope in self.trigger_device.child_devices:
            if scope is not self:
                for _, other_t, other_duration in scope.captures:
                    if t == other_t and duration == other_duration:
                        already_requested = True
        if not already_requested:
            self.trigger_device.trigger(t, duration)

        if len(self.captures) > 1:
            raise LabscriptError('Scopes can only capture once per cycle, '
                                 'but can have a number of triggers sent to them.')
        else:
            self.captures.append((name, t, duration))
        return duration

    def do_checks(self):
        # Check that all Cameras sharing a trigger device have exposures when we have exposures:
        for scope in self.trigger_device.child_devices:
            if scope is not self:
                for capture in self.captures:
                    if capture not in camera.captures:
                        _, start, duration = capture
                        raise LabscriptError('Scopes %s and %s share a trigger. ' % (self.name, scope.name) +
                                             '%s has a capture at %fs for %fs, ' % (self.name, start, duration) +
                                             'but there is no matching capture for %s. ' % scope.name +
                                             'Scopes sharing a trigger must have identical capture times and durations.')

    def generate_code(self, hdf5_file):
        self.do_checks()
        table_dtypes = [('name','a256'), ('time',float), ('duration',float)]
        data = np.array(self.captures,dtype=table_dtypes)

        group = self.init_device_group(hdf5_file)

        if self.captures:
            group.create_dataset('CAPTURES', data=data)


import os
from blacs.tab_base_classes import Worker, define_state
from blacs.tab_base_classes import MODE_MANUAL, MODE_TRANSITION_TO_BUFFERED, MODE_TRANSITION_TO_MANUAL, MODE_BUFFERED

from blacs.device_base_class import DeviceTab

from qtutils import UiLoader

@BLACS_tab
class Tektronix_TDS2000Tab(DeviceTab):
    def initialise_GUI(self):
        layout = self.get_tab_layout()
        ui_filepath = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'camera.ui')
        self.ui = UiLoader().load(ui_filepath)
        layout.addWidget(self.ui)

        port = int(self.settings['connection_table'].find_by_name(self.settings["device_name"]).BLACS_connection)
        self.ui.port_label.setText(str(port))

        self.ui.is_responding.setVisible(False)
        self.ui.is_not_responding.setVisible(False)

        self.ui.host_lineEdit.returnPressed.connect(self.update_settings_and_check_connectivity)
        self.ui.use_zmq_checkBox.toggled.connect(self.update_settings_and_check_connectivity)
        self.ui.check_connectivity_pushButton.clicked.connect(self.update_settings_and_check_connectivity)

    def get_save_data(self):
        return {'host': str(self.ui.host_lineEdit.text()), 'use_zmq': self.ui.use_zmq_checkBox.isChecked()}

    def restore_save_data(self, save_data):
        print 'restore save data running'
        if save_data:
            host = save_data['host']
            self.ui.host_lineEdit.setText(host)
            if 'use_zmq' in save_data:
                use_zmq = save_data['use_zmq']
                self.ui.use_zmq_checkBox.setChecked(use_zmq)
        else:
            self.logger.warning('No previous front panel state to restore')

        # call update_settings if primary_worker is set
        # this will be true if you load a front panel from the file menu after the tab has started
        if self.primary_worker:
            self.update_settings_and_check_connectivity()

    def initialise_workers(self):
        worker_initialisation_kwargs = {'port': self.ui.port_label.text()}
        self.create_worker("main_worker", Tektronix_TDS2000Worker, worker_initialisation_kwargs)
        self.primary_worker = "main_worker"
        self.update_settings_and_check_connectivity()

    @define_state(MODE_MANUAL, queue_state_indefinitely=True, delete_stale_states=True)
    def update_settings_and_check_connectivity(self, *args):
        self.ui.saying_hello.setVisible(True)
        self.ui.is_responding.setVisible(False)
        self.ui.is_not_responding.setVisible(False)
        kwargs = self.get_save_data()
        responding = yield(self.queue_work(self.primary_worker, 'update_settings_and_check_connectivity', **kwargs))
        self.update_responding_indicator(responding)

    def update_responding_indicator(self, responding):
        self.ui.saying_hello.setVisible(False)
        if responding:
            self.ui.is_responding.setVisible(True)
            self.ui.is_not_responding.setVisible(False)
        else:
            self.ui.is_responding.setVisible(False)
            self.ui.is_not_responding.setVisible(True)

@BLACS_worker
class Tektronix_TDS2000Worker(Worker):
    def init(self):#, port, host, use_zmq):
#        self.port = port
#        self.host = host
#        self.use_zmq = use_zmq
        global socket; import socket
        global zmq; import zmq
        global zprocess; import zprocess
        global shared_drive; import labscript_utils.shared_drive as shared_drive

        self.host = ''
        self.use_zmq = True

    def update_settings_and_check_connectivity(self, host, use_zmq):
        self.host = host
        self.use_zmq = use_zmq
        if not self.host:
            return False
        if not self.use_zmq:
            return self.initialise_sockets(self.host, self.port)
        else:
            response = zprocess.zmq_get_raw(self.port, self.host, data='hello')
            if response == 'hello':
                return True
            else:
                raise Exception('invalid response from server: ' + str(response))

    def initialise_sockets(self, host, port):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        assert port, 'No port number supplied.'
        assert host, 'No hostname supplied.'
        assert str(int(port)) == port, 'Port must be an integer.'
        s.settimeout(10)
        s.connect((host, int(port)))
        s.send('hello\r\n')
        response = s.recv(1024)
        s.close()
        if 'hello' in response:
            return True
        else:
            raise Exception('invalid response from server: ' + response)

    def transition_to_buffered(self, device_name, h5file, initial_values, fresh):
        h5file = shared_drive.path_to_agnostic(h5file)
        if not self.use_zmq:
            return self.transition_to_buffered_sockets(h5file,self.host, self.port)
        response = zprocess.zmq_get_raw(self.port, self.host, data=h5file)
        if response != 'ok':
            raise Exception('invalid response from server: ' + str(response))
        response = zprocess.zmq_get_raw(self.port, self.host, timeout = 10)
        if response != 'done':
            raise Exception('invalid response from server: ' + str(response))
        return {} # indicates final values of buffered run, we have none

    def transition_to_buffered_sockets(self, h5file, host, port):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(120)
        s.connect((host, int(port)))
        s.send('%s\r\n'%h5file)
        response = s.recv(1024)
        if not 'ok' in response:
            s.close()
            raise Exception(response)
        response = s.recv(1024)
        if not 'done' in response:
            s.close()
            raise Exception(response)
        return {} # indicates final values of buffered run, we have none

    def transition_to_manual(self):
        if not self.use_zmq:
            return self.transition_to_manual_sockets(self.host, self.port)
        response = zprocess.zmq_get_raw(self.port, self.host, 'done')
        if response != 'ok':
            raise Exception('invalid response from server: ' + str(response))
        response = zprocess.zmq_get_raw(self.port, self.host, timeout = 10)
        if response != 'done':
            raise Exception('invalid response from server: ' + str(response))
        return True # indicates success

    def transition_to_manual_sockets(self, host, port):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(120)
        s.connect((host, int(port)))
        s.send('done\r\n')
        response = s.recv(1024)
        if response != 'ok\r\n':
            s.close()
            raise Exception(response)
        response = s.recv(1024)
        if not 'done' in response:
            s.close()
            raise Exception(response)
        return True # indicates success

    def abort_buffered(self):
        return self.abort()

    def abort_transition_to_buffered(self):
        return self.abort()

    def abort(self):
        if not self.use_zmq:
            return self.abort_sockets(self.host, self.port)
        response = zprocess.zmq_get_raw(self.port, self.host, 'abort')
        if response != 'done':
            raise Exception('invalid response from server: ' + str(response))
        return True # indicates success

    def abort_sockets(self, host, port):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(120)
        s.connect((host, int(port)))
        s.send('abort\r\n')
        response = s.recv(1024)
        if not 'done' in response:
            s.close()
            raise Exception(response)
        return True # indicates success

    def program_manual(self, values):
        return {}

    def shutdown(self):
        return
