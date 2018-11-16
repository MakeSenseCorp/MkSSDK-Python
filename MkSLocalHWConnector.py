#!/usr/bin/python
import os
import sys
import json

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
		request 	= "{\"cmd\":\"get_device_uuid\",\"payload\":{}}"
		response 	= self.LocalDevice.Send(request)

		jsonData 	= json.loads(response)
		return jsonData["payload"]["uuid"]

	def GetDeviceInfo(self):
		request 	= "{\"cmd\":\"get_device_info\",\"payload\":{}}"
		response 	= self.LocalDevice.Send(request)

		jsonData 	= json.loads(response)
		return jsonData["payload"]

	def SetSensorInfo(self, info):
		request 	= "{\"cmd\":\"set_sensor_info\",\"payload\":" + info + "}"
		response 	= self.LocalDevice.Send(request)

		jsonData 	= json.loads(response)
		return jsonData["payload"]

	def GetSensorInfo(self, info):
		request 	= "{\"cmd\":\"get_sensor_info\",\"payload\":" + info + "}"
		response 	= self.LocalDevice.Send(request)

		jsonData 	= json.loads(response)
		return jsonData["payload"]

	def GetSensorListInfo(self):
		request 	= "{\"cmd\":\"get_sensor_list_info\",\"payload\":{}}"
		response 	= self.LocalDevice.Send(request)

		# print response
		jsonData 	= json.loads(response)
		return jsonData["payload"]