#!/usr/bin/python
import os
import sys
if sys.version_info[0] < 3:
	import thread
else:
	import _thread
import threading
import time
import json
import signal
import socket, select
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
			'ACCESS_WAIT':					self.StateAccessWait,
			'LOCAL_SERVICE':				self.StateLocalService,
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
		self.ExitEvent 						= threading.Event()
		self.ExitLocalServerEvent			= threading.Event()
		# Debug
		self.DebugMode						= False
		# Handlers
		self.Handlers						= {
			'get_node_info': 				self.GetNodeInfoHandler,
			'get_node_status': 				self.GetNodeStatusHandler,
			'register_subscriber':			self.RegisterSubscriberHandler,
			'unregister_subscriber':		self.UnregisterSubscriberHandler,
			'get_file':						self.GetFileHandler
		}

		self.LocalServiceNode.OnExitCallback 					= self.OnExitHandler
		self.LocalServiceNode.OnNewNodeCallback 				= self.OnNewNodeHandler
		self.LocalServiceNode.OnSlaveNodeDisconnectedCallback 	= self.OnSlaveNodeDisconnectedHandler
		self.LocalServiceNode.OnSlaveResponseCallback 			= self.OnSlaveResponseHandler
		self.LocalServiceNode.OnGetNodeInfoRequestCallback 		= self.OnGetNodeInfoRequestHandler

		parser = argparse.ArgumentParser(description='Execution module called Node')
		parser.add_argument('--path', action='store',
					dest='pwd', help='Root folder of a Node')
		args = parser.parse_args()

		if args.pwd is not None:
			os.chdir(args.pwd)

	# TODO - Not needed, remove
	def GetFile(self, filename, ui_type):
		objFile = MkSFile.File()
		return objFile.LoadStateFromFile("static/js/node/" + fileName)

	# TODO - Not needed, remove
	def GetFileHandler(self, message_type, source, data):
		if self.Network.GetNetworkState() is "CONN":
			uiType = data["payload"]["ui_type"]
			fileName = data["payload"]["file_name"]

			content = self.GetFile(fileName, uiType)
			payload = { 'file_content': content }
			message = self.Network.BuildMessage("DIRECT", source, self.UUID, "get_file", payload, {})
			self.Network.SendWebSocket(message)

	def OnNewNodeHandler(self, node):
		if self.Network.GetNetworkState() is "CONN":
			payload = { 'node': node }
			# Send node connected event to gateway
			message = self.Network.BuildMessage("MASTER", "GATEWAY", self.UUID, "node_connected", payload, {})
			self.Network.SendWebSocket(message)

	def OnSlaveNodeDisconnectedHandler(self, node):
		if self.Network.GetNetworkState() is "CONN":
			payload = { 'node': node }
			# Send node disconnected event to gateway
			message = self.Network.BuildMessage("MASTER", "GATEWAY", self.UUID, "node_disconnected", payload, {})
			self.Network.SendWebSocket(message)

	# Sending response to "get_node_info" request (mostly for proxy request)
	def OnSlaveResponseHandler(self, dest, src, command, payload, piggy):
		print ("[DEBUG MASTER] OnSlaveResponseHandler")
		if self.Network.GetNetworkState() is "CONN":
			message = self.Network.BuildMessage("DIRECT", dest, src, command, payload, piggy)
			self.Network.SendWebSocket(message)

	def OnGetNodeInfoRequestHandler(self, sock, packet):
		# Update response packet and encapsulate
		msg = self.LocalServiceNode.Commands.ProxyResponse(packet, self.NodeInfo)
		# Send to requestor
		sock.send(msg)

	def OnExitHandler(self):
		self.Exit()

	def DeviceDisconnectedCallback(self, data):
		print ("[DEBUG::Node] DeviceDisconnectedCallback")
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
			self.NodeInfo 			= dataSystem["node"]
			# Node connection to WS information
			self.Key 				= dataSystem["key"]
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
			print ("Error: [LoadSystemConfig] Wrong system.json format")
			self.Exit()
		
		self.DeviceInfo = MkSDevice.Device(self.UUID, self.Type, self.OSType, self.OSVersion, self.BrandName)
	
	# If this method called, this Node is HW enabled. 
	def SetConnector(self, connector):
		print ("[Node] SetDevice")
		self.Connector = connector
		self.IsHardwareBased = True

	def GetConnector(self):
		return self.Connector
		
	def SetNetwork(self):
		print ("SetNetwork")
	
	def StateIdle (self):
		print ("StateIdle")
	
	def StateConnectDevice (self):
		print ("StateConnectDevice")
		if True == self.IsHardwareBased:
			if None == self.Connector:
				print ("Error: [Run] Device did not specified")
				self.Exit()
				return
			
			if False == self.Connector.Connect(self.Type):
				print ("Error: [Run] Could not connect device")
				self.Exit()
				return
			
			# TODO - Make it work.
			#self.Connector.SetDeviceDisconnectCallback(self.DeviceDisconnectedCallback)
			deviceUUID = self.Connector.GetUUID()
			if len(deviceUUID) > 30:
				self.UUID = str(deviceUUID)
				print ("Serial Device UUID:",self.UUID)
				if None != self.OnDeviceConnected:
					self.OnDeviceConnected()
				if True == self.IsNodeWSServiceEnabled: 
					self.Network.SetDeviceUUID(self.UUID)
			else:
				print ("[Node] (ERROR) UUID is NOT correct.")
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
			self.AccessTick = 0

			self.State = "ACCESS"
		else:
			self.State = "WORK"

	def StateGetAccess (self):
		if True == self.IsNodeWSServiceEnabled:
			print ("[DEBUG::Node] StateGetAccess")
			self.Network.AccessGateway(self.Key, "[]")
			self.State = "ACCESS_WAIT"
		else:
			self.State = "WORK"
	
	def StateAccessWait (self):
		print ("ACCESS_WAIT")
		if self.AccessTick > 10:
			self.State 		= "ACCESS"
			self.AccessTick = 0
		else:
			self.AccessTick += 1

	def StateLocalService (self):
		pass

	def StateWork (self):
		if False == self.SystemLoaded:
			self.SystemLoaded = True # Update node that system done loading.
			self.OnNodeSystemLoaded()
	
	def WebSocketConnectedCallback (self):
		self.State = "WORK"
		self.LocalServiceNode.GatewayConnectedEvent()
		self.OnWSConnected()

	def GetNodeInfoHandler(self, json):
		print ("GetNodeInfoHandler")

		if self.Network.GetNetworkState() is "CONN":
			payload = self.NodeInfo
			message = self.Network.BuildResponse(json, payload)
			self.Network.SendWebSocket(message)

	def GetNodeStatusHandler(self, message_type, source, data):
		if True == self.SystemLoaded:
			res_payload = "\"state\":\"response\",\"status\":\"ok\",\"ts\":" + str(time.time()) + ",\"registered\":\"" + str(self.IsNodeRegistered(source)) + "\""
			self.SendMessage(message_type, source, "get_node_status", res_payload)
	
	def RegisterSubscriberHandler(self, message_type, source, data):
		print ("RegisterSubscriberHandler")
	
	def UnregisterSubscriberHandler(self, message_type, source, data):
		print ("UnregisterSubscriberHandler")
	
	def WebSocketDataArrivedCallback (self, json):
		self.State 	= "WORK"
		messageType = self.Network.GetMessageTypeFromJson(json)
		destination = self.Network.GetDestinationFromJson(json)
		command 	= self.Network.GetCommandFromJson(json)

		print ("\n[DEBUG::Node Network(In)] " + str(command) + "\n")

		# Is this packet for me?
		if destination in self.UUID:
			if messageType == "CUSTOM":
				return
			elif messageType == "DIRECT" or messageType == "PRIVATE" or messageType == "BROADCAST" or messageType == "WEBFACE":
				# If commands located in the list below, do not forward this message and handle it in this context.
				if command in ["get_node_info", "get_node_status"]:
					self.Handlers[command](json)
				else:
					print ("DEBUG #1")
					self.LocalServiceNode.HandleInternalReqest(json)
					print ("DEBUG #2")
					if self.OnWSDataArrived is not None:
						print ("DEBUG #3")
						self.OnWSDataArrived(json)
			else:
				print ("Error: Not support " + request + " request type.")
		else:
			# Find who has this destination adderes.
			self.LocalServiceNode.HandleExternalRequest(json)

	def IsNodeRegistered(self, subscriber_uuid):
		return subscriber_uuid in self.RegisteredNodes
	
	def SendMessage (self, message_type, destination, command, payload):
		message = self.Network.BuildMessage(message_type, destination, command, payload, {})
		print ("[DEBUG::Node Network(Out)] " + message)
		ret = self.Network.SendMessage(message)
		if False == ret:
			self.State = "ACCESS"
		return ret

	def WebSocketConnectionClosedCallback (self):
		self.LocalServiceNode.GatewayDisConnectedEvent()
		self.OnWSConnectionClosed()
		self.NetworkAccessTickLock.acquire()
		try:
			self.AccessTick = 0
		finally:
			self.NetworkAccessTickLock.release()
		self.State = "ACCESS_WAIT"

	def WebSocketErrorCallback (self):
		print ("WebSocketErrorCallback")
		# TODO - Send callback "OnWSError"
		self.NetworkAccessTickLock.acquire()
		try:
			self.AccessTick = 0
		finally:
			self.NetworkAccessTickLock.release()
		self.State = "ACCESS_WAIT"

	def GetFileContent (self, file):
		return self.File.LoadStateFromFile(file)

	def SetFileContent (self, file, content):
		self.File.SaveStateToFile(file, content)

	def AppendToFile (self, file, data):
		self.File.AppendToFile(file, data + "\n")

	def SaveBasicSensorValueToFile (self, uuid, value):
		self.AppendToFile(uuid + ".json", "{\"ts\":" + str(time.time()) + ",\"v\":" + str(value) + "},")

	def GetDeviceConfig (self):
		jsonConfigStr = self.File.LoadStateFromFile("config.json")
		try:
			dataConfig = json.loads(jsonConfigStr)
			return dataConfig
		except:
			print ("Error: [GetDeviceConfig] Wrong config.json format")
			return ""

	def SetWebServiceStatus(self, is_enabled):
		self.IsNodeWSServiceEnabled = is_enabled

	def SetLocalServerStatus(self, is_enabled):
		self.IsNodeLocalServerEnabled = is_enabled

	def SetMasterNodeStatus(self, is_enabled):
		self.IsMasterNode = is_enabled

	def SetPureSlaveStatus(self, is_enabled):
		self.isPureSlave = is_enabled

	def Run (self, callback):
		self.WorkingCallback = callback
		self.ExitEvent.clear()
		self.ExitLocalServerEvent.clear()
		self.State = "CONNECT_DEVICE"

		# We need to know if this worker is running for waiting mechanizm
		self.IsNodeMainEnabled = True

		# Read sytem configuration
		self.LoadSystemConfig()

		if True == self.IsNodeLocalServerEnabled:
			self.LocalServiceNode.SetNodeUUID(self.UUID)
			self.LocalServiceNode.SetNodeType(self.Type)
			thread.start_new_thread(self.LocalServiceNode.NodeLocalNetworkConectionListener, ())

		# Waiting here till SIGNAL from OS will come.
		while self.IsRunnig:
			self.Method = self.States[self.State]
			self.Method()

			self.WorkingCallback()
			time.sleep(0.5)

		print ("[DEBUG::Node] Exit NodeWork")
		if True == self.IsHardwareBased:
			self.Connector.Disconnect()
		self.ExitEvent.set()
		
		if True == self.IsNodeMainEnabled:
			self.ExitEvent.wait()

		if True == self.LocalServiceNode.LocalSocketServerRun:
			self.ExitLocalServerEvent.wait()
	
	def Stop (self):
		print ("[DEBUG::Node] Stop")
		self.IsRunnig 								= False
		self.LocalServiceNode.LocalSocketServerRun 	= False
	
	def Pause (self):
		print ("Pause")
	
	def Exit (self):
		self.Stop()
