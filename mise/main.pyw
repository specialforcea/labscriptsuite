#####################################################################
#                                                                   #
# /main.pyw                                                         #
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
import sys
import socket
import logging, logging.handlers
import Queue
import itertools
import subprocess
import threading
import urllib, urllib2

import numpy
import gtk, gobject
import zprocess.locking, labscript_utils.h5_lock, h5py

import labscript_utils.excepthook
from zprocess import ZMQServer, subprocess_with_queues, zmq_get
from labscript_utils.gtk_outputbox import OutputBox

from labscript_utils.labconfig import LabConfig, config_prefix

import labscript_utils.shared_drive
import runmanager
from mise import MiseParameter

# This provides debug info without having to run from a terminal, and
# avoids a stupid crash on Windows when there is no command window:
if not sys.stdout.isatty():
    sys.stdout = sys.stderr = open('debug.log','w',1)
    
# Set a meaningful name for zprocess.locking's client id:
zprocess.locking.set_client_process_name('mise')
    
if os.name == 'nt':
    # Make it not look so terrible (if icons and themes are installed):
    gtk.settings_get_default().set_string_property('gtk-icon-theme-name','gnome-human','')
    gtk.settings_get_default().set_string_property('gtk-theme-name','Clearlooks','')
    gtk.settings_get_default().set_string_property('gtk-font-name','ubuntu 11','')
    gtk.settings_get_default().set_long_property('gtk-button-images',False,'')

    # Have Windows 7 consider this program to be a separate app, and not
    # group it with other Python programs in the taskbar:
    import ctypes
    myappid = 'monashbec.labscript.mise' # arbitrary string
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except:
        pass

def setup_logging():
    logger = logging.getLogger('mise')
    handler = logging.handlers.RotatingFileHandler(r'mise.log', maxBytes=1024*1024*50)
    formatter = logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s')
    handler.setFormatter(formatter)
    handler.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    if sys.stdout.isatty():
        terminalhandler = logging.StreamHandler(sys.stdout)
        terminalhandler.setFormatter(formatter)
        terminalhandler.setLevel(logging.DEBUG) # only display info or higher in the terminal
        logger.addHandler(terminalhandler)
    logger.setLevel(logging.DEBUG)
    return logger
    
logger = setup_logging()
labscript_utils.excepthook.set_logger(logger)
logger.info('\n\n===============starting===============\n')


class WebServer(ZMQServer):
    """A server to receive parameter spaces from runmanager, and fitness
    reporting from lyse"""
    def handler(self, request_data):
        if request_data == 'hello':
            # just a ping:
            return 'hello'
        elif isinstance(request_data,tuple) and len(request_data) > 1:
            if request_data[0] == 'from runmanager':
                # A parameter space from runmanager:
                runmanager_data = request_data[1:]
                with gtk.gdk.lock:
                    success, message = app.receive_parameter_space(runmanager_data)
                return success, message
            elif request_data[0] == 'from lyse':
                # A fitness reported from lyse:
                individual_id, fitness = request_data[1:]
                with gtk.gdk.lock:
                    success, message = app.report_fitness(individual_id, fitness)
                return success, message
        success, message = False, 'Request to mise not understood\n'
        return success, message
            
class IndividualNotFound(Exception):
    """An exception class for when an operation on an individual fails
    because the individual has been deleted in the meantime."""
    pass
    
class Individual(object):
    counter = itertools.count()
    all_individuals = {}
    
    def __init__(self, genome, mutation_biases, generation):
        self.genome = genome
        self.id = self.counter.next()
        self.fitness_visible = False
        self.fitness = None
        self.compile_progress_visible = True
        self.compile_progress = 0
        self.error_visible = None
        self.waiting_visible = False
        self.all_individuals[self.id] = self
        self.mutation_biases = mutation_biases
        self.generation = generation
        
    def __getitem__(self,item):
        return self.genome[item]
        
    
