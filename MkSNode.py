#!/usr/bin/python
import os
import sys
import thread
import threading
import time
import json
import signal
import socket, select
import Queue
import argparse

from mksdk import MkSFile
from mksdk import MkSNetMachine
from mksdk import MkSDevice
from mksdk import MkSUtils
from mksdk import MkSAbstractNode

class Node():
	"""Node respomsable for coordinate between web services
	and adaptor (in most cases serial)"""
	   
	def __init__(self, node_type, local_service_node):
		# Objects node depend on
		self.File 							= MkSFile.File()
		self.Connector 						= None
		self.Network						= None
		self.LocalServiceNode 				= local_service_node
		# Node connection to WS information
		self.ApiUrl 						= ""
		self.WsUrl							= ""
		self.UserName 						= ""
		self.Password 						= ""
		self.NodeType 						= node_type
		# Device information
		self.Type 							= 0
		self.UUID 							= ""
		self.OSType 						= ""
		self.OSVersion 						= ""
		self.BrandName 						= ""
		self.Name 							= ""
		self.Description					= ""
		self.DeviceInfo 					= None
		# Misc
		self.State 							= 'IDLE'
		self.IsRunnig 						= True
		self.AccessTick 					= 0
		self.RegisteredNodes  				= []
		self.SystemLoaded					= False
		self.IsNodeMainEnabled  			= False
		self.IsHardwareBased 				= False
		self.IsNodeWSServiceEnabled 		= False # Based on HTTP requests and web sockets
		self.IsNodeLocalServerEnabled 		= False # Based on regular sockets
		# Inner state
		self.States = {
			'IDLE': 						self.StateIdle,
			'CONNECT_DEVICE':				self.StateConnectDevice,
			'INIT_NETWORK':					self.StateInitNetwork,
			'ACCESS': 						self.StateGetAccess,
			'WORK': 						self.StateWork
		}
		# Callbacks
		self.WorkingCallback 				= None
		self.OnWSDataArrived 				= None
		self.OnWSConnected 					= None
		self.OnWSConnectionClosed 			= None
		self.OnNodeSystemLoaded 			= None
		self.OnDeviceConnected 				= None
		# Locks and Events
		self.NetworkAccessTickLock 			= threading.Lock()
		self.ConnectorLock			 		= threading.Lock()
		self.ExitEvent 						= threading.Event()
		self.ExitLocalServerEvent			= threading.Event()
		# Debug
		self.DebugMode						= False
		# Handlers
		self.Handlers						= {
			'get_node_info': 				self.GetNodeInfoHandler,
			'get_node_status': 				self.GetNodeStatusHandler,
			'register_subscriber':			self.RegisterSubscriberHandler,
			'unregister_subscriber':		self.UnregisterSubscriberHandler 
		}

		self.LocalServiceNode.OnExitCallback = self.OnExitHandler

		parser = argparse.ArgumentParser(description='Execution module called Node')
		parser.add_argument('--path', action='store',
					dest='pwd', help='Root folder of a Node')
		args = parser.parse_args()

		if args.pwd is not None:
			os.chdir(args.pwd)

	def OnExitHandler(self):
		self.Exit()

	def DeviceDisconnectedCallback(self, data):
		print "[DEBUG::Node] DeviceDisconnectedCallback"
		if True == self.IsHardwareBased:
			self.Connector.Disconnect()
		self.Network.Disconnect()
		self.Stop()
		self.Run(self.WorkingCallback)

	def LoadSystemConfig(self):
		# Information about the node located here.
		jsonSystemStr = self.File.LoadStateFromFile("system.json")
		
		try:
			dataSystem 				= json.loads(jsonSystemStr)
			# Node connection to WS information
			self.ApiUrl 			= dataSystem["apiurl"]
			self.WsUrl				= dataSystem["wsurl"]
			self.UserName 			= dataSystem["username"]
			self.Password 			= dataSystem["password"]
			# Device information
			self.Type 				= dataSystem["node"]["type"]
			self.OSType 			= dataSystem["node"]["ostype"]
			self.OSVersion 			= dataSystem["node"]["osversion"]
			self.BrandName 			= dataSystem["node"]["brandname"]
			self.Name 				= dataSystem["node"]["name"]
			self.Description 		= dataSystem["node"]["description"]
			self.UserDefined		= dataSystem["user"]
			# Device UUID MUST be read from HW device.
			if "True" == dataSystem["node"]["isHW"]:
				self.IsHardwareBased = True
			else:
				self.UUID = dataSystem["node"]["uuid"]
		except:
			print "Error: [LoadSystemConfig] Wrong system.json format"
			self.Exit()
		
		self.DeviceInfo = MkSDevice.Device(self.UUID, self.Type, self.OSType, self.OSVersion, self.BrandName)
	
	# If this method called, this Node is HW enabled. 
	def SetConnector(self, connector):
		print "[Node] SetDevice"
		self.Connector = connector
		self.IsHardwareBased = True

	def GetConnector(self):
		return self.Connector
		
	def SetNetwork(self):
		print "SetNetwork"
	
	def StateIdle (self):
		print "StateIdle"
	
	def StateConnectDevice (self):
		print "StateConnectDevice"
		if True == self.IsHardwareBased:
			if None == self.Connector:
				print "Error: [Run] Device did not specified"
				self.Exit()
				return
			
			if False == self.Connector.Connect(self.Type):
				print "Error: [Run] Could not connect device"
				self.Exit()
				return
			
			# TODO - Make it work.
			#self.Connector.SetDeviceDisconnectCallback(self.DeviceDisconnectedCallback)
			deviceUUID = self.Connector.GetUUID()
			if len(deviceUUID) > 30:
				self.UUID = str(deviceUUID)
				print "Serial Device UUID:",self.UUID
				if None != self.OnDeviceConnected:
					self.OnDeviceConnected()
				if True == self.IsNodeWSServiceEnabled: 
					self.Network.SetDeviceUUID(self.UUID)
			else:
				print "[Node] (ERROR) UUID is NOT correct."
				self.Exit()
				return

		self.State = "INIT_NETWORK"
	
	def StateInitNetwork(self):
		if True == self.IsNodeWSServiceEnabled:
			self.Network = MkSNetMachine.Network(self.ApiUrl, self.WsUrl)
			self.Network.SetDeviceType(self.Type)
			self.Network.SetDeviceUUID(self.UUID)
			self.Network.OnConnectionCallback  		= self.WebSocketConnectedCallback
			self.Network.OnDataArrivedCallback 		= self.WebSocketDataArrivedCallback
			self.Network.OnConnectionClosedCallback = self.WebSocketConnectionClosedCallback
			self.Network.OnErrorCallback 			= self.WebSocketErrorCallback

			self.State = "ACCESS"
		else:
			self.State = "WORK"

	def StateGetAccess (self):
		if True == self.IsNodeWSServiceEnabled:
			print "[DEBUG::Node] StateGetAccess"
			# Let the state machine know that this state was entered.
			self.NetworkAccessTickLock.acquire()
			try:
				self.AccessTick = 1
			finally:
				self.NetworkAccessTickLock.release()
			payloadStr = "[]"
			if self.Network.Connect(self.UserName, self.Password, payloadStr) == True:
				print "Register Device ..."
				data, error = self.Network.RegisterDevice(self.DeviceInfo)
				if error == False:
					return
		else:
			self.State = "WORK"
	
	def StateWork (self):
		if False == self.SystemLoaded:
			self.SystemLoaded = True # Update node that system done loading.
			self.OnNodeSystemLoaded()

		# TODO - If not connected switch state and try to connect WS.
		# If state is accessing network and it ia only the first time.
		#if self.State == "ACCESS" and self.AccessTick > 0:
		#	self.NetworkAccessTickLock.acquire()
		#	try:
		#		self.AccessTick = self.AccessTick + 1
		#	finally:
		#		self.NetworkAccessTickLock.release()
		#	if self.AccessTick < 10:
		#		print "Waiting for web service ... " + str(self.AccessTick)
		#		continue
	
	def WebSocketConnectedCallback (self):
		self.State = "WORK"
		self.OnWSConnected()

	def GetNodeInfoHandler(self, message_type, source, data):
		if True == self.SystemLoaded:
			# print self.UserDefined
			res_payload = "\"state\":\"response\",\"status\":\"ok\",\"ts\":" + str(time.time()) + ",\"name\":\"" + self.Name + "\",\"description\":\"" + self.Description + "\", \"user\":" + json.dumps(self.UserDefined)
			print res_payload
			self.SendMessage(message_type, source, "get_node_info", res_payload)

	def GetNodeStatusHandler(self, message_type, source, data):
		if True == self.SystemLoaded:
			res_payload = "\"state\":\"response\",\"status\":\"ok\",\"ts\":" + str(time.time()) + ",\"registered\":\"" + str(self.IsNodeRegistered(source)) + "\""
			self.SendMessage(message_type, source, "get_node_status", res_payload)
	
	def RegisterSubscriberHandler(self, message_type, source, data):
		print "RegisterSubscriberHandler"
	
	def UnregisterSubscriberHandler(self, message_type, source, data):
		print "UnregisterSubscriberHandler"
	
	def WebSocketDataArrivedCallback (self, json):
		self.State = "WORK"
		messageType = self.Network.GetMessageTypeFromJson(json)
		source = self.Network.GetSourceFromJson(json)
		command = self.Network.GetCommandFromJson(json)
		print "[DEBUG::Node Network(In)] " + str(json)
		if messageType == "CUSTOM":
			return;
		elif messageType == "DIRECT" or messageType == "PRIVATE" or messageType == "BROADCAST" or messageType == "WEBFACE":
			data = self.Network.GetDataFromJson(json)
			# If commands located in the list below, do not forward this message and handle it in this context.
			if command in ["get_node_info", "get_node_status"]:
				self.Handlers[command](messageType, source, data)
			else:
				self.OnWSDataArrived(messageType, source, data)
		else:
			print "Error: Not support " + request + " request type."

	def IsNodeRegistered(self, subscriber_uuid):
		return subscriber_uuid in self.RegisteredNodes
	
	def SendMessage (self, message_type, destination, command, payload):
		message = self.Network.BuildMessage(message_type, destination, command, payload)
		print "[DEBUG::Node Network(Out)] " + message
		ret = self.Network.SendMessage(message)
		if False == ret:
			self.State = "ACCESS"
		return ret

	def WebSocketConnectionClosedCallback (self):
		self.OnWSConnectionClosed()
		self.NetworkAccessTickLock.acquire()
		try:
			self.AccessTick = 0
		finally:
			self.NetworkAccessTickLock.release()
		self.State = "ACCESS"

	def WebSocketErrorCallback (self):
		print "WebSocketErrorCallback"
		# TODO - Send callback "OnWSError"
		self.NetworkAccessTickLock.acquire()
		try:
			self.AccessTick = 0
		finally:
			self.NetworkAccessTickLock.release()
		self.State = "ACCESS"

	def GetFileContent (self, file):
		return self.File.LoadStateFromFile(file)

	def SetFileContent (self, file, content):
		self.File.SaveStateToFile(file, content)

	def AppendToFile (self, file, data):
		self.File.AppendToFile(file, data + "\n")

	def SaveBasicSensorValueToFile (self, uuid, value):
		self.AppendToFile(uuid + ".json", "{\"ts\":" + str(time.time()) + ",\"v\":" + str(value) + "},")
	
	def LoadBasicSensorValuesFromFileByRowNumber (self, uuid, rows_number):
		buf_size = 8192
		data_set = "["
		data_set_index = 0
		with open(uuid + ".json") as fh:
			segment = None
			offset = 0
			fh.seek(0, os.SEEK_END)
			file_size = remaining_size = fh.tell()
			while remaining_size > 0:
				offset = min(file_size, offset + buf_size)
				fh.seek(file_size - offset)
				buffer = fh.read(min(remaining_size, buf_size))
				remaining_size -= buf_size
				lines = buffer.split('\n')
				if segment is not None:
					if buffer[-1] is not '\n':
						lines[-1] += segment
					else:
						print "1" + segment
				segment = lines[0]
				for index in range(len(lines) - 1, 0, -1):
					if len(lines[index]):
						data_set_index += 1
						data_set += lines[index]
						if data_set_index == rows_number:
							data_set = data_set[:-1] + "]"
							return data_set
			if segment is not None:
				data_set += segment
		data_set = data_set[:-1] + "]"
		return data_set

	def GetDeviceConfig (self):
		jsonConfigStr = self.File.LoadStateFromFile("config.json")
		try:
			dataConfig = json.loads(jsonConfigStr)
			return dataConfig
		except:
			print "Error: [GetDeviceConfig] Wrong config.json format"
			return ""
	
	def GetSensorHWValue (self, id):
		"""Get HW device sensor value"""
		self.ConnectorLock.acquire()
		error, device_id, value = self.Connector.GetSensor(id)
		if error == True:
			error, device_id, value = self.Connector.GetSensor(id)
			if error == True:
				self.ConnectorLock.release()
				return True, 0, 0
		self.ConnectorLock.release()
		return False, device_id, value

	def SetSensorHWValue (self, id, value):
		"""Set HW device with sensor value"""
		self.ConnectorLock.acquire()
		data = self.Connector.SetSensor(id, value)
		self.ConnectorLock.release()
		return data

	def NodeWorker (self, callback):
		self.WorkingCallback = callback
		self.State = "CONNECT_DEVICE"
		
		# We need to know if this worker is running for waiting mechanizm
		self.IsNodeMainEnabled = True
		while self.IsRunnig:
			time.sleep(0.5)
			self.Method = self.States[self.State]
			self.Method()
		
		print "[DEBUG::Node] Exit NodeWork"
		if True == self.IsHardwareBased:
			self.Connector.Disconnect()
		self.ExitEvent.set()

	def SetWebServiceStatus(self, is_enabled):
		self.IsNodeWSServiceEnabled = is_enabled

	def SetLocalServerStatus(self, is_enabled):
		self.IsNodeLocalServerEnabled = is_enabled

	def SetMasterNodeStatus(self, is_enabled):
		self.IsMasterNode 		= is_enabled

	def SetPureSlaveStatus(self, is_enabled):
		self.isPureSlave = is_enabled

	def Run (self, callback):
		self.WorkingCallback = callback
		self.ExitEvent.clear()
		self.ExitLocalServerEvent.clear()

		# Read sytem configuration
		self.LoadSystemConfig()

		# Start Node worker thread
		thread.start_new_thread(self.NodeWorker, (callback, ))

		if True == self.IsNodeLocalServerEnabled:
			self.LocalServiceNode.SetNodeUUID(self.UUID)
			self.LocalServiceNode.SetNodeType(self.Type)
			thread.start_new_thread(self.LocalServiceNode.NodeLocalNetworkConectionListener, ())

		# Waiting here till SIGNAL from OS will come.
		while self.IsRunnig:
			self.WorkingCallback()
			time.sleep(0.5)
		
		if True == self.IsNodeMainEnabled:
			self.ExitEvent.wait()

		if True == self.LocalServiceNode.LocalSocketServerRun:
			self.ExitLocalServerEvent.wait()
	
	def Stop (self):
		print "[DEBUG::Node] Stop"
		self.IsRunnig 								= False
		self.LocalServiceNode.LocalSocketServerRun 	= False
	
	def Pause (self):
		print "Pause"
	
	def Exit (self):
		self.Stop()
