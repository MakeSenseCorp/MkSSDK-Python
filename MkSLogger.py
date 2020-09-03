#!/usr/bin/python
import os
import sys
import logging
import json
import datetime
from datetime import date

if sys.version_info[0] < 3:
	import thread
else:
	import _thread
import threading

from mksdk import MkSFile
from mksdk import MkSQueue

class Logger():
    def __init__(self, name):
        self.ClassName          = "Logger"
        self.Name               = name
        self.Locker             = threading.Lock()
        self.LogerEnabled       = False
        self.Logger             = None
        self.Print              = False
        self.LoggerType         = "MKS"
        self.Path               = ""
        self.Queue              = MkSQueue.Manager(self.Callback)
        self.LogType            = 5
        self.LogTypeMap         = {
            "1": "DEBUG",
            "2": "CRITICAL",
            "3": "ERROR",
            "4": "WARNNING",
            "5": "INFO",
            "6": "FRIENDLY",
            "7": "NONE"
        }

        self.Queue.Start()
    
    def Callback(self, item):
        try:
            lvl = item["level"]
            if str(lvl) in self.LogTypeMap:
                log_type = self.LogTypeMap[str(lvl)]
                if lvl >= self.LogType:
                    message = item["message"]
                    if self.LogerEnabled is True:
                        if self.Logger is not None:
                            if self.LoggerType == "MKS":
                                today = datetime.datetime.today()
                                date = today.strftime("(%a %b.%d.%Y) (%H:%M:%S)")
                                msg = "{0} - [{1}] - ({2}) - {3}\n".format(date, log_type, item["thread_id"], message)
                                self.Logger.Append(self.Path, msg)
                            elif self.LoggerType == "DEFAULT":
                                self.Logger.info(message)
                            else:
                                pass
                    if self.Print is True:
                        print(message)
        except Exception as e:
            print("({classname})# ERROR - [LocalQueueWorker] {error}".format(classname=self.ClassName,error=str(e)))
    
    def EnablePrint(self):
        self.Print = True
    
    def SetLogLevel(self, level):
        self.LogType = level

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

    def Log(self, message, level):
        self.Locker.acquire()
        try:
            self.Queue.QueueItem({
                "thread_id": 1,
                "level": level,
                "message": message
            })
        except Exception as e:
            print("({classname})# [Log] ERROR".format(classname=self.ClassName))
        self.Locker.release()