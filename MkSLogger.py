#!/usr/bin/python
import os
import sys
import logging
import json
import datetime
from datetime import date

from mksdk import MkSFile
from mksdk import MkSQueue

class Logger():
    def __init__(self, name):
        self.Name               = name
        self.LogerEnabled       = False
        self.Logger             = None
        self.Print              = False
        self.LoggerType         = "MKS"
        self.Path               = ""
        self.Queue              = MkSQueue.Manager(self.Callback)
    
    def Callback(self, item):
        if self.LogerEnabled is True:
            log_Type = "INFO"
            try:
                message = item["message"]
                if self.Logger is not None:
                    if self.LoggerType == "MKS":
                        today = datetime.datetime.today()
                        date = today.strftime("(%a %b.%d.%Y) (%H:%M:%S)")
                        msg = "{0} - [{1}] - ({2}) - {3}\n".format(date, log_Type, item["thread_id"], message)
                        self.Logger.Append(self.Path, msg)
                    elif self.LoggerType == "DEFAULT":
                        self.Logger.info(message)
                    else:
                        pass
                    
                if self.Print is True:
                    print(message)
            except Exception as e:
                self.Logger.Log("({classname})# ERROR - [LocalQueueWorker] {error}".format(classname=self.ClassName,error=str(e)))
    
    def EnablePrint(self):
        self.Print = True

    def EnableLogger(self):
        self.Path = os.path.join('..','..','logs','{0}.log'.format(self.Name))
        if self.LoggerType == "MKS":
            self.Logger = MkSFile.File()
            self.LogerEnabled = True
        elif self.LoggerType == "DEFAULT":
            self.Logger = logging.getLogger(self.Name)
            self.Logger.setLevel(logging.DEBUG)
            hndl = logging.FileHandler(self.Path)
            formatter = logging.Formatter('%(asctime)s - %(message)s')
            hndl.setFormatter(formatter)
            self.Logger.addHandler(hndl)
            self.LogerEnabled = True
        else:
            pass
    
        if self.LogerEnabled is True:
            self.Queue.Start()

    def Log(self, message):
        if self.LogerEnabled is True:
            try:
                self.Queue.QueueItem({
                    "thread_id": 1,
                    "message": message
                })
            except Exception as e:
                print("({classname})# [Log] ERROR".format(classname=self.ClassName))