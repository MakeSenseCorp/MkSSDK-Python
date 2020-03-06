#!/usr/bin/python
import os
import sys
import json
if sys.version_info[0] < 3:
	import thread
else:
	import _thread
import threading

class AbstractConnector():
	def __init__(self):
		self.Protocol 		= None
		self.Adaptor 		= None
		# Flags
		self.IsConnected = False
		# Callbacks
		self.OnDeviceDisconnectCallback = None

	def SetProtocol(self, protocol):
		self.Protocol = protocol

	def SetAdaptor(self, adaptor):
		self.Adaptor = adaptor

	def Connect(self, type):
		return self.IsConnected

	def Disconnect(self):
		return self.IsConnected

	def IsValidDevice(self):
		return True

	def GetUUID(self):
		return ""

	def GetDeviceInfo(self):
		return ""
