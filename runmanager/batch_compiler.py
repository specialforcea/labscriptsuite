#####################################################################
#                                                                   #
# /batch_compiler.py                                                #
#                                                                   #
# Copyright 2013, Monash University                                 #
#                                                                   #
# This file is part of the program runmanager, in the labscript     #
# suite (see http://labscriptsuite.org), and is licensed under the  #
# Simplified BSD License. See the license.txt file in the root of   #
# the project for the full license.                                 #
#                                                                   #
#####################################################################

import sys
from zprocess import setup_connection_with_parent
to_parent, from_parent, kill_lock = setup_connection_with_parent(lock = True)

import labscript
import labscript_utils.excepthook
from labscript_utils.modulewatcher import ModuleWatcher


class BatchProcessor(object):
    def __init__(self, to_parent, from_parent, kill_lock):
        self.to_parent = to_parent
        self.from_parent = from_parent
        self.kill_lock = kill_lock
        self.mainloop()
        
    def mainloop(self):
        while True:
            signal, data =  self.from_parent.get()
            if signal == 'compile':
                with kill_lock:
                    # TODO: remove actual compilation of labscript from here and
                    # move to when file is ready to go at blacs.  This code should do
                    #
                    # labscript.labscript_init(run_file, labscript_file=labscript_file)
                    # with h5py.File(run_file) as h5_file:
                    #    labscript.save_labscripts(h5_file)
                    # labscript.labscript_cleanup()
                    # instead of the following code
                    # 
                    success = labscript.compile(*data)
                self.to_parent.put(['done',success])
            elif signal == 'quit':
                sys.exit(0)
            else:
                raise ValueError(signal)
                       
if __name__ == '__main__':
    module_watcher = ModuleWatcher() # Make sure modified modules are reloaded
    batch_processor = BatchProcessor(to_parent,from_parent,kill_lock)
