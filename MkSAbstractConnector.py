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

	def SetProtocol(self, protocol):
		self.Protocol = protocol

	def SetAdaptor(self, adaptor):
		self.Adaptor = adaptor

	def Connect(self):
		return True

	def Disconnect(self):
		return True

	def IsValidDevice(self):
		return True

	def GetUUID(self):
		return ""

	def SetSensorInfo(self, info):
		return True

	def GetSensorInfo(self):
		return ""