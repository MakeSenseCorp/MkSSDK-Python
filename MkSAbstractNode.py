#!/usr/bin/python
import os
import sys
import json
if sys.version_info[0] < 3:
	import thread
else:
	import _thread
import threading
import time
import socket, select
import argparse
import logging
import Queue

import MkSGlobals
from mksdk import MkSFile
from mksdk import MkSUtils
from mksdk import MkSBasicNetworkProtocol
from mksdk import MkSSecurity
from mksdk import MkSLocalSocketMngr

class AbstractNode():
	def __init__(self):
		self.ClassName								= ""
		self.File 									= MkSFile.File()
		self.SocketServer							= MkSLocalSocketMngr.Manager()
		self.Network								= None
		self.LocalWSManager							= None
		self.MKSPath								= ""
		self.HostName								= socket.gethostname()
		# Device information
		self.Type 									= 0
		self.UUID 									= ""
		self.OSType 								= ""
		self.OSVersion 								= ""
		self.BrandName 								= ""
		self.Description							= ""
		self.BoardType 								= ""
		self.Name 									= "N/A"
		# Misc
		self.IsMainNodeRunnig 						= True
		self.AccessTick 							= 0 	# Network establishment counter
		self.RegisteredNodes  						= []
		self.System									= None
		self.SystemLoaded							= False
		self.IsHardwareBased 						= False
		self.IsNodeWSServiceEnabled 				= False # Based on HTTP requests and web sockets
		self.IsNodeLocalServerEnabled 				= False # Based on regular sockets
		self.IsLocalUIEnabled						= False
		self.Ticker 								= 0
		self.Pwd									= os.getcwd()
		self.IsMaster 								= False
		# Queue
		# State machine
		self.State 									= 'IDLE' # Current state of node
		self.States 								= None	 # States list
		# Locks and Events
		self.ExitLocalServerEvent					= threading.Event()
		# Debug
		self.DebugMode								= False	
		self.Logger 								= None
		# Callbacks
		self.WorkingCallback 						= None
		self.NodeSystemLoadedCallback 				= None
		self.OnLocalServerStartedCallback 			= None # Main local server (listener) rutin started.		
		self.OnApplicationRequestCallback			= None # Application will get this event on request arrived from local socket
		self.OnApplicationResponseCallback			= None # Application will get this event on response arrived from local socket
		self.OnAceptNewConnectionCallback			= None # Local server listener recieved new socket connection
		self.OnMasterFoundCallback					= None # When master node found or connected this event will be raised.
		self.OnMasterSearchCallback					= None # Raised on serach of master nodes start.
		self.OnMasterDisconnectedCallback			= None # When slave node loose connection with master node.
		self.OnTerminateConnectionCallback 			= None # When local server (listener) terminate socket connection.
		self.OnLocalServerListenerStartedCallback	= None # When loacl server (listener) succesfully binded port.
		self.OnShutdownCallback						= None # When node recieve command to terminate itself.
		self.OnGetNodesListCallback 				= None # Get all online nodes from GLOBAL gateway (Not implemented yet)
		# Registered items
		self.OnDeviceChangeList						= [] # Register command "register_on_node_change"
		# Synchronization
		self.DeviceChangeListLock 					= threading.Lock()
		# Services
		self.IPScannerServiceUUID					= ""
		self.EMailServiceUUID						= ""
		self.SMSServiceUUID							= ""
		self.Services 								= {}
		self.NetworkOnlineDevicesList 				= []
		# Timers
		self.ServiceSearchTS						= time.time()
		## Unused
		self.DeviceConnectedCallback 				= None
		# Initialization methods
		self.MyPID 									= os.getpid()
		self.MyLocalIP 								= ""
		self.NetworkCards 							= MkSUtils.GetIPList()
		# Network
		#self.MasterSocket							= None
		self.LocalMasterConnection					= None
		# Handlers
		self.NodeRequestHandlers					= {
			'get_node_info': 						self.GetNodeInfoRequestHandler,
			'get_node_status': 						self.GetNodeStatusRequestHandler,
			'get_file': 							self.GetFileRequestHandler,
			'register_on_node_change':				self.RegisterOnNodeChangeHandler,
			'unregister_on_node_change':			self.UnregisterOnNodeChangeHandler,
			'find_node':							self.FindNodeRequestHandler,
			'master_append_node':					self.MasterAppendNodeRequestHandler,
			'master_remove_node':					self.MasterRemoveNodeRequestHandler,
			'close_local_socket':					self.CloseLocalSocketRequestHandler
		}
		self.NodeResponseHandlers					= {
			'get_node_info': 						self.GetNodeInfoResponseHandler,
			'get_node_status': 						self.GetNodeStatusResponseHandler,
			'find_node': 							self.FindNodeResponseHandler,
			'master_append_node':					self.MasterAppendNodeResponseHandler,
			'master_remove_node':					self.MasterRemoveNodeResponseHandler,
			'get_online_devices':					self.GetOnlineDevicesResponseHandler
		}
		# LocalFace UI
		self.UI 									= None
		self.LocalWebPort							= ""
		self.BasicProtocol 							= MkSBasicNetworkProtocol.BasicNetworkProtocol()
		print(self.NetworkCards)

		self.Services[101] = {
			'uuid': "",
			'name': "eMail",
			'enabled': 0
		}

		self.Services[102] = {
			'uuid': "",
			'name': "SMS",
			'enabled': 0
		}

		self.Services[103] = {
			'uuid': "",
			'name': "IP Scanner",
			'enabled': 0
		}

		parser = argparse.ArgumentParser(description='Execution module called Node')
		parser.add_argument('--path', action='store',
							dest='pwd', help='Root folder of a Node')
		args = parser.parse_args()

		if args.pwd is not None:
			os.chdir(args.pwd)
		
		self.SocketServer.NewSocketEvent			= self.SocketConnectHandler
		self.SocketServer.CloseSocketEvent			= self.SocketDisconnectedHandler
		self.SocketServer.NewConnectionEvent 		= self.NewNodeConnectedHandler
		self.SocketServer.ConnectionRemovedEvent 	= self.NodeDisconnectedHandler
		self.SocketServer.DataArrivedEvent			= self.DataSocketInputHandler
		self.SocketServer.ServerStartetedEvent		= self.LocalServerStartedHandler
		
	# Overload
	def GatewayConnectedEvent(self):
		pass

	# Overload
	def GatewayDisConnectedEvent(self):
		pass

	# Overload
	def HandleExternalRequest(self, data):
		pass

	# Overload
	def NodeWorker(self):
		pass

	# Overload
	def SendGatewayPing(self):
		pass

	# Overload
	def GetNodeInfoRequestHandler(self, sock, packet):
		pass

	# Overload
	def GetNodeStatusRequestHandler(self, sock, packet):
		pass
	
	# Overload	
	def GetNodeInfoResponseHandler(self, sock, packet):
		pass
	
	# Overload
	def GetNodeStatusResponseHandler(self, sock, packet):
		pass

	# Overload
	def ExitRoutine(self):
		pass

	# Overload
	def SocketConnectHandler(self, conn, addr):
		pass

	# Overload
	def SocketDisconnectedHandler(self, sock):
		pass

	# Overload
	def NodeMasterAvailable(self, sock):
		pass

	# Overload
	def PreUILoaderHandler(self):
		pass

	# Overload
	def SendRequest(self, uuid, msg_type, command, payload, additional):
		pass

	# Overload
	def EmitOnNodeChange(self, payload):
		pass

	# Overload
	def LocalServerTerminated(self):
		pass

	# Overload
	def MasterAppendNodeRequestHandler(self, sock, packet):
		pass

	# Overload
	def MasterRemoveNodeRequestHandler(self, sock, packet):
		pass

	''' 
		Description:	Connect node (MASTER) over socket, add connection to connections list
						and add node to masters list.
		Return: 		Status (True/False).
	'''
	def ConnectMaster(self, ip):
		connection, status = self.SocketServer.Connect(ip, 16999)
		if status is True:
			connection.Obj["local_type"] = "MASTER"
			self.MasterNodesList.append(connection)
			if self.OnMasterFoundCallback is not None:
				self.OnMasterFoundCallback(connection)
			# Save socket as master socket
			self.LocalMasterConnection = connection
			return True

		return False

	''' 
		Description:	Connect node over socket, add connection to connections list.
		Return: 		Connection and status
	'''
	def ConnectNode(self, ip, port):
		return self.SocketServer.Connect(ip, port)

	''' 
		Description:	Search for MASTER nodes on local network.
		Return: 		IP list of MASTER nodes.
	'''
	def FindMasters(self):
		# Let user know master search started.
		if self.OnMasterSearchCallback is not None:
			self.OnMasterSearchCallback()
		# Find all master nodes on the network.
		ips = MkSUtils.FindLocalMasterNodes()
		for ip in ips:
			self.ConnectMaster(ip)
		return len(ips)
	
	''' 
		Description:	Connect node (MASTER) over socket, add connection to connections list
						and add node to masters list.
		Return: 		Status (True/False).
	'''
	def ConnectLocalMaster(self):
		return self.ConnectMaster(self.MyLocalIP)
	
	''' 
		Description: 	Send message over socket via message queue.
		Return: 		Status.
	'''	
	def SendMKSPacketOverLocalNetwork(self, uuid, msg_type, command, payload, additional):
		# Generate request
		message = self.BasicProtocol.BuildRequest(msg_type, uuid, self.UUID, command, payload, additional)
		packet  = self.BasicProtocol.AppendMagic(message)

	''' 
		Description: 	Get local node.
		Return: 		SocketConnection list.
	'''	
	def GetConnectedNodes(self):
		return self.SocketServer.GetConnections()

	''' 
		Description: 	Get local node by UUID.
		Return: 		SocketConnection.
	'''
	def GetNodeByUUID(self, uuid):
		connection_map = self.SocketServer.GetConnections()
		for key in connection_map:
			conn = connection_map[key]
			if conn.Obj["uuid"] == uuid:
				return conn
		return None

	''' 
		Description: 	<N/A>
		Return: 		<N/A>
	'''
	def SendBySocket(self, sock, command, payload):
		conn = self.SocketServer.GetConnectionBySock(sock)
		if conn is not None:
			message = self.BasicProtocol.BuildRequest("DIRECT", conn.Obj["uuid"], self.UUID, command, payload, {})
			packet  = self.BasicProtocol.AppendMagic(message)
			self.SocketServer.Send(sock, packet)
			return True
		return False
	
	''' 
		Description: 	<N/A>
		Return: 		<N/A>
	'''
	def SendBroadcastBySocket(self, sock, command):
		message = self.BasicProtocol.BuildRequest("BROADCAST", "UNKNOWN", self.UUID, command, {}, {})
		packet  = self.BasicProtocol.AppendMagic(message)
		self.SocketServer.Send(sock, packet)
		return True

	''' 
		Description: 	<N/A>
		Return: 		<N/A>
	'''	
	def SendBroadcastByUUID(self, uuid, command):
		conn = self.GetNodeByUUID(uuid)
		if conn is not None:
			return self.SendBroadcastBySocket(conn.Socket, command)
		return False
	
	''' 
		Description: 	Input handler binded to LocalSocketMngr callback.
		Return: 		None.
	'''
	def DataSocketInputHandler(self, connection, data):
		try:
			# Each makesense packet should start from magic number "MKS"
			if "MKSS" in data[:4]:
				# One packet can hold multiple MKS messages.
				multiData = data.split("MKSS:")
				for fragment in multiData[1:]:
					if "MKSE" in fragment:
						# Handling MKS packet
						raw_data	= fragment[:-5]
						sock 		= connection.Socket
						packet 		= json.loads(raw_data)
						messageType = self.BasicProtocol.GetMessageTypeFromJson(packet)
						command 	= self.BasicProtocol.GetCommandFromJson(packet)
						direction 	= self.BasicProtocol.GetDirectionFromJson(packet)
						destination = self.BasicProtocol.GetDestinationFromJson(packet)
						source 		= self.BasicProtocol.GetSourceFromJson(packet)
						broadcast 	= False

						packet["additional"]["client_type"] = "global_ws" # Why?
						self.LogMSG("({classname})# SOCK [{type}] [{direction}] {source} -> {dest} [{cmd}]".format(classname=self.ClassName,
									direction=direction,
									source=source,
									dest=destination,
									cmd=command,
									type=messageType), 5)
						
						if messageType == "BROADCAST":
							broadcast = True
						else:
							if destination in self.UUID and source in self.UUID:
								return
						
						# Is this packet for me or this packet for MASTER and I'm a Master or this message is BROADCAST?
						if destination in self.UUID or (destination in "MASTER" and 1 == self.Type) or broadcast is True:
							if direction in "request":
								if command in self.NodeRequestHandlers.keys():
									try:
										message = self.NodeRequestHandlers[command](sock, packet)
										if message == "" or message is None:
											return
										packet = self.BasicProtocol.AppendMagic(message)
										self.SocketServer.Send(sock, packet)
									except Exception as e:
										self.LogException("[DataSocketInputHandler #1] {0}".format(command),e,3)
								else:
									# This command belongs to the application level
									if self.OnApplicationRequestCallback is not None:
										try:
											message = self.OnApplicationRequestCallback(sock, packet)
											if message == "" or message is None:
												return
											packet = self.BasicProtocol.AppendMagic(message)
											self.SocketServer.Send(sock, packet)
										except Exception as e:
											self.LogException("[DataSocketInputHandler #2]",e,3)
							elif direction in "response":
								if command in self.NodeResponseHandlers.keys():
									try:
										self.NodeResponseHandlers[command](sock, packet)
									except Exception as e:
										self.LogException("[DataSocketInputHandler #3] {0}".format(command),e,3)
								else:
									# This command belongs to the application level
									if self.OnApplicationResponseCallback is not None:
										try:
											self.OnApplicationResponseCallback(sock, packet)
										except Exception as e:
											self.LogException("[DataSocketInputHandler #4]",e,3)
							else:
								pass
						else:
							# This massage is external (MOSTLY MASTER)
							try:
								if self.Network is not None:
									self.LogMSG("({classname})# This massage is external (MOSTLY MASTER)".format(classname=self.ClassName), 5)
									self.SendPacketGateway(raw_data)
							except Exception as e:
								self.LogException("[DataSocketInputHandler #5]",e,3)
					else:
						pass
			else:
				self.LogMSG("({classname})# [DataSocketInputHandler] Data Invalid ...".format(classname=self.ClassName), 4)
		except Exception as e:
			self.LogException("[DataSocketInputHandler]",e,3)
	
	''' 
		Description: 	This handler cslled after socket created and appended
						to the connections list with HASH and etc...
		Return: 		
	'''
	def NewNodeConnectedHandler(self, connection):
		if self.SocketServer.GetListenerSocket() != connection.Socket:
			# Raise event for user
			if self.OnAceptNewConnectionCallback is not None:
				self.OnAceptNewConnectionCallback(connection)
			self.SendBroadcastBySocket(connection.Socket, "get_node_info")
		
		# Initiate NODE information
		connection.Obj["uuid"] 			= "N/A"
		connection.Obj["type"] 			= 0
		connection.Obj["local_type"] 	= "CLIENT"
		connection.Obj["listener_port"] = 0
		connection.Obj["pid"] 			= 0
		connection.Obj["name"] 			= "N/A"
		connection.Obj["status"] 		= 1
		connection.Obj["is_slave"]		= 0
		connection.Obj["info"]			= None
	
	''' 
		Description: 	
		Return: 		
	'''
	def NodeDisconnectedHandler(self, connection):
		# Raise event for user
		if self.OnTerminateConnectionCallback is not None:
			self.OnTerminateConnectionCallback(connection)

	''' 
		Description: 	
		Return: 		
	'''	
	def LocalServerStartedHandler(self, connection):
		# Let know registered method about local server start.
		if self.OnLocalServerListenerStartedCallback is not None:
			self.OnLocalServerListenerStartedCallback(connection.Socket, connection.IP, connection.Port)
		# Update node information
		connection.Obj["uuid"] 			= self.UUID
		connection.Obj["type"] 			= self.Type
		connection.Obj["local_type"] 	= "LISTENER"
		connection.Obj["listener_port"] = 16999

		connection.Obj["pid"] 			= 0
		connection.Obj["name"] 			= "N/A"
		connection.Obj["status"] 		= 1

	''' 
		Description: 	Get devices in local network
		Return: 		None
	'''	
	def ScanNetwork(self):
		self.SendRequestToNode(self.Services[103]["uuid"], "get_online_devices", {})

	''' 
		Description: 	Get devices in local network handler. [RESPONSE]
		Return: 		None
	'''		
	def GetOnlineDevicesResponseHandler(self, sock, packet):
		self.LogMSG("({classname})# [GetOnlineDevicesResponseHandler]".format(classname=self.ClassName),5)
		payload = self.BasicProtocol.GetPayloadFromJson(packet)
		self.NetworkOnlineDevicesList = payload["online_devices"]

	''' 
		Description: 	Find nodes according to type and categories.
		Return: 		None
	'''	
	def FindNode(self, category1, category2, category3, node_type):
		payload = {
			'cat_1': category1,
			'cat_2': category2,
			'cat_3': category3,
			'type': node_type
		}
		self.SendRequest("BROADCAST", "BROADCAST", "find_node", payload, {})

	''' 
		Description: 	Find nodes according to type and categories handler. [RESPONSE]
		Return: 		None
	'''	
	def FindNodeResponseHandler(self, sock, packet):
		self.LogMSG("({classname})# [FindNodeResponseHandler]".format(classname=self.ClassName),5)
		payload 	= self.BasicProtocol.GetPayloadFromJson(packet)
		additional 	= self.BasicProtocol.GetAdditionalFromJson(packet)

		additional["online"] = True
		packet = self.BasicProtocol.SetAdditional(packet, additional)

		if payload["tagging"]["cat_1"] == "service":
			self.Services[payload["type"]]["uuid"] 		= payload["uuid"]
			self.Services[payload["type"]]["enabled"] 	= 1
		
		# Send threw node info handler as well.
		# self.GetNodeInfoResponseHandler(sock, packet)

	''' 
		Description: 	Find nodes according to type and categories handler. [REQUEST]
		Return: 		None
	'''	
	def FindNodeRequestHandler(self, sock, packet):
		self.LogMSG("({classname})# [FindNodeRequestHandler]".format(classname=self.ClassName),5)
		payload = self.BasicProtocol.GetPayloadFromJson(packet)
		cat_1 = payload["cat_1"]
		cat_2 = payload["cat_2"]
		cat_3 = payload["cat_3"]
		node_type = payload["type"]

		if str(node_type) == str(self.Type):
			return self.BasicProtocol.BuildResponse(packet, self.NodeInfo)

		if cat_1 in "service" and cat_2 in "network" and cat_3 in "ip_scanner" and node_type == 0:
			return self.BasicProtocol.BuildResponse(packet, self.NodeInfo)
		else:
			return ""
		
	def MasterAppendNodeResponseHandler(self, sock, packet):
		self.LogMSG("({classname})# [MasterAppendNodeResponseHandler]".format(classname=self.ClassName),5)
		payload 	= self.BasicProtocol.GetPayloadFromJson(packet)
		additional 	= self.BasicProtocol.GetAdditionalFromJson(packet)

		additional["online"] = True
		packet = self.BasicProtocol.SetAdditional(packet, additional)

		if payload["tagging"]["cat_1"] == "service":
			self.Services[payload["type"]]["uuid"] 		= payload["uuid"]
			self.Services[payload["type"]]["enabled"] 	= 1
		# Send threw node info handler as well.
		# self.GetNodeInfoResponseHandler(sock, packet)

	def MasterRemoveNodeResponseHandler(self, sock, packet):
		self.LogMSG("({classname})# [MasterRemoveNodeResponseHandler]".format(classname=self.ClassName),1)
		payload 	= self.BasicProtocol.GetPayloadFromJson(packet)
		additional = self.BasicProtocol.GetAdditionalFromJson(packet)
		self.LogMSG("({classname})# [MasterRemoveNodeResponseHandler] {0}".format(payload,classname=self.ClassName),5)
		
		additional["online"] = False
		packet = self.BasicProtocol.SetAdditional(packet, additional)

		if payload["tagging"]["cat_1"] == "service":
			self.Services[payload["type"]]["uuid"] 		= ""
			self.Services[payload["type"]]["enabled"] 	= 0
		# self.GetNodeInfoResponseHandler(sock, packet)
	
	def CloseLocalSocketRequestHandler(self, sock, packet):
		payload	= self.BasicProtocol.GetPayloadFromJson(packet)
		self.LogMSG("({classname})# [CloseLocalSocketRequestHandler] {0}".format(payload, classname=self.ClassName),5)
		self.RemoveConnectionBySock(sock)
		#if self.MasterSocket == sock:
		#	self.MasterSocket = None
	
	def SetState (self, state):
		self.LogMSG("({classname})# Change state [{0}]".format(state,classname=self.ClassName),5)
		self.State = state
	
	def GetState (self):
		return self.State
	
	def GetServices(self):
		enabled_services = []
		for key in self.Services:
			if self.Services[key]["enabled"] == 1:
				enabled_services.append({ 
					'name': self.Services[key]["name"],
					'type': key
				})
		return enabled_services

	def FindSMSService(self):
		self.FindNode("service", "network", "sms", 0)
	
	def FindEmailService(self):
		self.FindNode("service", "network", "email", 0)

	def FindIPScannerService(self):
		self.FindNode("service", "network", "ip_scanner", 0)

	def GetNetworkOnlineDevicesList(self):
		return self.NetworkOnlineDevicesList

	def SendRequestToNode(self, uuid, command, payload):
		self.SendRequest(uuid, "DIRECT", command, payload, {})

	def AppendDeviceChangeListNode(self, payload):
		self.DeviceChangeListLock.acquire()
		for item in self.OnDeviceChangeList:
			if item["uuid"] == payload["uuid"]:
				self.DeviceChangeListLock.release()
				return

		self.OnDeviceChangeList.append({
			'ts':		time.time(),
			'payload':	payload
		})		
		self.DeviceChangeListLock.release()

	def AppendDeviceChangeListLocal(self, payload):
		self.DeviceChangeListLock.acquire()
		for item in self.OnDeviceChangeList:
			if item["payload"]["ws_id"] == payload["ws_id"]:
				self.DeviceChangeListLock.release()
				return

		self.OnDeviceChangeList.append({
			'ts':		time.time(),
			'payload':	payload
		})		
		self.DeviceChangeListLock.release()
	
	def AppendDeviceChangeListGlobal(self, payload):
		self.DeviceChangeListLock.acquire()
		for item in self.OnDeviceChangeList:
			if item["payload"]["webface_indexer"] == payload["webface_indexer"]:
				self.DeviceChangeListLock.release()
				return

		self.OnDeviceChangeList.append({
			'ts':		time.time(),
			'payload':	payload
		})		
		self.DeviceChangeListLock.release()
	
	def RemoveDeviceChangeListNode(self, uuid):
		# Context of geventwebsocket (PAY ATTENTION)
		self.DeviceChangeListLock.acquire()
		is_removed = False

		for i in xrange(len(self.OnDeviceChangeList) - 1, -1, -1):
			item = self.OnDeviceChangeList[i]
			item_payload = item["payload"]
			if item_payload["uuid"] == uuid:
				del self.OnDeviceChangeList[i]
				self.LogMSG("({classname})# Unregistered WEBFACE local session ({uuid}) ({length}))".format(classname=self.ClassName,
						uuid=str(uuid),
						length=len(self.OnDeviceChangeList)),5)
				is_removed = True
		self.DeviceChangeListLock.release()
		return is_removed

	def RemoveDeviceChangeListLocal(self, id):
		# Context of geventwebsocket (PAY ATTENTION)
		self.DeviceChangeListLock.acquire()
		is_removed = False

		for i in xrange(len(self.OnDeviceChangeList) - 1, -1, -1):
			item = self.OnDeviceChangeList[i]
			item_payload = item["payload"]
			if "ws_id" in item_payload:
				if item_payload["ws_id"] == id:
					del self.OnDeviceChangeList[i]
					self.LogMSG("({classname})# Unregistered WEBFACE local session ({ws_id}) ({length}))".format(classname=self.ClassName,
							ws_id=str(id),
							length=len(self.OnDeviceChangeList)),5)
					is_removed = True
		self.DeviceChangeListLock.release()
		return is_removed
	
	def RemoveDeviceChangeListGlobal(self, id):
		self.DeviceChangeListLock.acquire()
		for item in self.OnDeviceChangeList:
			item_payload = item["payload"]
			if "webface_indexer" in item_payload:
				if item_payload["webface_indexer"] == id:
					self.OnDeviceChangeList.remove(item)
					self.LogMSG("({classname})# Unregistered WEBFACE global session ({webface_indexer}))".format(classname=self.ClassName,
							webface_indexer=str(id)),5)
					self.DeviceChangeListLock.release()
					return True
		self.DeviceChangeListLock.release()
		return False

	def UnRegisterOnNodeChangeEvent(self, uuid):
		self.SendRequestToNode(uuid, "unregister_on_node_change", {
				'item_type': 1,
				'uuid':	self.UUID
			})

	def RegisterOnNodeChangeEvent(self, uuid):
		self.SendRequestToNode(uuid, "register_on_node_change", {
				'item_type': 1,
				'uuid':	self.UUID
			})
	
	def RegisterOnNodeChangeHandler(self, sock, packet):
		self.LogMSG("({classname})# On Node change request recieved ....".format(classname=self.ClassName),5)
		payload 	= self.BasicProtocol.GetPayloadFromJson(packet)
		item_type 	= payload["item_type"]
		# Node
		if item_type == 1:
			self.AppendDeviceChangeListNode(payload)
		# Webface
		elif item_type == 2:
			piggy = self.BasicProtocol.GetPiggybagFromJson(packet)
			payload["pipe"] = packet["additional"]["pipe"]
			if packet["additional"]["pipe"] == "GATEWAY":
				payload["webface_indexer"] = piggy["webface_indexer"]
				self.AppendDeviceChangeListGlobal(payload)
			elif packet["additional"]["pipe"] == "LOCAL_WS":
				payload["ws_id"] = packet["additional"]["ws_id"]
				self.AppendDeviceChangeListLocal(payload)
			
			return self.BasicProtocol.BuildResponse(packet, {
				'registered': "OK"
			})
		
		return self.BasicProtocol.BuildResponse(packet, {
			'registered': "NO REGISTERED"
		})
	
	def UnregisterOnNodeChangeHandler(self, sock, packet):
		payload 		= self.BasicProtocol.GetPayloadFromJson(packet)
		item_type		= payload["item_type"]

		# Node
		if item_type == 1:
			uuid = payload["uuid"]
			self.RemoveDeviceChangeListNode(uuid)
		# Webface
		elif item_type == 2:
			if packet["additional"]["pipe"] == "GATEWAY":
				webface_indexer = payload["webface_indexer"]
				if self.UnregisterGlobalWS(webface_indexer) is True:
					return self.BasicProtocol.BuildResponse(packet, {
						'unregistered': "OK"
					})
			elif packet["additional"]["pipe"] == "LOCAL_WS":
				ws_id = packet["additional"]["ws_id"]
				if self.UnregisterLocalWS(ws_id) is True:
					return self.BasicProtocol.BuildResponse(packet, {
						'unregistered': "OK"
					})
		
		return self.BasicProtocol.BuildResponse(packet, {
			'unregistered': "FAILED"
		})
	
	def UnregisterLocalWS(self, id):
		return self.RemoveDeviceChangeListLocal(id)

	def UnregisterGlobalWS(self, id):
		return self.RemoveDeviceChangeListGlobal(id)

	''' 
		Description: 	Get file handler [REQUEST]
		Return: 		N/A
	'''	
	def GetFileRequestHandler(self, sock, packet):
		objFile 		= MkSFile.File()
		payload 		= self.BasicProtocol.GetPayloadFromJson(packet)
		uiType 			= payload["ui_type"]
		fileType 		= payload["file_type"]
		fileName 		= payload["file_name"]
		client_type 	= packet["additional"]["client_type"]
		stamping 		= packet["stamping"]
		# TODO - Node should get type of machine the node ui running on.
		machine_type 	= "pc"

		folder = {
			'config': 		'config',
			'app': 			'app',
			'thumbnail': 	'thumbnail'
		}

		path 	= os.path.join(".","ui",machine_type,folder[uiType],"ui." + fileType)
		content = objFile.Load(path)
		
		if ("html" in fileType):
			content = content.replace("[NODE_UUID]", self.UUID)
			if stamping is None:
				self.LogMSG("({classname})# [ERROR] Missing STAMPING in packet ...".format(classname=self.ClassName),3)
				content = content.replace("[GATEWAY_IP]", self.GatewayIP)
			else:
				if "cloud_t" in stamping:
					# TODO - Cloud URL must be in config.json
					content = content.replace("[GATEWAY_IP]", "ec2-54-188-199-33.us-west-2.compute.amazonaws.com")
				else:
					content = content.replace("[GATEWAY_IP]", self.GatewayIP)

			css 	= ""
			script 	= ""
			if client_type == "global_ws":
				script = '''					
					<script src="mksdk-js/MkSAPI.js"></script>
					<script src="mksdk-js/MkSCommon.js"></script>
					<script src="mksdk-js/MkSGateway.js"></script>
					<script src="mksdk-js/MkSWebface.js"></script>
				'''
			elif client_type == "local_ws":
				pass
			else:
				pass
		
			content = content.replace("[CSS]",css)
			content = content.replace("[SCRIPTS]",script)

		# TODO - Minify file content
		content = content.replace("\t","")
		self.LogMSG("({classname})# Requested file: {path} ({fileName}.{fileType}) ({length})".format(classname=self.ClassName,
				path=path,
				fileName=fileName,
				fileType=fileType,
				length=str(len(content))),5)
		
		return self.BasicProtocol.BuildResponse(packet, {
								'file_type': fileType,
								'ui_type': uiType,
								'content': content.encode('hex')
		})

	''' 
		Description: 	N/A
		Return: 		N/A
	'''	
	def LoadSystemConfig(self):
		self.MKSPath = os.path.join(os.environ['HOME'],"mks")
		# Information about the node located here.
		strSystemJson 		= self.File.Load("system.json") # Located in node context
		strMachineJson 		= self.File.Load(os.path.join(self.MKSPath,"config.json"))

		if (strSystemJson is None or len(strSystemJson) == 0):
			self.LogMSG("({classname})# ERROR - Cannot find system.json file.".format(classname=self.ClassName),2)
			self.Exit("ERROR - Cannot find system.json file")
			return False

		if (strMachineJson is None or len(strMachineJson) == 0):
			self.LogMSG("({classname})# ERROR - Cannot find config.json file.".format(classname=self.ClassName),2)
			self.Exit("ERROR - Cannot find config.json file")
			return False
		
		try:
			dataSystem 				= json.loads(strSystemJson)
			dataConfig 				= json.loads(strMachineJson)
			self.NodeInfo 			= dataSystem["node"]["info"]
			self.ServiceDepened 	= dataSystem["node"]["service"]["depend"]
			self.System				= dataSystem["node"]["system"]
		
			self.EnableLogs(str(self.NodeInfo["type"]))
			self.LogMSG("({classname})# MakeSense HOME folder '{0}'".format(self.MKSPath, classname=self.ClassName),5)

			for network in self.NetworkCards:
				if network["iface"] in dataConfig["network"]["iface"]:
					self.MyLocalIP = network["ip"]
					self.LogMSG("({classname})# Local IP found ... {0}".format(self.MyLocalIP,classname=self.ClassName),5)
					break
			
			if self.MyLocalIP == "":
				self.LogMSG("({classname})# ERROR - Local IP not found".format(classname=self.ClassName),3)

			# Node connection to WS information
			self.Key 				= dataConfig["network"]["key"]
			self.GatewayIP			= dataConfig["network"]["gateway"]
			self.ApiPort 			= dataConfig["network"]["apiport"]
			self.WsPort 			= dataConfig["network"]["wsport"]
			self.ApiUrl 			= "http://{gateway}:{api_port}".format(gateway=self.GatewayIP, api_port=self.ApiPort)
			self.WsUrl				= "ws://{gateway}:{ws_port}".format(gateway=self.GatewayIP, ws_port=self.WsPort)
			# Device information
			self.Type 				= self.NodeInfo["type"]
			self.OSType 			= self.NodeInfo["ostype"]
			self.OSVersion 			= self.NodeInfo["osversion"]
			self.BrandName 			= self.NodeInfo["brandname"]
			self.Name 				= self.NodeInfo["name"]
			self.Description 		= self.NodeInfo["description"]
			# TODO - Why is that?
			if (self.Type == 1):
				self.BoardType 		= self.NodeInfo["boardType"]
			self.UserDefined		= dataSystem["user"]
			# Device UUID MUST be read from HW device.
			if "True" == self.NodeInfo["isHW"]:
				self.IsHardwareBased = True
			else:
				self.UUID = self.NodeInfo["uuid"]
			
			self.BasicProtocol.SetKey(self.Key)
		except Exception as e:
			self.LogException("Wrong configuration format",e,2)
			self.Exit("ERROR - Wrong configuration format")
			return False
		
		return True

	''' 
		Description: 	N/A
		Return: 		N/A
	'''		
	def SetWebServiceStatus(self, is_enabled):
		self.IsNodeWSServiceEnabled = is_enabled

	''' 
		Description: 	N/A
		Return: 		N/A
	'''	
	def SetLocalServerStatus(self, is_enabled):
		self.IsNodeLocalServerEnabled = is_enabled
	
	def ServicesManager(self):
		if self.IsMaster is True:
			return
		
		if len(self.ServiceDepened) == 0:
			return
		
		if time.time() - self.ServiceSearchTS > 10:
			for depend_srv_type in self.ServiceDepened:
				for key in self.Services:
					service = self.Services[key]
					if key == depend_srv_type:
						if service["enabled"] == 0:
							self.FindNode("", "", "", depend_srv_type)
						else:
							self.ScanNetwork()
			self.ServiceSearchTS = time.time()

	''' 
		Description: 	N/A
		Return: 		N/A
	'''	
	def LogMSG(self, message, level):
		if self.Logger is not None:
			self.Logger.Log(message, level)
		else:
			print("({classname})# [NONE LOGGER] - {0}".format(message,classname=self.ClassName))

	''' 
		Description: 	N/A
		Return: 		N/A
	'''	
	def LogException(self, message, e, level):
		if self.Logger is not None:
			exeption = "({classname})# ********** EXCEPTION **********\n----\nINFO\n----\n{0}\n-----\nERROR\n-----\n({error})\n********************************\n".format(
				message,
				classname=self.ClassName,
				error=str(e))
			self.Logger.Log(exeption, level)
		else:
			print("({classname})# ********** EXCEPTION **********\n----\nINFO\n----\n{0}\n-----\nERROR\n-----\n({error})\n********************************\n".format(
				message,
				classname=self.ClassName,
				error=str(e)))
	
	''' 
		Description: 	N/A
		Return: 		N/A
	'''	
	def Run (self, callback):
		# Will be called each half a second.
		self.WorkingCallback = callback
		# Read sytem configuration
		if (self.LoadSystemConfig() is False):
			print("({classname})# Load system configuration ... FAILED".format(classname=self.ClassName))
			return
		
		self.LogMSG("({classname})# System configuration loaded".format(classname=self.ClassName),5)
		self.SetState("INIT")

		# Start local node dervice thread
		self.ExitLocalServerEvent.clear()
		if self.IsNodeLocalServerEnabled is True:
			self.SocketServer.Logger = self.Logger
			self.SocketServer.SetExitSync(self.ExitLocalServerEvent)

		# Waiting here till SIGNAL from OS will come.
		while self.IsMainNodeRunnig:
			# State machine management
			self.Method = self.States[self.State]
			self.Method()

			# User callback
			if ("WORKING" == self.GetState() and self.SystemLoaded is True):
				self.ServicesManager() # TODO - Must be in differebt thread
				self.WorkingCallback()

			self.Ticker += 1
			time.sleep(0.5)
		
		self.LogMSG("({classname})# Start Exiting Node ...".format(classname=self.ClassName),5)

		# If websocket server enabled, shut it down.
		if self.IsNodeWSServiceEnabled is True:
			if self.Network is not None:
				self.Network.Disconnect()

		# If local socket server enabled (most nodes), shut it down.
		if self.IsNodeLocalServerEnabled is True:
			self.SocketServer.Stop()
			self.ExitLocalServerEvent.wait()
	
	''' 
		Description: 	N/A
		Return: 		N/A
	'''	
	def Stop (self, reason):
		self.LogMSG("({classname})# Stop Node ... ({0})".format(reason,classname=self.ClassName),5)
		self.IsMainNodeRunnig 		= False
		self.IsLocalSocketRunning 	= False

	''' 
		Description: 	N/A
		Return: 		N/A
	'''	
	def Pause (self):
		pass

	''' 
		Description: 	N/A
		Return: 		N/A
	'''	
	def Exit (self, reason):
		self.Stop(reason)
