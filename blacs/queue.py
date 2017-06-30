#####################################################################
#                                                                   #
# /queue.py                                                         #
#                                                                   #
# Copyright 2013, Monash University                                 #
#                                                                   #
# This file is part of the program BLACS, in the labscript suite    #
# (see http://labscriptsuite.org), and is licensed under the        #
# Simplified BSD License. See the license.txt file in the root of   #
# the project for the full license.                                 #
#                                                                   #
#####################################################################

import logging
import os
import platform
import Queue
import threading
import time
import sys

if 'PySide' in sys.modules.copy():
    from PySide.QtCore import *
    from PySide.QtGui import *
else:
    from PyQt4.QtCore import *
    from PyQt4.QtGui import *

import zprocess.locking, labscript_utils.h5_lock, h5py
from labscript import compile_h5
import labscript_utils.h5_scripting
import labscript_utils.timing_utils
import labscript_utils.file_utils

zprocess.locking.set_client_process_name('BLACS.queuemanager')

from qtutils import *

# Connection Table Code
from connections import ConnectionTable
from blacs.tab_base_classes import MODE_MANUAL, MODE_TRANSITION_TO_BUFFERED, MODE_TRANSITION_TO_MANUAL, MODE_BUFFERED  
from runmanager import get_shot_globals, set_shot_globals

FILEPATH_COLUMN = 0

