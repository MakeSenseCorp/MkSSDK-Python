#!/usr/bin/python
import os
import time
import struct
import json

import MkSUSBAdaptor
import MkSProtocol

from mksdk import MkSAbstractConnector

class Connector (MkSAbstractConnector.AbstractConnector):
	def __init__ (self, local_device):
		MkSAbstractConnector.AbstractConnector.__init__(self, local_device)

	def Connect (self, device_type):
		idx = 1
		deviceFound = False
		for item in self.Adaptor.Interfaces:
			isConnected = self.Adaptor.ConnectDevice(idx, 3)
			if isConnected == True:
				txPacket = self.Protocol.GetDeviceTypeCommand()
				rxPacket = self.Adaptor.Send(txPacket)
				if (len(rxPacket) > 5):
					magic_one, magic_two, op_code, content_length = struct.unpack("BBHB", rxPacket[0:5])
					if (magic_one == 0xde and magic_two == 0xad):
						deviceType = rxPacket[5:-1]
						print str(deviceType) + " <?> " + str(device_type)
						if str(deviceType) == str(device_type):
							print "Device Type: " + deviceType
							deviceFound = True
							self.IsConnected = True
							return True
					else:
						self.Adaptor.DisconnectDevice()
						print "Not a MakeSense complient device... "
				else:
					self.Adaptor.DisconnectDevice()
					print "Not a MakeSense complient device... "
			idx = idx + 1
			self.Adaptor.DisconnectDevice()
		self.IsConnected = False
		return False
	
	def Disconnect(self):
		print "[DEBUG::Connector] Disconnect"
		self.IsConnected = False
		self.Adaptor.DisconnectDevice()
		print "Connector ... [DISCONNECTED]"

	def IsValidDevice(self):
		return self.IsConnected
	
	def GetUUID (self):
		txPacket = self.Protocol.GetDeviceUUIDCommand()
		rxPacket = self.Adaptor.Send(txPacket)
		return rxPacket[5:-1] # "-1" is for removing "\n" at the end (no unpack used)

	def GetDeviceInfo(self):
		txPacket = self.Protocol.GetDeviceInfoCommand()
		rxPacket = self.Adaptor.Send(txPacket)

		MagicOne, MagicTwo, Opcode, Length, InfoSize, SensorsCount = struct.unpack("BBHBBB", rxPacket[0:7])

		payload = "\"sensors_count\":" + str(SensorsCount) + ",\"sensors\":["
		for i in range(0,SensorsCount):
			pin, id, value, group, direction = struct.unpack("BBBBB", rxPacket[7 + (5 * i):7 + (5 * (i + 1))])
			payload += "{\"id\":" + str(id) + ",\"value\":" + str(value) + ",\"group\":" + str(group) + ",\"direction\":" + str(direction) + "},"

		payload = payload[0:-1] + "]"
		ret = "{\"status\":\"OK\",\"payload\":{" + payload + "}}"
		return json.loads(ret)

	def SetSensorInfo(self, info):
		txPacket = self.Protocol.SetArduinoNanoUSBSensorValueCommand(info.Id, info.Value)
		rxPacket = self.Adaptor.Send(txPacket)

		return "{\"status\":\"OK\"}"

	def GetSensorInfo(self, info):
		txPacket = self.Protocol.GetArduinoNanoUSBSensorValueCommand(info.Id)
		rxPacket = self.Adaptor.Send(txPacket)
		if (len(rxPacket) > 7):
			MagicOne, MagicTwo, Opcode, Length, Id, Value = struct.unpack("BBHBBH", rxPacket[0:8])
			return "{\"status\":\"OK\",\"payload\":{\"id\":" + str(Id) + ",\"value\":" + str(Value) + "}}"
		else:
			return "{\"status\":\"FAILED\"}"

	def GetSensorListInfo(self):
		return ""





	def SetSensor (self, id, value):
		txPacket = self.Protocol.SetArduinoNanoUSBSensorValueCommand(id, value)
		rxPacket = self.Adaptor.Send(txPacket)
		return rxPacket

	def SetDeviceDisconnectCallback(self, callback):
		self.Adaptor.OnSerialConnectionClosedCallback = callback

	def GetSensor (self, id):
		txPacket = self.Protocol.GetArduinoNanoUSBSensorValueCommand(id)
		rxPacket = self.Adaptor.Send(txPacket)
		if (len(rxPacket) > 7):
			MagicOne, MagicTwo, Opcode, Length, DeviceId, Value = struct.unpack("BBHBBH", rxPacket[0:8])
			Error = False
		else:
			DeviceId = Value = 0
			Error = True
		return Error, DeviceId, Value
	
	def SetWindow (self, window_id, msg, value_type, sign, block_type):
		txPacket = self.Protocol.SetWindowMessageCommand(window_id, msg, value_type, sign, block_type)
		rxPacket = self.Adaptor.Send(txPacket)
		return rxPacket[5:-1] # "-1" is for removing "\n" at the end (no unpack used)
