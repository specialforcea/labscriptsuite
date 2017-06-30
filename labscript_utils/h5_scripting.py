# -*- coding: utf-8 -*-
"""
Created on Thu May 21 09:35:44 2015

@author: Ian Spielman
"""

import os
import sys
import ast
import linecache

import h5_lock, h5py

def exec_in_namespace(code, namespace):
    if sys.version < '3':
        exec("""exec code in namespace""")
    else:
        if isinstance(__builtins__, dict):
            exec_func = __builtins__['exec']
        else:
            exec_func = getattr(__builtins__, 'exec')
        exec_func(code, namespace) 

    
class attached_function(object):

    """
    Decorator that saves the decorated function to an h5 file.

    A function decorator that saves the source of the decorated function
    as a dataset within the hdf5 file, along with other data for how the
    function should be called.

    filename : h5 file to use. This will be passed to automatically
        to the saved function as its first argument.

    groupname : what group in the h5 file to save the dataset to.
        Defaults to 'post_process'.
        
    args : list or tuple of arguments that will be automatically passed
        to the function, after the filename argument.
        
    kwargs: dictionary of keyword arguments that will be automatically passed
        to the function.

    note: function should be written assuming that it enters life in
        an empty namespace. This decorator modifies the defined function
        to run in an empty namespace, and to be called with the provided
        arguments and keyword arguments.
    """

    def __init__(self, hdf5_file, groupname='post_process', args=None, kwargs=None):
        self.hdf5_file = hdf5_file
        self.groupname = groupname
        self.args = args
        self.kwargs = kwargs
        
    def __call__(self, function):
        import inspect
        
        name = function.__name__

        function_name = function.__name__
        
        if self.args is None:
            args = []
        else:
            args = self.args
        if not (isinstance(args, list) or isinstance(args, tuple)):
            raise TypeError('args must be a list or a tuple')
        function_args = repr(args)
        try:
            assert ast.literal_eval(function_args) == args
        except Exception:
            raise ValueError('Argument list can contain only Python literals')
        
        if self.kwargs is None:
            kwargs = {}
        else:
            kwargs = self.kwargs
        if not isinstance(kwargs, dict):
            raise TypeError('kwargs must be a dictionary')
        function_kwargs = repr(kwargs)
        try:
            assert ast.literal_eval(function_kwargs) == kwargs
        except Exception:
            raise TypeError('Keyword argument list can contain only Python literals')
            
        try:
            # This is a bug workaround for a cache that is present that blocks
            # updates to these functions!
            linecache.clearcache()
            function_source = inspect.getsource(function)
        except Exception:
            raise TypeError('Could not get source code of %s %s. '%(type(function).__name__, repr(function)) + 
                            'Only ordinary Python functions defined in Python source code can be saved.')
            
        function_lines = function_source.splitlines()
        indentation = min(len(line) - len(line.lstrip(' ')) for line in function_lines)
        # Remove this decorator from the source, if present:
        if function_lines[0][indentation:].startswith('@'):
            del function_lines[0]
        # Remove initial indentation from the source:
        function_source = '\n'.join(line[indentation:] for line in function_lines)

        group = self.hdf5_file.require_group(self.groupname)
        try:
            del group[name]
        except KeyError:
            pass
        dataset = group.create_dataset(name, data=function_source)
        dataset.attrs['__h5scripting__function_name__'] = function_name
        dataset.attrs['__h5scripting__function_args__'] = function_args
        dataset.attrs['__h5scripting__function_kwargs__'] = function_kwargs


def attach_function(function, hdf5_file, groupname='post_process', args=None, kwargs=None):
    """
    Saves the source of a function to an h5 file.

    This is exactly the same as the attached_function decorator, except
    that one passes in the function to be saved as the firt argument instead
    of decorating its definition. Returns the sandboxed version of the function.
    
    function : The function to save

    All other arguments are the same as in the attached_function decorator.
    
    note: The function's source code must be self contained and introspectable
        by Python, that means no lambdas, class/instance methods, functools.partial
        objects, C extensions etc, only ordinary Python functions.
    """
    attacher = attached_function(hdf5_file, groupname, args, kwargs)
    attacher(function)
 