class QueueTreeview(QTreeView):
    def __init__(self,*args,**kwargs):
        QTreeView.__init__(self,*args,**kwargs)
        self.header().setStretchLastSection(True)
        self.setAutoScroll(False)
        self.setTextElideMode(Qt.ElideLeft)
        self.add_to_queue = None
        self.delete_selection = None
        self._logger = logging.getLogger('BLACS.QueueManager') 

    def keyPressEvent(self,event):
        if event.key() == Qt.Key_Delete:
            event.accept()
            if self.delete_selection:
                self.delete_selection()
        QTreeView.keyPressEvent(self,event)
        
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.setDropAction(Qt.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            event.setDropAction(Qt.CopyAction)
            event.accept()
            
            for url in event.mimeData().urls():
                path = str(url.toLocalFile())
                if path.endswith('.h5') or path.endswith('.hdf5'):
                    self._logger.info('Acceptable file dropped. Path is %s'%path)
                    if self.add_to_queue:
                        self.add_to_queue(str(path))
                    else:
                        self._logger.info('Dropped file not added to queue because there is no access to the neccessary add_to_queue method')
                else:
                    self._logger.info('Invalid file dropped. Path was %s'%path)
        else:
            event.ignore()

class QueueManager(object):
    
    def __init__(self, BLACS, ui):
        self._ui = ui
        self.BLACS = BLACS
        self._manager_running = True
        self._manager_paused = False
        self.manager_repeat = 0
        self.master_pseudoclock = self.BLACS.connection_table.master_pseudoclock
        
        self._logger = logging.getLogger('BLACS.QueueManager')   
        
        # Create listview model
        self._model = QStandardItemModel()
        self._create_headers()
        self._ui.treeview.setModel(self._model)
        self._ui.treeview.add_to_queue = self.process_request
        self._ui.treeview.delete_selection = self._delete_selected_items
        
        # set up queue control buttons
        self._ui.queue_pause_button.toggled.connect(self._toggle_pause)
        self._ui.queue_repeat_comboBox.activated.connect(self._activated_repeat)
        self._ui.queue_delete_button.clicked.connect(self._delete_selected_items)
        self._ui.queue_push_up.clicked.connect(self._move_up)
        self._ui.queue_push_down.clicked.connect(self._move_down)
        self._ui.queue_push_to_top.clicked.connect(self._move_top)
        self._ui.queue_push_to_bottom.clicked.connect(self._move_bottom)
        self._repeats = int(self._ui.repeats_spinBox.value())
        self._ui.repeats_spinBox.valueChanged.connect(self._repeats_changed)        
        
        # timer
        self._timer = labscript_utils.timing_utils.timer()


        # dynamic globals
        self._ui.ClearDynamic_pushButton.clicked.connect(self._delete_dynamic_globals)
        self.DynamicGlobals = {}
        
        self.manager = threading.Thread(target = self.manage)
        self.manager.daemon=True
        self.manager.start()
    
    def _create_headers(self):
        self._model.setHorizontalHeaderItem(FILEPATH_COLUMN, QStandardItem('Filepath'))
    
        
    
    def get_save_data(self):
        # get list of files in the queue
        file_list = []
        for i in range(self._model.rowCount()):
            file_list.append(self._model.item(i).text())
        # get button states
        return {'manager_paused':self.manager_paused,
                'manager_repeat':self.manager_repeat,
                'files_queued':file_list,
               }
    
    def restore_save_data(self,data):
        if 'manager_paused' in data:
            self.manager_paused = data['manager_paused']
        if 'manager_repeat' in data:
            self.manager_repeat = data['manager_repeat']
        if 'files_queued' in data:
            file_list = list(data['files_queued'])
            self._model.clear()
            self._create_headers()
            for file in file_list:
                self.process_request(str(file))
        
    @property
    @inmain_decorator(True)
    def manager_running(self):
        return self._manager_running
        
    @manager_running.setter
    @inmain_decorator(True)
    def manager_running(self,value):
        value = bool(value)
        self._manager_running = value
        
    def _toggle_pause(self,checked):    
        self.manager_paused = checked
    
    @property
    @inmain_decorator(True)
    def manager_paused(self):
        return self._manager_paused
    
    @manager_paused.setter
    @inmain_decorator(True)
    def manager_paused(self,value):
        value = bool(value)
        self._manager_paused = value
        if value != self._ui.queue_pause_button.isChecked():
            self._ui.queue_pause_button.setChecked(value)
    
    def _activated_repeat(self, value):    
        self.manager_repeat = int(value)
        
    @property
    @inmain_decorator(True)
    def manager_repeat(self):
        return self._manager_repeat
    
    @manager_repeat.setter
    @inmain_decorator(True)
    def manager_repeat(self, value):
        value = int(value)
        self._manager_repeat = value
        if value != self._ui.queue_repeat_comboBox.currentIndex():
            self._ui.queue_repeat_comboBox.setCurrentIndex(value)
        
    def _delete_selected_items(self):
        index_list = self._ui.treeview.selectedIndexes()
        while index_list:
            index =  index_list[0].row()
            self._model.takeRow(index)
            index_list = self._ui.treeview.selectedIndexes()

    def _delete_dynamic_globals(self):
        self.DynamicGlobals = {}        
        self._ui.Globals_tableWidget.setRowCount(0)
    
    def _move_up(self):        
        # Get the selection model from the treeview
        selection_model = self._ui.treeview.selectionModel()    
        # Create a list of select row indices
        selected_row_list = [index.row() for index in sorted(selection_model.selectedRows())]
        # For each row selected
        for i,row in enumerate(selected_row_list):
            # only move the row if it is not element 0, and the row above it is not selected
            # (note that while a row above may have been initially selected, it should by now, be one row higher
            # since we start moving elements of the list upwards starting from the lowest index)
            if row > 0 and (row-1) not in selected_row_list:
                # Remove the selected row
                items = self._model.takeRow(row)
                # Add the selected row into a position one above
                self._model.insertRow(row-1,items)
                # Since it is now a newly inserted row, select it again
                selection_model.select(self._model.indexFromItem(items[0]),QItemSelectionModel.SelectCurrent)
                # reupdate the list of selected indices to reflect this change
                selected_row_list[i] -= 1
       
    def _move_down(self):
        # Get the selection model from the treeview
        selection_model = self._ui.treeview.selectionModel()    
        # Create a list of select row indices
        selected_row_list = [index.row() for index in reversed(sorted(selection_model.selectedRows()))]
        # For each row selected
        for i,row in enumerate(selected_row_list):
            # only move the row if it is not the last element, and the row above it is not selected
            # (note that while a row below may have been initially selected, it should by now, be one row lower
            # since we start moving elements of the list upwards starting from the highest index)
            if row < self._model.rowCount()-1 and (row+1) not in selected_row_list:
                # Remove the selected row
                items = self._model.takeRow(row)
                # Add the selected row into a position one above
                self._model.insertRow(row+1,items)
                # Since it is now a newly inserted row, select it again
                selection_model.select(self._model.indexFromItem(items[0]),QItemSelectionModel.SelectCurrent)
                # reupdate the list of selected indices to reflect this change
                selected_row_list[i] += 1
        
    def _move_top(self):
        # Get the selection model from the treeview
        selection_model = self._ui.treeview.selectionModel()    
        # Create a list of select row indices
        selected_row_list = [index.row() for index in sorted(selection_model.selectedRows())]
        # For each row selected
        for i,row in enumerate(selected_row_list):
            # only move the row while it is not element 0, and the row above it is not selected
            # (note that while a row above may have been initially selected, it should by now, be one row higher
            # since we start moving elements of the list upwards starting from the lowest index)
            while row > 0 and (row-1) not in selected_row_list:
                # Remove the selected row
                items = self._model.takeRow(row)
                # Add the selected row into a position one above
                self._model.insertRow(row-1,items)
                # Since it is now a newly inserted row, select it again
                selection_model.select(self._model.indexFromItem(items[0]),QItemSelectionModel.SelectCurrent)
                # reupdate the list of selected indices to reflect this change
                selected_row_list[i] -= 1
                row -= 1
              
    def _move_bottom(self):
        selection_model = self._ui.treeview.selectionModel()    
        # Create a list of select row indices
        selected_row_list = [index.row() for index in reversed(sorted(selection_model.selectedRows()))]
        # For each row selected
        for i,row in enumerate(selected_row_list):
            # only move the row while it is not the last element, and the row above it is not selected
            # (note that while a row below may have been initially selected, it should by now, be one row lower
            # since we start moving elements of the list upwards starting from the highest index)
            while row < self._model.rowCount()-1 and (row+1) not in selected_row_list:
                # Remove the selected row
                items = self._model.takeRow(row)
                # Add the selected row into a position one above
                self._model.insertRow(row+1,items)
                # Since it is now a newly inserted row, select it again
                selection_model.select(self._model.indexFromItem(items[0]),QItemSelectionModel.SelectCurrent)
                # reupdate the list of selected indices to reflect this change
                selected_row_list[i] += 1
                row += 1
    
    def _repeats_changed(self, value):
        """
        Sets the number of repeats allowed in repeat mode
        """
        self._repeats = int(value)

    @inmain_decorator(True)
    def append(self, h5files):
        for file in h5files:
            item = QStandardItem(file)
            item.setToolTip(file)
            self._model.appendRow(item)
    
    @inmain_decorator(True)
    def prepend(self,h5file):
        if not self.is_in_queue(h5file):
            self._model.insertRow(0,QStandardItem(h5file))
    
    def process_request(self,h5_filepath):
        # check connection table
        
        try:
            new_conn = ConnectionTable(h5_filepath)
        except:
            return "H5 file not accessible to Control PC\n"

        result,error = inmain(self.BLACS.connection_table.compare_to,new_conn)

        if result:
            # Has this run file been run already?
            with h5py.File(h5_filepath) as h5_file:
                if 'data' in h5_file['/']:
                    rerun = True
                else:
                    rerun = False
            if rerun or self.is_in_queue(h5_filepath):
                self._logger.debug('Run file has already been run! Creating a fresh copy to rerun')
                new_h5_filepath = labscript_utils.file_utils.new_rep_name(h5_filepath, repeats=self._repeats)
                
                success = self.clean_h5_file(h5_filepath, new_h5_filepath)
                if not success:
                   return 'Cannot create a re run of this experiment. Is it a valid run file?'
                self.append([new_h5_filepath])
                message = "Experiment added successfully: experiment to be re-run\n"
            else:
                self.append([h5_filepath])
                message = "Experiment added successfully\n"
            if self.manager_paused:
                message += "Warning: Queue is currently paused\n"
            if not self.manager_running:
                message = "Error: Queue is not running\n"
            return message
        else:
            # TODO: Parse and display the contents of "error" in a more human readable format for analysis of what is wrong!
            message =  ("Connection table of your file is not a subset of the experimental control apparatus.\n"
                       "You may have:\n"
                       "    Submitted your file to the wrong control PC\n"
                       "    Added new channels to your h5 file, without rewiring the experiment and updating the control PC\n"
                       "    Renamed a channel at the top of your script\n"
                       "    Submitted an old file, and the experiment has since been rewired\n"
                       "\n"
                       "Please verify your experiment script matches the current experiment configuration, and try again\n"
                       "The error was %s\n"%error)
            return message
                    
    def clean_h5_file(self,h5file,new_h5_file):
        try:
            with h5py.File(h5file,'r') as old_file:
                with h5py.File(new_h5_file,'w') as new_file:
                    groups_to_copy = ['devices', 'calibrations', 'script', 'globals', 'connection table', 
                                      'labscriptlib', 'waits']
                    for group in groups_to_copy:
                        if group in old_file:
                            new_file.copy(old_file[group], group)
                    for name in old_file.attrs:
                        new_file.attrs[name] = old_file.attrs[name]
        except Exception as e:
            #raise
            self._logger.error('Clean H5 File Error: %s' %str(e))
            return False
            
        return True
    
    @inmain_decorator(wait_for_return=True)    
    def is_in_queue(self,path):                
        item = self._model.findItems(path,column=FILEPATH_COLUMN)
        if item:
            return True
        else:
            return False

    @inmain_decorator(wait_for_return=True)
    def get_num_files(self):
        return int(self._model.rowCount())
 

    @inmain_decorator(wait_for_return=True)
    def set_status(self,text):
        # TODO: make this fancier!
        self._ui.queue_status.setText(str(text))
        
    @inmain_decorator(wait_for_return=True)
    def get_status(self):
        return self._ui.queue_status.text()
            
    @inmain_decorator(wait_for_return=True)
    def get_next_file(self):
        return str(self._model.takeRow(0)[0].text())
    
        
    
    @inmain_decorator(wait_for_return=True)    
    def transition_device_to_buffered(self, name, transition_list, h5file, restart_receiver):
        tab = self.BLACS.tablist[name]
        if self.get_device_error_state(name,self.BLACS.tablist):
            return False
        tab.connect_restart_receiver(restart_receiver)
        tab.transition_to_buffered(h5file,self.current_queue)
        transition_list[name] = tab
        return True
    
    @inmain_decorator(wait_for_return=True)
    def get_device_error_state(self,name,device_list):
        return device_list[name].error_message
       
     
    def manage(self):
        logger = logging.getLogger('BLACS.queue_manager.thread')   
        # While the program is running!
        logger.info('starting')
        
        # HDF5 prints lots of errors by default, for things that aren't
        # actually errors. These are silenced on a per thread basis,
        # and automatically silenced in the main thread when h5py is
        # imported. So we'll silence them in this thread too:
        h5py._errors.silence_errors()
        
        # This name stores the queue currently being used to
        # communicate with tabs, so that abort signals can be put
        # to it when those tabs never respond and are restarted by
        # the user.
        self.current_queue = Queue.Queue()
        
        #TODO: put in general configuration
        timeout_limit = 300 #seconds
        self.set_status("Idle") 
        
        while self.manager_running:
            # If the pause button is pushed in, sleep
            if self.manager_paused:
                if self.get_status() == "Idle":
                    logger.info('Paused')
                    self.set_status("Queue Paused") 
                time.sleep(1)
                continue
            
            # Get the top file
            try:
                path = self.get_next_file()
                now_running_text = 'Now running: <b>%s</b>'%os.path.basename(path)
                self.set_status(now_running_text)
                logger.info('Got a file: %s'%path)
            except:
                # If no files, sleep for 1s,
                self.set_status("Idle")
                time.sleep(1)
                continue
                        
            devices_in_use = {}
            transition_list = {}   
            start_time = time.time()
            self.current_queue = Queue.Queue()   
            
            # Function to be run when abort button is clicked
            def abort_function():
                try:
                    # Set device name to "Queue Manager" which will never be a labscript device name
                    # as it is not a valid python variable name (has a space in it!)
                    self.current_queue.put(['Queue Manager', 'abort'])
                except Exception:
                    logger.exception('Could not send abort message to the queue manager')
        
            def restart_function(device_name):
                try:
                    self.current_queue.put([device_name, 'restart'])
                except Exception:
                    logger.exception('Could not send restart message to the queue manager for device %s'%device_name)
        
            ##########################################################################################################################################
            #                                                       transition to buffered                                                           #
            ########################################################################################################################################## 
            try:  
                # A Queue for event-based notification when the tabs have
                # completed transitioning to buffered:        
                
                timed_out = False
                error_condition = False
                abort = False
                restarted = False
                self.set_status(now_running_text+"<br>Transitioning to Buffered")
                
                # Enable abort button, and link in current_queue:
                inmain(self._ui.queue_abort_button.clicked.connect,abort_function)
                inmain(self._ui.queue_abort_button.setEnabled,True)
                          
                # Ready to run file: assume that the file has _not_ been compiled and compile it 
                
                # Extract script globals, and update them from the blacs mantained dictionary of globals.
                shot_globals = get_shot_globals(path)
                shot_globals.update(self.DynamicGlobals)
                with h5py.File(path, "a") as hdf5_file:
                    set_shot_globals(hdf5_file, shot_globals)

                # Compile file
                compile_h5(path)

                # Run file
                with h5py.File(path, "r+") as hdf5_file:
                    min_time = hdf5_file.attrs['min_time']
                    h5_file_devices = hdf5_file['devices/'].keys()
                
                for name in h5_file_devices: 
                    try:
                        # Connect restart signal from tabs to current_queue and transition the device to buffered mode
                        success = self.transition_device_to_buffered(name,transition_list,path,restart_function)
                        if not success:
                            logger.error('%s has an error condition, aborting run' % name)
                            error_condition = True
                            break
                    except Exception as e:
                        logger.error('Exception while transitioning %s to buffered mode. Exception was: %s'%(name,str(e)))
                        error_condition = True
                        break
                        
                devices_in_use = transition_list.copy()

                while transition_list and not error_condition:
                    try:
                        # Wait for a device to transtition_to_buffered:
                        logger.debug('Waiting for the following devices to finish transitioning to buffered mode: %s'%str(transition_list))
                        device_name, result = self.current_queue.get(timeout=2)
                        
                        #Handle abort button signal
                        if device_name == 'Queue Manager' and result == 'abort':
                            # we should abort the run
                            logger.info('abort signal received from GUI')
                            abort = True
                            break
                            
                        if result == 'fail':
                            logger.info('abort signal received during transition to buffered of %s' % device_name)
                            error_condition = True
                            break
                        elif result == 'restart':
                            logger.info('Device %s was restarted, aborting shot.'%device_name)
                            restarted = True
                            break
                            
                        logger.debug('%s finished transitioning to buffered mode' % device_name)
                        
                        # The tab says it's done, but does it have an error condition?
                        if self.get_device_error_state(device_name,transition_list):
                            logger.error('%s has an error condition, aborting run' % device_name)
                            error_condition = True
                            break
                            
                        del transition_list[device_name]                   
                    except Queue.Empty:
                        # It's been 2 seconds without a device finishing
                        # transitioning to buffered. Is there an error?
                        for name in transition_list:
                            if self.get_device_error_state(name,transition_list):
                                error_condition = True
                                break
                                
                        if error_condition:
                            break
                            
                        # Has programming timed out?
                        if time.time() - start_time > timeout_limit:
                            logger.error('Transitioning to buffered mode timed out')
                            timed_out = True
                            break

                # Handle if we broke out of loop due to timeout or error:
                if timed_out or error_condition or abort or restarted:
                    # Pause the queue, re add the path to the top of the queue, and set a status message!
                    # only if we aren't responding to an abort click
                    if not abort:
                        self.manager_paused = True
                        self.prepend(path)                
                    if timed_out:
                        self.set_status("Device programming timed out. Queue Paused...")
                    elif abort:
                        self.set_status("Shot aborted")
                    elif restarted:
                        self.set_status('A device was restarted during transition_to_buffered. Shot aborted')
                    else:
                        self.set_status("One or more devices is in an error state. Queue Paused...")
                        
                    # Abort the run for all devices in use:
                    # need to recreate the queue here because we don't want to hear from devices that are still transitioning to buffered mode
                    self.current_queue = Queue.Queue()
                    for tab in devices_in_use.values():                        
                        # We call abort buffered here, because if each tab is either in mode=BUFFERED or transition_to_buffered failed in which case
                        # it should have called abort_transition_to_buffered itself and returned to manual mode
                        # Since abort buffered will only run in mode=BUFFERED, and the state is not queued indefinitely (aka it is deleted if we are not in mode=BUFFERED)
                        # this is the correct method call to make for either case
                        tab.abort_buffered(self.current_queue)
                        # We don't need to check the results of this function call because it will either be successful, or raise a visible error in the tab.
                        
                        # disconnect restart signal from tabs
                        inmain(tab.disconnect_restart_receiver,restart_function)
                        
                    # disconnect abort button and disable
                    inmain(self._ui.queue_abort_button.clicked.disconnect,abort_function)
                    inmain(self._ui.queue_abort_button.setEnabled,False)
                    
                    # Start a new iteration
                    continue
                
            
            
                ##########################################################################################################################################
                #                                                             SCIENCE!                                                                   #
                ##########################################################################################################################################
            
                # Get front panel data, but don't save it to the h5 file until the experiment ends:
                states,tab_positions,window_data,plugin_data = self.BLACS.front_panel_settings.get_save_data()
                self.set_status(now_running_text+"<br>Running...(program time: %.3fs)"%(time.time() - start_time))
                    
                # A Queue for event-based notification of when the experiment has finished.
                experiment_finished_queue = Queue.Queue()               
                logger.debug('About to start the master pseudoclock')
                
                
                # Do not start until delay time specificed by last sequence has expired
                self._timer.wait()
                
                # Start the timer to block until the next run starts
                self._timer.start(
                    min_time,
                    countdown_queue=self.BLACS._countdown_queue,
                    countdown_mode='precent_done')                                
                
                run_time = time.localtime()
                
                #TODO: fix potential race condition if BLACS is closing when this line executes?
                self.BLACS.tablist[self.master_pseudoclock].start_run(experiment_finished_queue)
                
                                                
                # Wait for notification of the end of run:
                abort = False
                restarted = False
                while result != 'done':
                    try:
                        result = experiment_finished_queue.get(timeout=0.5)
                    except Queue.Empty:
                        pass
                    try:
                        # Poll self.current_queue for abort signal from button or device restart
                        device_name, result = self.current_queue.get(timeout=0.5)                        
                        if (device_name == 'Queue Manager' and result == 'abort'):
                            abort = True
                            break
                        elif result == 'restart':
                            restarted = True
                            break
                        # Check for error states in tabs
                        for device_name, tab in devices_in_use.items():
                            if self.get_device_error_state(device_name,devices_in_use):
                                restarted = True
                                break
                        if restarted:
                            break
                    except Queue.Empty:
                        pass
                              
                if abort or restarted:
                    for devicename, tab in devices_in_use.items():
                        if tab.mode == MODE_BUFFERED:
                            tab.abort_buffered(self.current_queue)
                        # disconnect restart signal from tabs 
                        inmain(tab.disconnect_restart_receiver,restart_function)
                                            
                # Disable abort button
                inmain(self._ui.queue_abort_button.clicked.disconnect,abort_function)
                inmain(self._ui.queue_abort_button.setEnabled,False)
                
                if restarted:                    
                    self.manager_paused = True
                    self.prepend(path)  
                    self.set_status("Device restarted mid-shot. Shot aborted, Queue paused.")
                elif abort:
                    self.set_status("Shot aborted")
                    
                if abort or restarted:
                    # after disabling the abort button, we now start a new iteration
                    continue                
                
                logger.info('Run complete')
                self.set_status(now_running_text+"<br>Sequence done, saving data...")
            # End try/except block here
            except Exception:
                logger.exception("Error in queue manager execution. Queue paused.")
                # clean up the h5 file
                self.manager_paused = True
                # clean the h5 file:
                self.clean_h5_file(path, 'temp.h5')
                try:
                    os.remove(path)
                    os.rename('temp.h5', path)
                except WindowsError if platform.system() == 'Windows' else None:
                    logger.warning('Couldn\'t delete failed run file %s, another process may be using it. Using alternate filename for second attempt.'%path)
                    os.rename('temp.h5', path.replace('.h5','_retry.h5'))
                    path = path.replace('.h5','_retry.h5')
                # Put it back at the start of the queue:
                self.prepend(path)
                
                # Need to put devices back in manual mode
                self.current_queue = Queue.Queue()
                for devicename, tab in devices_in_use.items():
                    if tab.mode == MODE_BUFFERED or tab.mode == MODE_TRANSITION_TO_BUFFERED:
                        tab.abort_buffered(self.current_queue)
                    # disconnect restart signal from tabs 
                    inmain(tab.disconnect_restart_receiver,restart_function)
                self.set_status("Error occured in Queue Manager. Queue Paused. \nPlease make sure all devices are back in manual mode before unpausing the queue")
                
                # disconnect and disable abort button
                inmain(self._ui.queue_abort_button.clicked.disconnect,abort_function)
                inmain(self._ui.queue_abort_button.setEnabled,False)
                
                # Start a new iteration
                continue
                             
            ##########################################################################################################################################
            #                                                           SCIENCE OVER!                                                                #
            ##########################################################################################################################################
            
            
            
            ##########################################################################################################################################
            #                                                       Transition to manual                                                             #
            ##########################################################################################################################################
            # start new try/except block here                   
            try:
                with h5py.File(path,'r+') as hdf5_file:
                    self.BLACS.front_panel_settings.store_front_panel_in_h5(hdf5_file,states,tab_positions,window_data,plugin_data,save_conn_table = False)
                with h5py.File(path,'r+') as hdf5_file:
                    data_group = hdf5_file['/'].create_group('data')
                    # stamp with the run time of the experiment
                    hdf5_file.attrs['run time'] = time.strftime('%Y%m%dT%H%M%S',run_time)
        
                # A Queue for event-based notification of when the devices have transitioned to static mode:
                # Shouldn't need to recreate the queue: self.current_queue = Queue.Queue()    
                    
                # TODO: unserialise this if everything is using zprocess.locking
                # only transition one device to static at a time,
                # since writing data to the h5 file can potentially
                # happen at this stage:
                error_condition = False
                
                # This is far more complicated than it needs to be once transition_to_manual is unserialised!
                response_list = {}
                for device_name, tab in devices_in_use.items():
                    if device_name not in response_list:
                        tab.transition_to_manual(self.current_queue)               
                        while True:
                            # TODO: make the call to current_queue.get() timeout 
                            # and periodically check for error condition on the tab
                            got_device_name, result = self.current_queue.get()
                            # if the response is not for this device, then save it for later!
                            if device_name != got_device_name:
                                response_list[got_device_name] = result
                            else:
                                break
                    else:
                        result = response_list[device_name]
                    # Check for abort signal from device restart
                    if result == 'fail':
                        error_condition = True
                    if result == 'restart':
                        error_condition = True
                    if self.get_device_error_state(device_name,devices_in_use):
                        error_condition = True
                    # Once device has transitioned_to_manual, disconnect restart signal
                    inmain(tab.disconnect_restart_receiver,restart_function)
                    
                if error_condition:                
                    self.set_status("Error during transtion to manual. Queue Paused.")
                    # TODO: Kind of dodgy raising an exception here...
                    raise Exception('A device failed during transition to manual')
                
                # All data written, now run all PostProcessing functions
                SavedFunctions = labscript_utils.h5_scripting.get_all_saved_functions(path)
                
                with h5py.File(path, 'r+') as hdf5_file:
                    for SavedFunction in SavedFunctions:
                        try:
                            result = SavedFunction(hdf5_file, **shot_globals)
                        except:
                            result = {}
                            logger.error('Post Processing function did not execute correctly')
                            
                        try:
                            self.DynamicGlobals.update(result)
                        except:
                            logger.error('Post Processing function did not return a dict type')

                inmain(self._ui.Globals_tableWidget.setRowCount, len(self.DynamicGlobals))
                for i, key in enumerate(self.DynamicGlobals):
                    inmain(self._ui.Globals_tableWidget.setItem, i, 0, QTableWidgetItem(key)) 
                    inmain(self._ui.Globals_tableWidget.setItem, i, 1, QTableWidgetItem( str(self.DynamicGlobals[key]) ))

                
                
            except Exception as e:
                logger.exception("Error in queue manager execution. Queue paused.")
                # clean up the h5 file
                self.manager_paused = True
                # clean the h5 file:
                self.clean_h5_file(path, 'temp.h5')
                try:
                    os.remove(path)
                    os.rename('temp.h5', path)
                except WindowsError if platform.system() == 'Windows' else None:
                    logger.warning('Couldn\'t delete failed run file %s, another process may be using it. Using alternate filename for second attempt.'%path)
                    os.rename('temp.h5', path.replace('.h5','_retry.h5'))
                    path = path.replace('.h5','_retry.h5')
                # Put it back at the start of the queue:
                self.prepend(path)
                
                # Need to put devices back in manual mode. Since the experiment is over before this try/except block begins, we can 
                # safely call transition_to_manual() on each device tab
                # TODO: Not serialised...could be bad with older BIAS versions :(
                self.current_queue = Queue.Queue()
                for devicename, tab in devices_in_use.items():
                    if tab.mode == MODE_BUFFERED:
                        tab.transition_to_manual(self.current_queue)
                    # disconnect restart signal from tabs 
                    inmain(tab.disconnect_restart_receiver,restart_function)
                self.set_status("Error occured in Queue Manager. Queue Paused. \nPlease make sure all devices are back in manual mode before unpausing the queue")
                continue
            
            ##########################################################################################################################################
            #                                                        Analysis Submission                                                             #
            ########################################################################################################################################## 
            logger.info('All devices are back in static mode.')  
            # Submit to the analysis server
            self.BLACS.analysis_submission.get_queue().put(['file', path])
             
            ##########################################################################################################################################
            #                                                        Repeat Experiment?                                                              #
            ########################################################################################################################################## 
            if (self.manager_repeat == 1) or (self.manager_repeat == 2 and self.get_num_files() == 0):
                # Resubmit job to the bottom of the queue:
                try:
                    message = self.process_request(path)
                    logger.info(message)      
                except:
                    # TODO: make this error popup for the user
                    logger.error('Failed to copy h5_file (%s) for repeat run'%path)

            self.set_status("Idle")
        logger.info('Stopping')

