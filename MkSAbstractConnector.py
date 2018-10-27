#!/usr/bin/python
import os
import sys
import json
import thread
import threading

class AbstractConnector():
	def __init__(self, local_device):
		self.Protocol 		= None
		self.Adaptor 		= None
		self.LocalDevice 	= local_device
		# Flags
		self.IsConnected = False
		# Callbacks
		self.SetDeviceDisconnectCallback = None

	def SetProtocol(self, protocol):
		self.Protocol = protocol

	def SetAdaptor(self, adaptor):
		self.Adaptor = adaptor

	def SetDeviceDisconnectCallback(self, callback):
		pass

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

	def SetSensorInfo(self, info):
		return True

	def GetSensorInfo(self):
		return ""

	def GetSensorListInfo(self):
		return ""