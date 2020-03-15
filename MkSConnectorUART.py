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
		self.ClassName 					= "Connector"
		self.NodeType 					= 0
		self.Adapters					= []
		self.Protocol 					= MkSProtocol.Protocol()
		self.UARTInterfaces 			= []
		# Events
		self.AdaptorDisconnectedEvent 	= None

	def FindUARTDevices(self):
		dev = os.listdir("/dev/")
		return ["/dev/" + item for item in dev if "ttyUSB" in item]
	
	def __Connect(self, path):
		adaptor = MkSUSBAdaptor.Adaptor(path, 9600)
		adaptor.OnSerialAsyncDataCallback 			= self.OnAdapterDataArrived
		adaptor.OnSerialConnectionClosedCallback 	= self.OnAdapterDisconnected
		status = adaptor.Connect(3)
		if status is True:
			tx_packet = self.Protocol.GetDeviceTypeCommand()
			rx_packet = adaptor.Send(tx_packet)
			if (len(rx_packet) > 3):
				deviceType = ''.join([str(unichr(elem)) for elem in rx_packet[3:]])
				if str(deviceType) == str(self.NodeType):
					self.Adapters.append({
						'dev': adaptor,
						'path': path
					})
					return True
			adaptor.Disconnect()
		return False
	
	def Connect (self, device_type):
		self.NodeType = device_type
		self.UARTInterfaces = self.FindUARTDevices()
		for dev_path in self.UARTInterfaces:
			self.__Connect(dev_path)
		return self.Adapters
	
	def FindAdaptor(self, path):
		for adaptor in self.Adapters:
			if adaptor["path"] == path:
				return adaptor
		return None
	
	def UpdateUARTInterfaces(self):
		changes = []
		interfaces = self.FindUARTDevices()
		# Find disconnected adaptors
		for adaptor in self.Adapters:
			if adaptor["path"] not in interfaces:
				# USB must be disconnected
				changes.append({
					"change": "remove",
					"path": adaptor["path"]
				})
		for interface in interfaces:
			adaptor = self.FindAdaptor(interface)
			if adaptor is None:
				if self.__Connect(interface) is True:
					changes.append({
						"change": "append",
						"path": interface
					})

		if len(changes) > 0:
			print ("({classname})# Changes ({0})".format(changes, classname=self.ClassName))
		
		return changes
	
	def OnAdapterDisconnected(self, path):
		adaptor = self.FindAdaptor(path)
		if self.AdaptorDisconnectedEvent is not None and adaptor is not None:
			if "rf_type" in adaptor:
				self.AdaptorDisconnectedEvent(path, adaptor["rf_type"])
		if adaptor is not None:
			self.Adapters.remove(adaptor)

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
