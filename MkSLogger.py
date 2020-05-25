#!/usr/bin/python
import os
import sys
import logging
import threading

class Logger():
    def __init__(self, name):
        self.Name               = name
        self.LogerEnabled       = False
        self.Logger             = None
        self.Print              = False
        self.Locker				= threading.Lock()
    
    def EnablePrint(self):
        self.Print = True

    def EnableLogger(self):
        self.LogerEnabled = True
        self.Logger = logging.getLogger(self.Name)
        self.Logger.setLevel(logging.DEBUG)
        hndl = logging.FileHandler(os.path.join('..','..','logs','{0}.log'.format(self.Name)))
        formatter = logging.Formatter('%(asctime)s - %(message)s')
        hndl.setFormatter(formatter)
        self.Logger.addHandler(hndl)

    def Log(self, message):
        self.Locker.acquire()
        try:
            if self.Logger is not None:
                self.Logger.info(message)
            if self.Print is True:
                print(message)
        except Exception as e:
            print("({classname})# [Log] ERROR".format(classname=self.ClassName))
        self.Locker.release()