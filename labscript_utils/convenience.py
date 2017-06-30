# -*- coding: utf-8 -*-
"""
Created on Fri Jun 19 09:16:29 2015

@author: Ian Spielman

Contains simple utilities that many functions can call
"""

def ValidName(name, RaiseError=False):
    try:
        # Test that name is a valid Python variable name:
        exec '%s = None'%name
        assert '.' not in name
    except:
        if RaiseError:
            raise ValueError('%s is not a valid Python variable name.'%name)

        return False
    return True