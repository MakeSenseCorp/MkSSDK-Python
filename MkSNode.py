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

import MkSGlobals
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
		self.GatewayIP 						= ""
		self.ApiPort 						= "8080"
		self.WsPort 						= "1981"
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
		self.BoardType 						= ""
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
		self.States 						= {
			'IDLE': 						self.StateIdle,
			'CONNECT_HARDWARE':				self.StateConnectHardware,
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
		self.RequestHandlers				= {
			'get_node_info': 				self.GetNodeInfoHandler,
			'get_node_status': 				self.GetNodeStatusHandler,
			'register_subscriber':			self.RegisterSubscriberHandler,
			'unregister_subscriber':		self.UnregisterSubscriberHandler
		}
		self.ResponseHandlers				= {
		}

		self.LocalServiceNode.OnExitCallback 					= self.OnExitHandler
		self.LocalServiceNode.ServiceNewNodeCallback			= self.OnNewNodeHandler
		self.LocalServiceNode.OnSlaveNodeDisconnectedCallback 	= self.OnSlaveNodeDisconnectedHandler
		self.LocalServiceNode.OnSlaveResponseCallback 			= self.OnSlaveResponseHandler
		self.LocalServiceNode.OnGetNodeInfoRequestCallback 		= self.OnGetNodeInfoRequestHandler
		# Refactoring
		self.LocalServiceNode.SendGatewayMessageCallback 		= self.SendGateway

		parser = argparse.ArgumentParser(description='Execution module called Node')
		parser.add_argument('--path', action='store',
					dest='pwd', help='Root folder of a Node')
		args = parser.parse_args()

		if args.pwd is not None:
			os.chdir(args.pwd)

	def OnNewNodeHandler(self, node):
		if self.Network.GetNetworkState() is "CONN":
			payload = { 'node': node }
			# Send node connected event to gateway
			message = self.Network.BuildMessage("request", "MASTER", "GATEWAY", self.UUID, "node_connected", payload, {})
			self.Network.SendWebSocket(message)

	def OnSlaveNodeDisconnectedHandler(self, node):
		if self.Network.GetNetworkState() is "CONN":
			payload = { 'node': node }
			# Send node disconnected event to gateway
			message = self.Network.BuildMessage("request", "MASTER", "GATEWAY", self.UUID, "node_disconnected", payload, {})
			self.Network.SendWebSocket(message)

	# OBSOLETE
	# Sending response to "get_node_info" request (mostly for proxy request)
	def OnSlaveResponseHandler(self, direction, dest, src, command, payload, piggy):
		print ("[DEBUG MASTER] OnSlaveResponseHandler")
		if self.Network.GetNetworkState() is "CONN":
			message = self.Network.BuildMessage(direction, "DIRECT", dest, src, command, payload, piggy)
			self.Network.SendWebSocket(message)
			
	def SendGateway(self, packet):
		if self.Network.GetNetworkState() is "CONN":
			print("(MkSNode)# Sending message to Gateway")
			self.Network.SendWebSocket(packet)
	
	# OBSOLETE
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
		if MkSGlobals.OS_TYPE in ["linux", "linux2"]:
			MKS_PATH = os.environ['HOME'] + "/mks/"
		else:
			MKS_PATH = "C:\\mks\\"

		# Information about the node located here.
		strSystemJson 		= self.File.Load("system.json")
		strMachineJson 		= self.File.Load(MKS_PATH + "config.json")

		if (strSystemJson is None or len(strSystemJson) == 0):
			print("(MkSNode)# ERROR - Cannot find system.json file.")
			self.Exit()
			return False

		if (strMachineJson is None or len(strMachineJson) == 0):
			print("(MkSNode)# ERROR - Cannot find config.json file.")
			self.Exit()
			return False
		
		try:
			dataSystem 				= json.loads(strSystemJson)
			dataConfig 				= json.loads(strMachineJson)
			self.NodeInfo 			= dataSystem["node"]
			# Node connection to WS information
			self.Key 				= dataConfig["network"]["key"]
			self.GatewayIP			= dataConfig["network"]["gateway"]
			self.ApiPort 			= dataConfig["network"]["apiport"]
			self.WsPort 			= dataConfig["network"]["wsport"]
			self.ApiUrl 			= "http://{gateway}:{api_port}".format(gateway=self.GatewayIP, api_port=self.ApiPort)
			self.WsUrl				= "ws://{gateway}:{ws_port}".format(gateway=self.GatewayIP, ws_port=self.WsPort)
			# Device information
			self.Type 				= dataSystem["node"]["type"]
			self.OSType 			= dataSystem["node"]["ostype"]
			self.OSVersion 			= dataSystem["node"]["osversion"]
			self.BrandName 			= dataSystem["node"]["brandname"]
			self.Name 				= dataSystem["node"]["name"]
			self.Description 		= dataSystem["node"]["description"]
			if (self.Type == 1):
				self.BoardType 		= dataSystem["node"]["boardType"]
			self.UserDefined		= dataSystem["user"]
			# Device UUID MUST be read from HW device.
			if "True" == dataSystem["node"]["isHW"]:
				self.IsHardwareBased = True
			else:
				self.UUID = dataSystem["node"]["uuid"]
			
			self.LocalServiceNode.SetNodeUUID(self.UUID)
			self.LocalServiceNode.SetNodeType(self.Type)
			self.LocalServiceNode.SetNodeName(self.Name)
			self.LocalServiceNode.SetGatewayIPAddress(self.GatewayIP)
		except:
			print ("(MkSNode)# ERROR - Wrong configuration format")
			self.Exit()
			return False
		
		print("# TODO - Do we need this DeviceInfo?")
		self.DeviceInfo = MkSDevice.Device(self.UUID, self.Type, self.OSType, self.OSVersion, self.BrandName)
		return True
	
	# If this method called, this Node is HW enabled. 
	def SetConnector(self, connector):
		print ("[Node] SetDevice")
		self.Connector = connector
		self.IsHardwareBased = True

	def GetConnector(self):
		return self.Connector
		
	def SetNetwork(self):
		print ("SetNetwork")
	
	def SetState(self, state):
		self.State = state

	def StateIdle (self):
		pass
	
	def StateConnectHardware (self):
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

		self.SetState("INIT_NETWORK")
	
	def StateInitNetwork(self):
		if self.IsNodeWSServiceEnabled is True:
			self.Network = MkSNetMachine.Network(self.ApiUrl, self.WsUrl)
			self.Network.SetDeviceType(self.Type)
			self.Network.SetDeviceUUID(self.UUID)
			self.Network.OnConnectionCallback  		= self.WebSocketConnectedCallback
			self.Network.OnDataArrivedCallback 		= self.WebSocketDataArrivedCallback
			self.Network.OnConnectionClosedCallback = self.WebSocketConnectionClosedCallback
			self.Network.OnErrorCallback 			= self.WebSocketErrorCallback
			self.AccessTick = 0

			self.SetState("ACCESS")
		else:
			self.SetState("WORK")

	def StateGetAccess (self):
		if True == self.IsNodeWSServiceEnabled:
			self.Network.AccessGateway(self.Key, json.dumps({
				'node_name': str(self.Name),
				'node_type': self.Type
			}))

			self.SetState("ACCESS_WAIT")
		else:
			self.SetState("WORK")
	
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
		self.SetState("WORK")
		self.LocalServiceNode.GatewayConnectedEvent()
		self.OnWSConnected()

	def GetNodeInfoHandler(self, json):
		if self.Network.GetNetworkState() is "CONN":
			payload = self.NodeInfo
			message = self.Network.BasicProtocol.BuildResponse(json, payload)
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
		self.SetState("WORK")
		messageType = self.Network.BasicProtocol.GetMessageTypeFromJson(json)
		destination = self.Network.BasicProtocol.GetDestinationFromJson(json)
		command 	= self.Network.BasicProtocol.GetCommandFromJson(json)

		print ("(MkSNode)# [REQUEST] Gateway -> Node {" + str(command) + ", " + destination + "}")

		# Is this packet for me?
		if destination in self.UUID:
			if messageType == "CUSTOM":
				return
			elif messageType == "DIRECT" or messageType == "PRIVATE" or messageType == "BROADCAST" or messageType == "WEBFACE":
				# If commands located in the list below, do not forward this message and handle it in this context.
				if command in ["get_node_info", "get_node_status"]:
					# Only node with Gateway connection will answer from here.
					self.RequestHandlers[command](json)
				else:
					print ("(MkSNode)# [Websocket INBOUND] Pass to local service ...")
					self.LocalServiceNode.HandleInternalReqest(json)
					if self.OnWSDataArrived is not None:
						self.OnWSDataArrived(json)
			else:
				print ("(MkSNode)# [Websocket INBOUND] ERROR - Not support " + request + " request type.")
		else:
			print ("WebSocketDataArrivedCallback", "HandleExternalRequest", destination)
			# Find who has this destination adderes.
			self.LocalServiceNode.HandleExternalRequest(json)

	def IsNodeRegistered(self, subscriber_uuid):
		return subscriber_uuid in self.RegisteredNodes
	
	def SendMessage (self, message_type, destination, command, payload):
		message = self.Network.BuildMessage("request", message_type, destination, command, payload, {})
		print ("[DEBUG::Node Network(Out)] " + message)
		ret = self.Network.SendWebSocket(message)
		if False == ret:
			self.SetState("ACCESS")
		return ret

	def WebSocketConnectionClosedCallback (self):
		self.LocalServiceNode.GatewayDisConnectedEvent()
		self.OnWSConnectionClosed()
		self.NetworkAccessTickLock.acquire()
		try:
			self.AccessTick = 0
		finally:
			self.NetworkAccessTickLock.release()
		self.SetState("ACCESS_WAIT")

	def WebSocketErrorCallback (self):
		print ("WebSocketErrorCallback")
		# TODO - Send callback "OnWSError"
		self.NetworkAccessTickLock.acquire()
		try:
			self.AccessTick = 0
		finally:
			self.NetworkAccessTickLock.release()
		self.SetState("ACCESS_WAIT")

	def GetFileContent (self, file):
		return self.File.Load(file)

	def SetFileContent (self, file, content):
		self.File.SaveStateToFile(file, content)

	def AppendToFile (self, file, data):
		self.File.AppendToFile(file, data + "\n")

	def SaveBasicSensorValueToFile (self, uuid, value):
		self.AppendToFile(uuid + ".json", "{\"ts\":" + str(time.time()) + ",\"v\":" + str(value) + "},")

	def GetDeviceConfig (self):
		jsonConfigStr = self.File.Load("config.json")
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
	
	def StartLocalNode(self):
		print("TODO - (MkSNode.Run) Missing management of network HW disconnection")
		thread.start_new_thread(self.LocalServiceNode.NodeLocalNetworkConectionListener, ())

	def Run (self, callback):
		# Will be called each half a second.
		self.WorkingCallback = callback
		self.ExitEvent.clear()
		self.ExitLocalServerEvent.clear()
		# Initial state is connect to Gateway.
		self.SetState("CONNECT_HARDWARE")

		# We need to know if this worker is running for waiting mechanizm
		self.IsNodeMainEnabled = True

		# Read sytem configuration
		print("(MkSNode)# Load system configuration ...")
		if (self.LoadSystemConfig() is False):
			print("(MkSNode)# Load system configuration ... FAILED")
			return

		# Start local node dervice thread
		if self.IsNodeLocalServerEnabled is True:
			self.StartLocalNode()

		# Waiting here till SIGNAL from OS will come.
		while self.IsRunnig:
			# State machine management
			self.Method = self.States[self.State]
			self.Method()

			# User callback
			self.WorkingCallback()
			time.sleep(0.5)

		print ("(MkSNode)# Exit Node ...")
		self.Network.Disconnect()

		if self.IsHardwareBased is True:
			self.Connector.Disconnect()
		self.ExitEvent.set()
		
		if self.IsNodeMainEnabled is True:
			self.ExitEvent.wait()

		if self.LocalServiceNode.LocalSocketServerRun is True:
			self.ExitLocalServerEvent.wait()
	
	def Stop (self):
		print ("(MkSNode)# Stop Node ...")
		self.IsRunnig 								= False
		self.LocalServiceNode.LocalSocketServerRun 	= False
	
	def Pause (self):
		pass
	
	def Exit (self):
		self.Stop()
