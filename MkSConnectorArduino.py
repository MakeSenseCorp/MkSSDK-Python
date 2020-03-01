#!/usr/bin/python
import os
import time
import struct
import json

import MkSUSBAdaptor
import MkSProtocol

from mksdk import MkSAbstractConnector

class Connector (MkSAbstractConnector.AbstractConnector):
	def __init__ (self):
		MkSAbstractConnector.AbstractConnector.__init__(self)

	def Connect (self, device_type):
		idx = 1
		deviceFound = False
		for item in self.Adaptor.Interfaces:
			isConnected = self.Adaptor.ConnectDevice(idx, 3)
			if isConnected == True:
				time.sleep(2)
				txPacket = self.Protocol.GetDeviceTypeCommand()
				rxPacket = self.Adaptor.Send(txPacket)
				if (len(rxPacket) > 4):
					magic_one, magic_two, direction, op_code, content_length = struct.unpack("BBBBB", rxPacket[0:5])
					if (magic_one == 0xde and magic_two == 0xad):
						deviceType = rxPacket[5:-2]
						print (str(deviceType) + " <?> " + str(device_type))
						if str(deviceType) == str(device_type):
							print ("Device Type: " + deviceType)
							deviceFound = True
							self.IsConnected = True
							return True
					else:
						self.Adaptor.DisconnectDevice()
						print ("Not a MakeSense complient device... ")
				else:
					self.Adaptor.DisconnectDevice()
					print ("Not a MakeSense complient device... ")
			idx = idx + 1
			self.Adaptor.DisconnectDevice()
		self.IsConnected = False
		return False
	
	def Disconnect(self):
		self.IsConnected = False
		self.Adaptor.DisconnectDevice()
		print ("Connector ... [DISCONNECTED]")

	def IsValidDevice(self):
		return self.IsConnected
	
	def GetUUID (self):
		txPacket = self.Protocol.GetDeviceUUIDCommand()
		rxPacket = self.Adaptor.Send(txPacket)
		return rxPacket[6:-1] # "-1" is for removing "\n" at the end (no unpack used)

	def Send(self, packet):
		rxPacket = self.Adaptor.Send(packet)
		return rxPacket