class SavedFunction(object):
    def __init__(self, h5_filename, dataset):
        """provides a callable from the function saved in the provided dataset.
        
        filename: The name of the (currently open) h5 file the 
        
        This callable executes in an empty namespace, and so does not have
        access to global and local variables in the calling scope.

        When called, it automatically receives 'filename' as its first
        argument, args and kwargs as its arguments and keyword arguments."""
        
        import functools
        
        function_source = dataset.value
        function_name = dataset.attrs['__h5scripting__function_name__']
        function_args = ast.literal_eval(dataset.attrs['__h5scripting__function_args__'])
        function_kwargs = ast.literal_eval(dataset.attrs['__h5scripting__function_kwargs__'])
        
        # Exec the function definition to get the function object:
        sandbox_namespace = {}
        exec_in_namespace(function_source, sandbox_namespace)
        function = sandbox_namespace[function_name]
    
        self._function = function
        self.name = dataset.name
        self.function_source = function_source
        self.function_name = function_name
        self.function_args = function_args
        self.function_kwargs = function_kwargs
        self.h5_filename = h5_filename
        functools.update_wrapper(self, function)
        
    def __call__(self, *args, **kwargs):
        """Calls the wrapped function in an empty namespace. Returns the result.
        If keyword arguments are provided, these override the saved keyword arguments.
        Positional arguiments cannot be overridden, please use custom_call() for that.."""
        if args:
            message = ("To call this SavedFunction with custom positional arguments, please call  the custom_call()', " +
                       "method, passing in all desired arguments and keyword arguments.")
            raise TypeError(message)
        sandbox_kwargs = self.function_kwargs.copy()
        sandbox_kwargs.update(kwargs)
        return self.custom_call(*self.function_args, **sandbox_kwargs)
            
    def custom_call(self, *args, **kwargs):
        """Call the wrapped function with custom positional and keyword arguments."""
        # Names mangled to reduce risk of colliding with the function
        # attempting to access global variables (which it shouldn't be doing):
        with h5py.File(self.h5_filename, "r") as h5_file:
            sandbox_namespace = {'__h5s_file': h5_file,
                                 '__h5s_function': self._function,
                                 '__h5s_args': args,
                                 '__h5s_kwargs': kwargs}
            exc_line = '__h5s_result = __h5s_function(__h5s_file, *__h5s_args, **__h5s_kwargs)'
            exec_in_namespace(exc_line, sandbox_namespace)
            result = sandbox_namespace['__h5s_result']
        return result
        

        
def get_saved_function(filename, name, groupname='post_process'):
    """
    Retrieves a previously saved function from the h5 file.

    The function is returned as a callable that will run in an
    empty namespace with no access to global or local variables
    in the calling scope.

    filename : h5 file to use

    name : the name of the dataset to which the function is saved.
        if this was not set when saving the function with
        attach_function() or attached_function(), then this
        is the name of the function itself.

    groupname : the group in the h5 file to which the function is saved.
        Defaults to 'saved_functions'
        
    returns saved_function
    """

    with h5py.File(filename, "r") as f:
        grp = f.getitem(groupname)
        dataset = grp.getitem(name)
        saved_function = SavedFunction(filename, dataset)
    
    return saved_function
    
def get_all_saved_functions(filename, groupname='post_process'):
    """
    returns all the saved functions in the group deined by groupname as 
    a list of the form:
    
    [saved_function, ]
    
    This assumes that all of the datasets in groupname are saved functions.
    """
    
    saved_functions = []
    with h5py.File(filename, "r",) as f:
        grp = f[groupname]
        
        for dataset in grp.values():
            saved_functions += [SavedFunction(filename, dataset)]

    return saved_functions
