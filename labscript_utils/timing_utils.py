# -*- coding: utf-8 -*-
"""
Created on Sun May 24 22:08:53 2015

This file provides tools for better locking of timing in python programs

@author: Ian Spielman
"""

import time
from Queue import Queue
from threading import Thread

#
# Thread programs that run independentally and monitor timing
#

def SleepUntil(delay, timing_queue):
    time.sleep(delay)
    timing_queue.put("done")

def Countdown(delay, countdown_queue, interval, countdown_mode):
    """
    This is for sending a timing stream to a queue, for example
    for making a progress bar.  interval is the time between updates
    to the queue.
    """
    if interval > delay:
        interval = delay
    
    num = int(delay / interval)
    true_interval = delay / num

    initial_time = time.time()
    final_time = initial_time + delay
    for i in range(num):
        sleep_time = max(
            (i+1)*true_interval - (time.time()-initial_time), 
            0)
        time.sleep(sleep_time)
        remainig_time = max(final_time - time.time(),0)
        if countdown_mode == 'precent_remaining':
            remainig_time = 100*remainig_time/delay
        elif countdown_mode == 'precent_done': 
            remainig_time = 100*(1-remainig_time/delay)
        countdown_queue.put(remainig_time)

#
# Main timing class
# 

class timer():
    """
    provides ability to block program execution until time limit has expired
    
    privides a method to send ticks via a queue to other programs    
    
    Unlike sleep, you can start a timer, perform some computations and then
    wait until the time has elapsed.
    """

    def __init__(self, delay=0):
        """
        Setup timer
        """
        
        # status monitor if we are timing
        self._timing = False
        
        # expected delay time
        self._delay = delay       
        
        # Start time
        self._start_time = time.time()
        
        # queue to contacting timing thread    
        self._timing_queue = Queue()
    
    def _timer_done(self):
        self._timing = False
            
    def start(self, delay=None, countdown_queue=None, interval=1.0, countdown_mode=None):
        """
        Start a timer that will expire after delay seconds
        
        if countdown_queue is passed we will start a second thread
        that puts the remaining time into that queue updated every interval
        
        if countdown_mode == 'precent_remaining' then countdown monitor will monitor precent remaining
        if countdown_mode == 'precent_done' then countdown monitor will monitor precent done
        """
        
        if delay is not None:
            self._delay = delay
        
        if self._timing == True:
            raise RuntimeError('already timing')
        
        # Do not start a timer for zero or negative times.
        if delay <= 0:
            # just cleanup
            self._timer_done()
            return
        
        self._timing = True
        
        # Start a thread that will sleep for delay seconds, and empty queue
        while self._timing_queue.qsize()>0: self._timing_queue.get()
        SleepWorker = Thread(target=SleepUntil, args=(self._delay, self._timing_queue))
        SleepWorker.setDaemon(True)

        if countdown_queue is not None:
            CountdownWorker = Thread(target=Countdown, args=(self._delay, countdown_queue, interval, countdown_mode))
            CountdownWorker.setDaemon(True)
            CountdownWorker.start()

        SleepWorker.start()
        self._start_time = time.time()
    
    def elapsed(self):
        """
        time since timer started
        """
        
        if self.check():
            return time.time() -  self._start_time    
        else:
            return self._delay

    def remaining(self):
        """
        time reamining on timer
        """
        
        return self._delay - self.elapsed()


    def check(self):
        """
        see if a timer is running
        """
        
        # if we are not timing right now, just return
        if not self._timing:
            return False
        else:
            try:
                response = self._timing_queue.get_nowait()                
            except: 
                # Nothing in queue yet and still timing
                return True
            else:
                # did get a response
                self._timer_done()
                if response == 'done':
                    return False
                else:
                    raise RuntimeError('invalid response from timer worker')
        
    def wait(self):
        """
        wait until timer expires
        
        returns the amount of time waited in this function
        """
        
        # if we are not timing right now, just return
        if not self._timing:
            return 0.0
        else:
            start_time = time.time()
            response = self._timing_queue.get()
            self._timer_done()
            if response == 'done':
                return time.time() - start_time
            else:
                raise RuntimeError('invalid response from timer worker')
                return 0.0
                 