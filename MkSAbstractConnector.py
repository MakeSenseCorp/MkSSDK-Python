#!/usr/bin/python
import os
import sys
import json
import thread
import threading

class AbstractConnector():
	def __init__(self):
		self.Protocol 		= None
		self.Adaptor 		= None

	def SetProtocol(self, protocol):
		self.Protocol = protocol

	def SetAdaptor(self, adaptor):
		self.Adaptor = adaptor