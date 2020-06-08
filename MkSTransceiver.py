#!/usr/bin/python
import os
import sys
import json

from mksdk import MkSQueue
from mksdk import MkSLogger

class Manager():
    def __init__(self, tx_callback, rx_callback):
        self.ClassName		    = "MkSTransceiver"
        self.TXQueue            = MkSQueue.Manager(tx_callback)
        self.RXQueue            = MkSQueue.Manager(rx_callback)

        self.TXQueue.Start()
        self.RXQueue.Start()
    
    def Send(self, item):
        if self.TXQueue is not None:
            self.TXQueue.QueueItem(item)
            return True
        return False
    
    def Receive(self, item):
        if self.RXQueue is not None:
            self.RXQueue.QueueItem(item)
            return True
        return False
