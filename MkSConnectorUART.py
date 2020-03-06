#!/usr/bin/python
import os
import time
import struct
import json

from mksdk import MkSUSBAdaptor
from mksdk import MkSProtocol

from mksdk import MkSAbstractConnector

class Connector (MkSAbstractConnector.AbstractConnector):
	def __init__ (self):
		MkSAbstractConnector.AbstractConnector.__init__(self)
		self.Adapters	= []
		self.Protocol 	= MkSProtocol.Protocol()

	def FindUARTDevices(self):
		dev = os.listdir("/dev/")
		return ["/dev/" + item for item in dev if "ttyUSB" in item]
	
	def Connect (self, device_type):
		for dev_path in self.FindUARTDevices():
			adaptor = MkSUSBAdaptor.Adaptor(dev_path, 9600)
			adaptor.OnSerialAsyncDataCallback 			= self.OnAdapterDataArrived
			adaptor.OnSerialConnectionClosedCallback 	= self.OnAdapterDisconnected
			status = adaptor.Connect(3)
			if status is True:
				tx_packet = self.Protocol.GetDeviceTypeCommand()
				rx_packet = adaptor.Send(tx_packet)
				if (len(rx_packet) > 4):
					magic_one, magic_two, direction, op_code, content_length = struct.unpack("BBBBB", rx_packet[0:5])
					# print(magic_one, magic_two, direction, op_code, content_length)
					if (magic_one == 0xde and magic_two == 0xad):
						deviceType = rx_packet[5:-2]
						if str(deviceType) == str(device_type):
							self.Adapters.append({
								'dev': adaptor,
								'path': dev_path
							})
		return self.Adapters
	
	def OnAdapterDisconnected(self, path):
		pass

	def OnAdapterDataArrived(self, path, data):
		pass
	
	def Disconnect(self):
		self.IsConnected = False
		for adaptor in self.Adapters:
			adaptor["dev"].Disconnect()
		print ("Connector ... [DISCONNECTED]")

	def IsValidDevice(self):
		return self.IsConnected
	
	def GetUUID (self):
		txPacket = self.Protocol.GetDeviceUUIDCommand()
		rxPacket = self.Adaptor.Send(txPacket)
		return rxPacket[6:-1] # "-1" is for removing "\n" at the end (no unpack used)

	def Send(self, packet):
		pass
		#rxPacket = self.Adaptor.Send(packet)
		#return rxPacket