class Generation(object):
    counter = itertools.count()
    all_generations = {}
    def __init__(self, population, parameters, previous_generation=None):
        self.id = self.counter.next()
        self.all_generations[self.id] = self
        self.individuals = []
        if previous_generation is None:
            # Spawn individuals to create the first generation:
            for i in range(population):
                genome = {}
                for name, param in parameters.items():
                    if param.initial is None:
                        # Pick a random starting value within the range: 
                        value = numpy.random.rand()*(param.max-param.min) + param.min
                    else:
                        # Pick a value by applying one generation's worth
                        # of mutation to the initial value:
                        value = numpy.random.normal(param.initial, param.mutation_rate)
                        value = numpy.clip(value, param.min, param.max)
                    genome[name] = value
                mutation_biases = {name: numpy.sign(numpy.random.normal()) for name in genome}
                individual = Individual(genome, mutation_biases, self)
                self.individuals.append(individual)
        else:
            # Create a new generation from the previous one, by 'mating'
            # pairs of individuals with each other with a probability
            # based on their fitnesses.  First, we normalize the
            # fitnesses of previous generation to create a probability
            # mass function:
            fitnesses = numpy.array([individual.fitness for individual in previous_generation])
            sorted_fitnesses = sorted(fitnesses)
            rankings = [sorted_fitnesses.index(fitness) for fitness in fitnesses]
            # Must be an array of floats if the inline +=,-=,/=,*= are to operate correctly
            fitnesses = numpy.array(rankings,dtype=numpy.float)
            fitnesses -= fitnesses.min()
            if fitnesses.max() != 0:
                fitnesses /= fitnesses.max()
            # Add an offset to ensure that the least fit individual
            # will still have a nonzero probability of reproduction;
            # approx 1/N times the most fit individual's probability:
            fitnesses += 1/len(fitnesses)
            fitnesses /= fitnesses.sum()
            # Let mating season begin:
            while len(self.individuals) < population:
                # Pick parent number #1
                parent_1_index = numpy.searchsorted(numpy.cumsum(fitnesses), numpy.random.rand())
                # Pick parent number #2, must be different to parent #1:
                parent_2_index = parent_1_index
                while parent_2_index == parent_1_index:
                    parent_2_index = numpy.searchsorted(numpy.cumsum(fitnesses), numpy.random.rand())
                parent_1 = previous_generation[parent_1_index]
                parent_2 = previous_generation[parent_2_index]
                # Now we have two parents. Let's mix their genomes:
                child_genome = {}
                child_mutation_biases = {}
                for name, param in parameters.items():
                    # Pick a point in parameter space from a uniform
                    # probability distribution along the line spanned
                    # by the two parents:
                    crossover_parameter = numpy.random.rand()
                    # The child will inherit mutation biases from
                    # whichever parent it is closest to in parameter
                    # space:
                    closest_parent = (parent_1,parent_2)[int(round(crossover_parameter))]
                    if name in parent_1.genome and name in parent_2.genome:
                        lim1, lim2 = parent_1[name], parent_2[name]
                        child_value = crossover_parameter*(lim2-lim1) + lim1
                        # Pick a mutation biasing direction from one of the parents:
                        mutation_bias = closest_parent.mutation_biases[name]
                        # Possibly mutate this direction, with probability 1/population:
                        if numpy.random.rand() < 1/population:
                            mutation_bias *= -1
                        child_mutation_biases[name] = mutation_bias
                        # Apply a Gaussian mutation and clip to keep in limits:
                        child_value = numpy.random.normal(child_value, param.mutation_rate)
                        mutation_value = abs(numpy.random.normal(0, param.mutation_rate))*mutation_bias
                        child_value += mutation_value
                        child_value = numpy.clip(child_value, param.min, param.max)
                    else:
                        # The parents don't have this
                        # parameter. Parameters must have changed,
                        # we need an initial value for this parameter:
                        if param.initial is None:
                            # Pick a random starting value within the range: 
                            child_value = numpy.random.rand()*(param.max-param.min) + param.min
                        else:
                            # Pick a value by applying one generation's worth
                            # of mutation to the initial value:
                            child_value = numpy.random.normal(param.initial, param.mutation_rate)
                            child_value = numpy.clip(value, param.min, param.max)
                        # Pick a random mutation biasing direction:
                        child_mutation_biases[name] = numpy.sign(numpy.random.normal())
                    child_genome[name] = child_value
                    
                # Congratulations, it's a boy!
                child = Individual(child_genome, child_mutation_biases, self)
                self.individuals.append(child)
                    
    def __iter__(self):
        return iter(self.individuals)
        
    def __getitem__(self, index):
        return self.individuals[index]

