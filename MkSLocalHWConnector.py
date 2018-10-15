#!/usr/bin/python
import os
import sys
import json
import thread
import threading

from mksdk import MkSAbstractConnector

class LocalHWConnector(MkSAbstractConnector.AbstractConnector):
	def __init__(self, local_device):
		MkSAbstractConnector.AbstractConnector.__init__(self, local_device)

	def Connect(self, type):
		# Param type is mainly for checking if we are on
		# the correct device.
		self.IsConnected = self.LocalDevice.Connect()
		return self.IsConnected

	def Disconnect(self):
		self.IsConnected = self.LocalDevice.Disconnect()
		return self.IsConnected

	def IsValidDevice(self):
		request = "JSON"
		return True

	def GetUUID(self):
		request = "JSON"
		return ""

	def GetDeviceInfo(self):
		request = "{\"cmd\":\"get_device_info\",\"payload\":\"\"}"
		response = self.LocalDevice.Send(request)
		return response

	def SetSensorInfo(self, info):
		request = "JSON"
		return True

	def GetSensorInfo(self):
		request = "JSON"
		return ""