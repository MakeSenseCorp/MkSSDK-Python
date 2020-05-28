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
        self.TXQueue.QueueItem(item)
    
    def Receive(self, item):
        self.RXQueue.QueueItem(item)