# Some convenient constants for accessing liststore columns:   

# Individual list store:       
GENERATION = 0
ID = 1
FITNESS_VISIBLE = 2
FITNESS = 3
COMPILE_PROGRESS_VISIBLE = 4
COMPILE_PROGRESS = 5
ERROR_VISIBLE = 6
WAITING_VISIBLE = 7
    
# Parameter liststore:
NAME = 0
MIN = 1
MAX = 2
MUTATION_RATE = 3
LOG = 4
 
class Mise(object):

    base_liststore_cols = ['generation', 
                           'id',
                           'fitness_visible',
                           'fitness',
                           'compile_progress_visible',
                           'compile_progress',
                           'error_visible',
                           'waiting_visible']
    
    base_liststore_types = {'generation': str, 
                            'id': str,
                            'fitness_visible': bool,
                            'fitness': str,
                            'compile_progress_visible': bool,
                            'compile_progress': int,
                            'error_visible': bool,
                            'waiting_visible': bool}
                            
    def __init__(self):
    
        # Make a gtk Builder with the user interface file:
        builder = gtk.Builder()
        builder.add_from_file('main.glade')
        
        # Get required objects from the builder:
        outputbox_container = builder.get_object('outputbox_container')
        self.window = builder.get_object('window')
        self.liststore_parameters = builder.get_object('liststore_parameters')
        self.treeview_individuals = builder.get_object('treeview_individuals')
        self.pause_button = builder.get_object('pause_button')
        self.box_paused = builder.get_object('paused')
        self.box_not_paused = builder.get_object('not_paused')
        self.label_labscript_file = builder.get_object('label_labscript_file')
        self.label_output_directory = builder.get_object('label_output_directory')
        self.spinbutton_population = builder.get_object('spinbutton_population')
        
        scrolledwindow_individuals = builder.get_object('scrolledwindow_individuals')
        self.adjustment_treeview_individuals = scrolledwindow_individuals.get_vadjustment()
        
        # Allow you to select multiple entries in the treeview:
        self.treeselection_individuals = self.treeview_individuals.get_selection()
        self.treeselection_individuals.set_mode(gtk.SELECTION_MULTIPLE)
        
        # Connect signals:
        builder.connect_signals(self)
        
        # Show the main window:
        self.window.show()
        
        # Make an output box for terminal output. Compilations will have their output streams
        # redirected to it over zmq sockets:
        self.outputbox = OutputBox(outputbox_container)
        
        # Get settings:
        config_path = os.path.join(config_prefix,'%s.ini'%socket.gethostname())
        required_config_params = {"paths":["experiment_shot_storage"],'ports':['mise']}
        self.config = LabConfig(config_path,required_config_params)

        # Start the web server:
        port = self.config.get('ports','mise')
        logger.info('starting web server on port %s'%port)
        self.server = WebServer(port)
    
        # A condition to let the looping threads know when to recheck conditions
        # they're waiting on (instead of having them do time.sleep)
        self.timing_condition = threading.Condition()
        
        self.params = {}
        self.labscript_file = None
        
        self.population = int(self.spinbutton_population.get_value())
        self.current_generation = None
        self.generations = []
        
        self.treeview_parameter_columns = []
        self.new_individual_liststore()
        
        # Start the compiler subprocess:
        runmanager_dir=os.path.dirname(runmanager.__file__)
        batch_compiler = os.path.join(runmanager_dir, 'batch_compiler.py')
        self.to_child, self.from_child, child = subprocess_with_queues(batch_compiler,self.outputbox.port)

        self.paused = False
        
        # Whether the last scroll to the bottom of the individuals treeview has been processed:
        self.scrolled = True
        
        # A thread which looks for un-compiled individuals and compiles
        # them, submitting them to BLACS:
        self.compile_thread = threading.Thread(target=self.compile_loop)
        self.compile_thread.daemon = True
        self.compile_thread.start()
        
        # A thread which looks for when all fitnesses have come back,
        # and spawns a new generation when they have:
        self.reproduction_thread = threading.Thread(target=self.reproduction_loop)
        self.reproduction_thread.daemon = True
        self.reproduction_thread.start()
        
        logger.info('init done')
    
    def destroy(self, widget):
        logger.info('destroy')
        gtk.main_quit()
    
    def error_dialog(self, message):
        dialog =  gtk.MessageDialog(self.window, gtk.DIALOG_DESTROY_WITH_PARENT, gtk.MESSAGE_WARNING, 
                                    buttons=(gtk.BUTTONS_OK), message_format = message)
        result = dialog.run()
        dialog.destroy()
    
    def scroll_to_bottom(self):
        with gtk.gdk.lock:
            self.adjustment_treeview_individuals.set_value(
                self.adjustment_treeview_individuals.upper - self.adjustment_treeview_individuals.page_size)
        self.scrolled = True
               
    def on_pause_button_toggled(self,button):
        if button.get_active():
            self.paused = True
            self.box_paused.show()
            self.box_not_paused.hide()
        else:
            self.paused = False
            self.box_paused.hide()
            self.box_not_paused.show()
            with self.timing_condition:
                self.timing_condition.notify_all()
    
    def on_spinbutton_population_value_changed(self, widget):
        self.population = int(self.spinbutton_population.get_value())
        print self.population
    
    def on_parameter_min_edited(self, renderer, rowindex, value):
        row = self.liststore_parameters[int(rowindex)]
        name = row[NAME]
        param = self.params[name]
        try:
            value = float(eval(value))
        except Exception as e:
            self.error_dialog(str(e))
            return
        if value >= param.max:
            self.error_dialog('Must have min < max.')
            return
        param.min = value
        row[MIN] = value
    
    def on_parameter_max_edited(self, renderer, rowindex, value):
        row = self.liststore_parameters[int(rowindex)]
        name = row[NAME]
        param = self.params[name]
        try:
            value = float(eval(value))
        except Exception as e:
            self.error_dialog(str(e))
            return
        if value <= param.min:
            self.error_dialog('Must have max > min.')
            return
        param.max = value
        row[MAX] = value
        
    def on_parameter_mutationrate_edited(self, renderer, rowindex, value):
        row = self.liststore_parameters[int(rowindex)]
        name = row[NAME]
        param = self.params[name]
        try:
            value = float(eval(value))
        except Exception as e:
            self.error_dialog(str(e))
            return
        param.mutation_rate = value
        row[MUTATION_RATE] = value
    
    def on_parameter_logarithmic_toggled(self, renderer, rowindex):
        row = self.liststore_parameters[int(rowindex)]
        name = row[NAME]
        param = self.params[name]
        param.log = not param.log
        row[LOG] = param.log
                   
    def receive_parameter_space(self, runmanager_data):
        """Receive a parameter space dictionary from runmanger"""
        (labscript_file, sequenceglobals, shots, 
             output_folder, shuffle, BLACS_server, BLACS_port, shared_drive_prefix) = runmanager_data
        self.params = {}
        self.liststore_parameters.clear()
        # Pull out the MiseParameters:
        first_shot = shots[0]
        for name, value in first_shot.items():
            if isinstance(value, MiseParameter):
                data = [name, value.min, value.max, value.mutation_rate]
                self.liststore_parameters.append(data)
                self.params[name] = value
        self.new_individual_liststore()
        if self.current_generation is None:
            self.new_generation()
        self.labscript_file = labscript_file
        self.sequenceglobals = sequenceglobals
        self.shots = shots
        self.output_folder = output_folder
        self.shuffle = shuffle
        self.BLACS_server = BLACS_server
        self.BLACS_port = BLACS_port
        self.shared_drive_prefix = shared_drive_prefix
            
        self.label_labscript_file.set_text(self.labscript_file)
        self.label_output_directory.set_text(self.output_folder)
        # Let waiting threads know that there might be new state for them to check:
        with self.timing_condition:
            self.timing_condition.notify_all()
        return True, 'optimisation request added successfully\n'

    def report_fitness(self, individual_id, fitness):
        found = False
        if self.current_generation is None:
            return False, 'mise is not initialised, there are no individuals requiring fitness reports.'
        for individual in self.current_generation:
            if individual.id == individual_id:
                found = True
                break
        if not found:
            return False, 'individual with id %d not found in current generation'%individual_id
        individual.fitness = fitness
        self.set_value(individual, FITNESS, fitness)
        individual.fitness_visible = True
        self.set_value(individual, FITNESS_VISIBLE, individual.fitness_visible)
        individual.waiting_visible = False
        self.set_value(individual, WAITING_VISIBLE, individual.waiting_visible)
        # The reproduction_loop will want to check whether its time for a new generation:
        with self.timing_condition:
            self.timing_condition.notify_all()
        return True, None
    
    def append_generation_to_liststore(self, generation):
        for individual in generation:
            row = [generation.id, 
                   individual.id, 
                   individual.fitness_visible, 
                   individual.fitness,
                   individual.compile_progress_visible,
                   individual.compile_progress,
                   individual.error_visible,
                   individual.waiting_visible]
            row += [individual[name] for name in self.params]
            self.liststore_individuals.append(row)
            
    def new_individual_liststore(self):
        column_names = self.base_liststore_cols + self.params.keys()
        column_types = [self.base_liststore_types[name] for name in self.base_liststore_cols]  + [str for name in self.params]
        self.liststore_individuals = gtk.ListStore(*column_types)
        self.treeview_individuals.set_model(self.liststore_individuals)
        for generation in self.generations:
            self.append_generation_to_liststore(generation)
        # Make sure the Treeview has columns for the current parameters:
        for param_name in self.params:
            if not param_name in self.treeview_parameter_columns:
                self.treeview_parameter_columns.append(param_name)
                model_column_index = column_names.index(param_name)
                renderer = gtk.CellRendererText()
                widget = gtk.HBox()
                heading = gtk.Label(param_name)
                heading.show()
                column = gtk.TreeViewColumn()
                column.pack_start(renderer)
                column.set_widget(heading)
                column.add_attribute(renderer, 'text', model_column_index)
                column.set_resizable(True)
                column.set_reorderable(True)
                self.treeview_individuals.append_column(column)
                
    def set_value(self, individual, column, value):
        """Searches the liststore for the individual, setting the
        value of a particular column in the individual's row. Raises
        IndividualNotFound if the row is not found. You must acquire
        the gtk lock before calling this method."""
        for row in self.liststore_individuals:
            if int(row[ID]) == individual.id:
                row[column] = value
                return
        raise IndividualNotFound


    def on_button_delete_individuals_clicked(self, button):
        model, selection = self.treeselection_individuals.get_selected_rows()
        # Have to delete one at a time, since the indices change after
        # each deletion:
        while selection:
            path = selection[0]
            iter = model.get_iter(path)
            individual_id = int(model.get_value(iter, ID))
            # Delete the individual's entry from the liststore:
            model.remove(iter)
            # Get the individual itself:
            individual =  Individual.all_individuals[individual_id]
            # Delete it from the record of all individuals:
            del Individual.all_individuals[individual_id]
            # Delete it from its parent generation's record of individuals:
            generation = individual.generation
            generation.individuals.remove(individual)
            # Update selection now that deletion of this individual is complete:
            selection = self.treeview_individuals.get_selection()
            model, selection = selection.get_selected_rows()

    def on_button_mark_uncompiled_clicked(self,button):
        model, selection = self.treeselection_individuals.get_selected_rows()
        for path in selection:
            iter = model.get_iter(path)
            individual_id = int(model.get_value(iter, ID))
            individual =  Individual.all_individuals[individual_id]
            if individual.compile_progress == 100:
                individual.compile_progress = 0
                self.set_value(individual, COMPILE_PROGRESS, individual.compile_progress)
                individual.compile_progress_visible = True
                self.set_value(individual, COMPILE_PROGRESS_VISIBLE, individual.compile_progress_visible)
                individual.error_visible = False
                self.set_value(individual, ERROR_VISIBLE, individual.error_visible)
                individual.waiting_visible = False
                self.set_value(individual, WAITING_VISIBLE, individual.waiting_visible)
                individual.fitness = None
                self.set_value(individual, FITNESS, individual.fitness)
                individual.fitness_visible = False
                self.set_value(individual, FITNESS_VISIBLE, individual.fitness_visible)
            with self.timing_condition:
                self.timing_condition.notify_all()
           
    def on_button_clear_fitness_clicked(self,button):
        model, selection = self.treeselection_individuals.get_selected_rows()
        for path in selection:
            iter = model.get_iter(path)
            individual_id = int(model.get_value(iter, ID))
            individual =  Individual.all_individuals[individual_id]
            if individual.fitness is not None:
                individual.waiting_visible = True
                self.set_value(individual, WAITING_VISIBLE, individual.waiting_visible)
                individual.fitness = None
                self.set_value(individual, FITNESS, individual.fitness)
                individual.fitness_visible = False
                self.set_value(individual, FITNESS_VISIBLE, individual.fitness_visible) 
            
    def compile_one_individual(self,individual):
        # Create a list of shot globals for this individual, by copying
        # self.shots and replacing MiseParameters with their values for
        # this individual:
        shots = []
        for shot in self.shots:
            this_shot = shot.copy()
            for param_name in individual.genome:
                this_shot[param_name] = individual[param_name]
            shots.append(this_shot)
        # Create run files:
        sequence_id = runmanager.generate_sequence_id(self.labscript_file) + '_g%di%d'%(self.current_generation.id, individual.id)
        n_run_files = len(shots)
        try:
            run_files = runmanager.make_run_files(self.output_folder, self.sequenceglobals, shots, sequence_id, self.shuffle)
            with gtk.gdk.lock:
                individual.error_visible = False
                self.set_value(individual, ERROR_VISIBLE, individual.error_visible)
            for i, run_file in enumerate(run_files):
                with h5py.File(run_file) as hdf5_file:
                    hdf5_file.attrs['individual id'] = individual.id
                    hdf5_file.attrs['generation'] = self.current_generation.id
                self.to_child.put(['compile',[self.labscript_file,run_file]])
                while True:
                    signal,data = self.from_child.get()
                    if signal == 'done':
                        success = data
                        break
                    else:
                        raise RuntimeError((signal, data))
                if not success:
                    raise Exception
                else:
                    with gtk.gdk.lock:
                        individual.compile_progress = 100*float(i+1)/n_run_files
                        self.set_value(individual, COMPILE_PROGRESS, individual.compile_progress)
                        if individual.compile_progress == 100:
                            individual.compile_progress_visible = False
                            self.set_value(individual, COMPILE_PROGRESS_VISIBLE, individual.compile_progress_visible)
                            individual.waiting_visible = True
                            self.set_value(individual, WAITING_VISIBLE, individual.waiting_visible)
                    self.submit_job(run_file)
                    
        except IndividualNotFound:
            # The Individial has been deleted at some point. It's gone,
            # so we don't have to worry about where we were up to with
            # anything. It will be garbage collected....now:
            return
            
        except Exception as e :
            # Couldn't make or run files, couldn't compile, or couldn't
            # submit. Print the error, pause mise, and display error icon:
            self.outputbox.output(str(e) + '\n', red = True)
            with gtk.gdk.lock:
                self.pause_button.set_active(True)
                individual.compile_progress = 0
                self.set_value(individual, COMPILE_PROGRESS, individual.compile_progress)
                individual.compile_progress_visible = False
                self.set_value(individual, COMPILE_PROGRESS_VISIBLE, individual.compile_progress_visible)
                individual.error_visible = True
                self.set_value(individual, ERROR_VISIBLE, individual.error_visible)
                individual.waiting_visible = False
                self.set_value(individual, WAITING_VISIBLE, individual.waiting_visible)
            
   
    def submit_job(self, run_file):
        # Workaround to force python not to use IPv6 for the request:
        host = socket.gethostbyname(self.BLACS_server)
        agnostic_path = labscript_utils.shared_drive.path_to_agnostic(run_file)
        self.outputbox.output('Submitting run file %s.\n'%os.path.basename(run_file))
        try:
            response = zmq_get(self.BLACS_port, host, data=agnostic_path)
            if 'added successfully' in response:
                self.outputbox.output(response)
            else:
                raise Exception(response)
        except Exception as e:
            self.outputbox.output('Couldn\'t submit job to control server: %s\n'%str(e),red=True)
            raise
  
    def compile_loop(self):
        while True:
            with self.timing_condition:
                while self.paused or self.current_generation is None:
                    self.timing_condition.wait()
                logger.info('compile loop iteration')
                # Get the next individual requiring compilation:
                compile_required = False
                for individual in self.current_generation:
                    if individual.compile_progress == 0:
                        logger.info('individual %d needs compiling'%individual.id)
                        compile_required = True
                        break
                # If we didn't find any individuals requiring compilation,
                # wait until a timing_condition notification before checking
                # again:
                if not compile_required:
                    logger.info('no individuals requiring compilation')
                    self.timing_condition.wait()
                    continue
            # OK, we have an individual which requires compilation.
            self.compile_one_individual(individual)
                    
    def reproduction_loop(self):
        while True:
            while self.paused or self.current_generation is None:
                with self.timing_condition:
                    self.timing_condition.wait()
            logger.info('reproduction loop iteration')
            if not all([individual.fitness is not None for individual in self.current_generation]):
                # Still waiting on at least one individual, do not spawn a new generation yet
                with self.timing_condition:
                    self.timing_condition.wait()
                    continue
            # OK, all fitnesses are reported. Mating season is upon us:
            with gtk.gdk.lock:
                self.new_generation()
                    
    def new_generation(self):
        self.current_generation = Generation(self.population, self.params, self.current_generation)
        self.generations.append(self.current_generation)
        self.append_generation_to_liststore(self.current_generation)
        if self.scrolled:
            # Are we scrolled to the bottom of the TreeView?
            if self.adjustment_treeview_individuals.value == self.adjustment_treeview_individuals.upper - self.adjustment_treeview_individuals.page_size:
                self.scrolled = False                 
                gobject.idle_add(self.scroll_to_bottom)
        # There are new individuals, the compile_loop will want to know about this:
        with self.timing_condition:
            self.timing_condition.notify_all()
            
if __name__ == '__main__':
    gtk.threads_init()
    app = Mise()
    with gtk.gdk.lock:
        gtk.main()    
