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
from mksdk import MkSDevice
from mksdk import MkSUtils
from mksdk import MkSBasicNetworkProtocol
from mksdk import MkSSecurity
from mksdk import MkSLocalSocketMngr

class AbstractNode():
	def __init__(self):
		self.ClassName								= ""
		self.File 									= MkSFile.File()
		self.SocketServer							= MkSLocalSocketMngr.Manager()
		self.Connector 								= None
		self.Network								= None
		self.LocalWSManager							= None
		self.MKSPath								= ""
		# Device information
		self.Type 									= 0
		self.UUID 									= ""
		self.OSType 								= ""
		self.OSVersion 								= ""
		self.BrandName 								= ""
		self.Description							= ""
		self.DeviceInfo 							= None
		self.BoardType 								= ""
		self.Name 									= "N/A"
		# Misc
		self.IsMainNodeRunnig 						= True
		self.AccessTick 							= 0 	# Network establishment counter
		self.RegisteredNodes  						= []
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
		self.ExitEvent 								= threading.Event()
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
		self.OnExitCallback							= None # When node recieve command to terminate itself.
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
			'get_file': 							self.GetFileHandler,
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
			'get_online_devices':					self.GetOnlineDevicesHandler
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
		self.SocketServer.ServerStatrtedEvent		= self.LocalServerStartedHandler
		
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
		connection, status = self.SocketServer.Connect((ip, 16999))
		if status is True:
			connection.Obj["name"] = "MASTER"
			self.MasterNodesList.append(connection)
			if self.OnMasterFoundCallback is not None:
				self.OnMasterFoundCallback(connection)
			# Save socket as master socket
			self.LocalMasterConnection = connection
			return True

		return False

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
		Description: 	Get local node by UUID.
		Return: 		SocketConnection.
	'''
	def GetNodeByUUID(self, uuid):
		connection_map = self.SocketServer.GetConnections()
		for key in self.connection_map:
			conn = self.connection_map[key]
			if conn.Obj["uuid"] == uuid:
				return conn
		return None

	''' 
		Description: 	<N/A>
		Return: 		<N/A>
	'''
	def SendBroadcastBySocket(self, sock, command):
		message = self.BasicProtocol.BuildRequest("BROADCAST", "", self.UUID, command, {}, {})
		packet  = self.BasicProtocol.AppendMagic(message)
		self.ServerSocket.Send(sock, packet)
		return True

	''' 
		Description: 	<N/A>
		Return: 		<N/A>
	'''	
	def SendBroadcastByUUID(self, uuid, command):
		conn = self.GetNodeByUUID(uuid)
		if conn is not None:
			message = self.BasicProtocol.BuildRequest("BROADCAST", "", self.UUID, command, {}, {})
			packet  = self.BasicProtocol.AppendMagic(message)
			self.ServerSocket.Send(conn.Socket, packet)
			return True
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
						sock 		= connection.Socket
						packet 		= json.loads(fragment[:-5])
						messageType = self.BasicProtocol.GetMessageTypeFromJson(packet)
						command 	= self.BasicProtocol.GetCommandFromJson(packet)
						direction 	= self.BasicProtocol.GetDirectionFromJson(packet)
						destination = self.BasicProtocol.GetDestinationFromJson(packet)
						source 		= self.BasicProtocol.GetSourceFromJson(packet)
						broadcast 	= False

						packet["additional"]["client_type"] = "global_ws" # Why?
						self.Logger.Log("({classname})# SOCK [{direction}] {source} -> {dest} [{cmd}]".format(classname=self.ClassName,
									direction=direction,
									source=source,
									dest=destination,
									cmd=command))
						
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
										self.ServerSocket.Send(sock, packet)
									except Exception as e:
										self.Logger.Log("({classname})# ERROR - [#1]\n(EXEPTION)# {error}".format(error=str(e),classname=self.ClassName))
								else:
									# This command belongs to the application level
									if self.OnApplicationRequestCallback is not None:
										try:
											message = self.OnApplicationRequestCallback(sock, packet)
											if message == "" or message is None:
												return
											packet = self.BasicProtocol.AppendMagic(message)
											self.ServerSocket.Send(sock, packet)
										except Exception as e:
											self.Logger.Log("({classname})# ERROR - [#2]\n(EXEPTION)# {error}".format(error=str(e),classname=self.ClassName))
							elif direction in "response":
								if command in self.NodeResponseHandlers.keys():
									try:
										self.NodeResponseHandlers[command](sock, packet)
									except Exception as e:
										self.Logger.Log("({classname})# ERROR - [#3]\n(EXEPTION)# {error}".format(error=str(e),classname=self.ClassName))
								else:
									# This command belongs to the application level
									if self.OnApplicationResponseCallback is not None:
										try:
											self.OnApplicationResponseCallback(sock, packet)
										except Exception as e:
											self.Logger.Log("({classname})# ERROR - [#4]\n(EXEPTION)# {error}".format(error=str(e),classname=self.ClassName))
							else:
								pass
						else:
							# This massage is external (MOSTLY MASTER)
							try:
								if self.Network is not None:
									self.Logger.Log("({classname})# This massage is external (MOSTLY MASTER)".format(classname=self.ClassName))
									self.SendPacketGateway(data)
							except Exception as e:
								self.Logger.Log("({classname})# ERROR - [#5]\n(EXEPTION)# {error}".format(error=str(e),classname=self.ClassName))
					else:
						pass
			else:
				self.Logger.Log("({classname})# [DataSocketInputHandler] Data Invalid ...".format(classname=self.ClassName))
		except Exception as e:
			self.Logger.Log("({classname})# [DataSocketInputHandler] ERROR - {error}".format(error=str(e),classname=self.ClassName))
	
	''' 
		Description: 	This handler cslled after socket created and appended
						to the connections list with HASH and etc...
		Return: 		
	'''
	def NewNodeConnectedHandler(self, connection):
		# Raise event for user
		if self.OnAceptNewConnectionCallback is not None:
			self.OnAceptNewConnectionCallback(connection)
		self.SendBroadcastBySocket(connection.Socket, "get_node_info")
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
		connection.Obj["uuid"] 	= self.UUID
		connection.Obj["type"] 	= self.Type
		connection.Obj["name"] 	= "LISTENER"

		#if self.IsLocalUIEnabled is True:
		#	# Run preloader for UI interface
		#	if self.UI is None:
		#		self.Logger.Log("({classname})# Executing UI preloader (Only valid for local UI aka Webface)".format(classname=self.ClassName))
		#		self.PreUILoaderHandler()

		# Run UI thread
		#if self.IsLocalUIEnabled is True:
		#	if self.UI is None:
		#		self.Logger.Log("({classname})# Local UI(Webface) is not set ... (NULL)".format(classname=self.ClassName))
		#	else:
		#		self.Logger.Log("({classname})# Running local UI(Webface)".format(classname=self.ClassName))
		#		self.UI.Run()

	def GetOnlineDevicesHandler(self, sock, packet):
		self.Logger.Log("({classname})# Online network device list ...".format(classname=self.ClassName))
		payload = self.BasicProtocol.GetPayloadFromJson(packet)
		self.NetworkOnlineDevicesList = payload["online_devices"]

	def MasterAppendNodeResponseHandler(self, sock, packet):
		payload 	= self.BasicProtocol.GetPayloadFromJson(packet)
		additional = self.BasicProtocol.GetAdditionalFromJson(packet)

		additional["online"] = True
		packet = self.BasicProtocol.SetAdditional(packet, additional)

		if payload["tagging"]["cat_1"] == "service":
			self.Services[payload["type"]]["uuid"] 		= payload["uuid"]
			self.Services[payload["type"]]["enabled"] 	= 1
		self.GetNodeInfoResponseHandler(sock, packet)

	def MasterRemoveNodeResponseHandler(self, sock, packet):
		payload 	= self.BasicProtocol.GetPayloadFromJson(packet)
		additional = self.BasicProtocol.GetAdditionalFromJson(packet)
		
		additional["online"] = False
		packet = self.BasicProtocol.SetAdditional(packet, additional)

		if payload["tagging"]["cat_1"] == "service":
			self.Services[payload["type"]]["uuid"] 		= ""
			self.Services[payload["type"]]["enabled"] 	= 0
		self.GetNodeInfoResponseHandler(sock, packet)
	
	def CloseLocalSocketRequestHandler(self, sock, packet):
		payload	= self.BasicProtocol.GetPayloadFromJson(packet)
		self.Logger.Log("({classname})# Close server socket request ... {0}".format(payload, classname=self.ClassName))
		self.RemoveConnectionBySock(sock)
		#if self.MasterSocket == sock:
		#	self.MasterSocket = None

	def FindNodeResponseHandler(self, sock, packet):
		payload 	= self.BasicProtocol.GetPayloadFromJson(packet)
		additional 	= self.BasicProtocol.GetAdditionalFromJson(packet)

		additional["online"] = True
		packet = self.BasicProtocol.SetAdditional(packet, additional)

		if payload["tagging"]["cat_1"] == "service":
			self.Services[payload["type"]]["uuid"] 		= payload["uuid"]
			self.Services[payload["type"]]["enabled"] 	= 1
		self.GetNodeInfoResponseHandler(sock, packet)

	def FindNodeRequestHandler(self, sock, packet):
		self.Logger.Log("({classname})# Search node request ...".format(classname=self.ClassName))
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
	
	def SetState (self, state):
		self.Logger.Log("({classname})# Change state [{0}]".format(state,classname=self.ClassName))
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
	
	def ScanNetwork(self):
		self.SendRequestToNode(self.Services[103]["uuid"], "get_online_devices", {})

	def GetNetworkOnlineDevicesList(self):
		return self.NetworkOnlineDevicesList

	def FindNode(self, category1, category2, category3, node_type):
		payload = {
			'cat_1': category1,
			'cat_2': category2,
			'cat_3': category3,
			'type': node_type
		}
		self.SendRequest("BROADCAST", "BROADCAST", "find_node", payload, {})

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
				self.Logger.Log("({classname})# Unregistered WEBFACE local session ({uuid}) ({length}))".format(classname=self.ClassName,
						uuid=str(uuid),
						length=len(self.OnDeviceChangeList)))
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
					self.Logger.Log("({classname})# Unregistered WEBFACE local session ({ws_id}) ({length}))".format(classname=self.ClassName,
							ws_id=str(id),
							length=len(self.OnDeviceChangeList)))
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
					self.Logger.Log("({classname})# Unregistered WEBFACE global session ({webface_indexer}))".format(classname=self.ClassName,
							webface_indexer=str(id)))
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
		self.Logger.Log("({classname})# On Node change request recieved ....".format(classname=self.ClassName))
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

	def GetFileHandler(self, sock, packet):
		objFile 		= MkSFile.File()
		payload 		= self.BasicProtocol.GetPayloadFromJson(packet)
		uiType 			= payload["ui_type"]
		fileType 		= payload["file_type"]
		fileName 		= payload["file_name"]
		client_type 	= packet["additional"]["client_type"]
		stamping 		= packet["stamping"]
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
				self.Logger.Log("({classname})# [ERROR] Missing STAMPING in packet ...".format(classname=self.ClassName))
				content = content.replace("[GATEWAY_IP]", self.GatewayIP)
			else:
				if "cloud_t" in stamping:
					content = content.replace("[GATEWAY_IP]", "ec2-54-188-199-33.us-west-2.compute.amazonaws.com")
				else:
					content = content.replace("[GATEWAY_IP]", self.GatewayIP)

			if client_type == "global_ws":
				css = '''
					<link rel="stylesheet" href="/static/lib/bootstrap/css/bootstrap.min.css" crossorigin="anonymous">
					<link rel="stylesheet" href="/static/lib/bootstrap/css/bootstrap-slider.css" crossorigin="anonymous">
					<link rel="stylesheet" href="/static/lib/fontawesome-5.11.2/css/all.min.css">
					<link rel="stylesheet" href="/static/lib/bootstrap4-editable/css/bootstrap-editable.css">
					<link rel="stylesheet" href="/static/lib/chartjs/2.9.3/Chart.min.css">
					<link rel="stylesheet" href="/static/lib/datetimepicker/bootstrap-datetimepicker.min.css">
				'''

				script = '''
					<script src="/static/lib/nodes/js/jquery_3_3_1/jquery.min.js"></script>
					<script src="/static/lib/nodes/js/popper_1_14_7/popper.min.js" crossorigin="anonymous"></script>
					<script src="/static/lib/bootstrap/js/bootstrap.min.js" crossorigin="anonymous"></script>
					<script src="/static/lib/bootstrap/js/bootstrap-slider.js" crossorigin="anonymous"></script>
					<script src="/static/lib/nodes/js/feather_4_19/feather.min.js"></script>
					<script src="/static/lib/nodes/map/feather_4_19/feather.min.js.map"></script>
					<script src="/static/lib/bootstrap4-editable/js/bootstrap-editable.min.js"></script>
					<script src="/static/lib/chartjs/2.9.3/Chart.min.js"></script>
					<script src="/static/lib/datetimepicker/bootstrap-datetimepicker.min.js"></script>
					
					<script src="mksdk-js/MkSAPI.js"></script>
					<script src="mksdk-js/MkSCommon.js"></script>
					<script src="mksdk-js/MkSGateway.js"></script>
					<script src="mksdk-js/MkSWebface.js"></script>
				'''
			elif client_type == "local_ws":
				css = '''
					<link rel="stylesheet" href="static/lib/bootstrap/css/bootstrap.min.css" crossorigin="anonymous">
					<link rel="stylesheet" href="static/lib/bootstrap/css/bootstrap-slider.css" crossorigin="anonymous">
					<link rel="stylesheet" href="static/lib/fontawesome-5.11.2/css/all.min.css">
					<link rel="stylesheet" href="static/lib/bootstrap4-editable/css/bootstrap-editable.css">
					<link rel="stylesheet" href="static/lib/chartjs/2.9.3/Chart.min.css">
					<link rel="stylesheet" href="static/lib/datetimepicker/bootstrap-datetimepicker.min.css">
				'''

				script = '''
					<script src="static/lib/nodes/js/jquery_3_3_1/jquery.min.js"></script>
					<script src="static/lib/nodes/js/popper_1_14_7/popper.min.js" crossorigin="anonymous"></script>
					<script src="static/lib/bootstrap/js/bootstrap.min.js" crossorigin="anonymous"></script>
					<script src="static/lib/bootstrap/js/bootstrap-slider.js" crossorigin="anonymous"></script>
					<script src="static/lib/nodes/js/feather_4_19/feather.min.js"></script>
					<script src="static/lib/nodes/map/feather_4_19/feather.min.js.map"></script>
					<script src="static/lib/bootstrap4-editable/js/bootstrap-editable.min.js"></script>
					<script src="static/lib/chartjs/2.9.3/Chart.min.js"></script>
					<script src="static/lib/datetimepicker/bootstrap-datetimepicker.min.js"></script>
					
					<script src="static/mksdk-js/MkSCommon.js"></script>
					<script src="static/mksdk-js/MkSAPI.js"></script>
					<script src="static/mksdk-js/MkSGateway.js"></script>
					<script src="static/mksdk-js/MkSWebface.js"></script>
				'''
			else:
				css 	= ""
				script 	= ""
		
			content = content.replace("[CSS]",css)
			content = content.replace("[SCRIPTS]",script)


		# TODO - Minify file content
		content = content.replace("\t","")
		self.Logger.Log("({classname})# Requested file: {path} ({fileName}.{fileType}) ({length})".format(classname=self.ClassName,
				path=path,
				fileName=fileName,
				fileType=fileType,
				length=str(len(content))))
		
		return self.BasicProtocol.BuildResponse(packet, {
								'file_type': fileType,
								'ui_type': uiType,
								'content': content.encode('hex')
		})

	def LoadSystemConfig(self):
		self.MKSPath = os.path.join(os.environ['HOME'],"mks")
		# Information about the node located here.
		strSystemJson 		= self.File.Load("system.json") # Located in node context
		strMachineJson 		= self.File.Load(os.path.join(self.MKSPath,"config.json"))

		if (strSystemJson is None or len(strSystemJson) == 0):
			#self.Logger.Log("({classname})# ERROR - Cannot find system.json file.".format(classname=self.ClassName))
			self.Exit("ERROR - Cannot find system.json file")
			return False

		if (strMachineJson is None or len(strMachineJson) == 0):
			#self.Logger.Log("({classname})# ERROR - Cannot find config.json file.".format(classname=self.ClassName))
			self.Exit("ERROR - Cannot find config.json file")
			return False
		
		try:
			dataSystem 				= json.loads(strSystemJson)
			dataConfig 				= json.loads(strMachineJson)
			self.NodeInfo 			= dataSystem["node"]["info"]
			self.ServiceDepened 	= dataSystem["node"]["service"]["depend"]
		
			self.EnableLogs(str(self.NodeInfo["type"]))
			self.Logger.Log("({classname})# MakeSense HOME folder '{0}'".format(self.MKSPath, classname=self.ClassName))

			for network in self.NetworkCards:
				if network["iface"] in dataConfig["network"]["iface"]:
					self.MyLocalIP = network["ip"]
					self.Logger.Log("({classname})# Local IP found ... {0}".format(self.MyLocalIP,classname=self.ClassName))
					break
			
			if self.MyLocalIP == "":
				self.Logger.Log("({classname})# ERROR - Local IP not found".format(classname=self.ClassName))

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
			
			self.SetNodeUUID(self.UUID)
			self.SetNodeType(self.Type)
			self.SetNodeName(self.Name)
			self.SetGatewayIPAddress(self.GatewayIP)
			self.BasicProtocol.SetKey(self.Key)
		except Exception as e:
			self.Logger.Log("({classname})# ERROR - Wrong configuration format\n(EXEPTION)# {error}".format(error=str(e),classname=self.ClassName))
			self.Exit("ERROR - Wrong configuration format")
			return False
		
		print("# TODO - Do we need this DeviceInfo?")
		self.DeviceInfo = MkSDevice.Device(self.UUID, self.Type, self.OSType, self.OSVersion, self.BrandName)
		return True
	
	def InitiateLocalServer(self, port):
		if self.IsLocalUIEnabled is True:
			self.UI 			= MkSLocalWebServer.WebInterface("Context", port)
			self.LocalWebPort	= port
			# Data for the pages.
			jsonUIData 	= {
				'ip': str(self.MyLocalIP),
				'port': str(port),
				'uuid': str(self.UUID)
			}
			data = json.dumps(jsonUIData)
			# UI Pages
			self.UI.AddEndpoint("/", 			"index", 		None, 		data)
			self.UI.AddEndpoint("/nodes", 		"nodes", 		None, 		data)
			self.UI.AddEndpoint("/config", 		"config", 		None, 		data)
			self.UI.AddEndpoint("/app", 		"app", 			None, 		data)
			self.UI.AddEndpoint("/mobile", 		"mobile", 		None, 		data)
			self.UI.AddEndpoint("/mobile/app", 	"mobile/app", 	None, 		data)
			# UI RestAPI
			self.UI.AddEndpoint("/test/<key>", 						"test", 						self.TestWithKeyHandler)
			self.UI.AddEndpoint("/get/socket_list/<key>", 			"get_socket_list", 				self.GetConnectedSocketsListHandler)

	def AppendFaceRestTable(self, endpoint=None, endpoint_name=None, handler=None, args=None, method=['GET']):
		if self.IsLocalUIEnabled is True:
			self.UI.AddEndpoint(endpoint, endpoint_name, handler, args, method)

	def TryStartListener(self):
		try:
			self.Logger.Log("({classname})# Start listener...".format(classname=self.ClassName))
			self.ServerSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
			self.ServerSocket.setblocking(0)

			self.ServerSocket.bind(self.ServerAdderss)
			# [socket, ip_address, port]
			node = self.AppendConnection(self.ServerSocket, self.MyLocalIP, self.ServerAdderss[1])
			node.LocalType 	= "LISTENER"
			node.UUID 		= self.UUID
			node.Type 		= self.Type

			self.ServerSocket.listen(32)
			self.IsLocalSocketRunning = True

			if self.IsLocalUIEnabled is True:
				# Run preloader for UI interface
				if self.UI is None:
					self.Logger.Log("({classname})# Executing UI preloader (Only valid for local UI aka Webface)".format(classname=self.ClassName))
					self.PreUILoaderHandler()

			# Let know registered method about local server start.
			if self.OnLocalServerListenerStartedCallback is not None:
				self.OnLocalServerListenerStartedCallback(self.ServerSocket, self.MyLocalIP, self.ServerAdderss[1])

			# Run UI thread
			if self.IsLocalUIEnabled is True:
				if self.UI is None:
					self.Logger.Log("({classname})# Local UI(Webface) is not set ... (NULL)".format(classname=self.ClassName))
				else:
					self.Logger.Log("({classname})# Running local UI(Webface)".format(classname=self.ClassName))
					self.UI.Run()

			return True
		except Exception as e:
			self.RemoveConnectionBySock(self.ServerSocket)
			self.Logger.Log("({classname})# Failed to open listener, {0}\n[EXCEPTION] {1}".format(str(self.ServerAdderss[1]),e,classname=self.ClassName))
			return False
	
	def LocalWSDisconnectedHandler(self, ws_id):
		self.UnregisterLocalWS(ws_id)

	def LocalWSDataArrivedHandler(self, ws, data):
		# print("({classname})# (WS) {0}".format(data,classname=self.ClassName))
		try:
			packet 		= json.loads(data)
			if ("HANDSHAKE" == self.BasicProtocol.GetMessageTypeFromJson(packet)):
				return
			
			command 	= self.BasicProtocol.GetCommandFromJson(packet)
			direction 	= self.BasicProtocol.GetDirectionFromJson(packet)
			destination = self.BasicProtocol.GetDestinationFromJson(packet)
			source 		= self.BasicProtocol.GetSourceFromJson(packet)

			packet["additional"]["client_type"] = "local_ws"

			self.Logger.Log("({classname})# WS LOCAL [{direction}] {source} -> {dest} [{cmd}]".format(classname=self.ClassName,
						direction=direction,
						source=source,
						dest=destination,
						cmd=command))

			if direction in "request":
				if command in self.NodeRequestHandlers.keys():
					message = self.NodeRequestHandlers[command](ws, packet)
					ws.send(message)
				else:
					# This command belongs to the application level
					if self.OnApplicationRequestCallback is not None:
						message = self.OnApplicationRequestCallback(ws, packet)
						ws.send(message)
			elif direction in "response":
				if command in self.NodeResponseHandlers.keys():
					self.NodeResponseHandlers[command](ws, packet)
				else:
					# This command belongs to the application level
					if self.OnApplicationResponseCallback is not None:
						self.OnApplicationResponseCallback(ws, packet)
			else:
				pass
		except Exception as e:
			self.Logger.Log("({classname})# ERROR - [LocalWSDataArrivedHandler]\n(EXEPTION)# {error}\n{data}".format(error=str(e),data=data,classname=self.ClassName))

	def SetNodeUUID(self, uuid):
		self.UUID = uuid

	def SetNodeType(self, node_type):
		self.Type = node_type
	
	def SetNodeName(self, name):
		self.Name = name
	
	def SetGatewayIPAddress(self, ip):
		self.GatewayIP = ip
	
	def SetWebServiceStatus(self, is_enabled):
		self.IsNodeWSServiceEnabled = is_enabled

	def SetLocalServerStatus(self, is_enabled):
		self.IsNodeLocalServerEnabled = is_enabled
	
	def StartLocalNode(self):
		print("TODO - (MkSNode.Run) Missing management of network HW disconnection")
		thread.start_new_thread(self.NodeLocalNetworkConectionListener, ())
	
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

	def Run (self, callback):
		# Will be called each half a second.
		self.WorkingCallback = callback
		if self.IsLocalUIEnabled is True:
			# Import Local WebSocket objects
			from mksdk import MkSLocalWebServer
			from mksdk import MkSLocalWS
			self.LocalWSManager = MkSLocalWS.WSManager
			# Register callbacks
			self.LocalWSManager.OnDataArrivedEvent  = self.LocalWSDataArrivedHandler
			self.LocalWSManager.OnWSDisconnected 	= self.LocalWSDisconnectedHandler
		self.ExitEvent.clear()
		self.ExitLocalServerEvent.clear()

		# Read sytem configuration
		if (self.LoadSystemConfig() is False):
			print("({classname})# Load system configuration ... FAILED".format(classname=self.ClassName))
			return
		
		self.Logger.Log("({classname})# System configuration loaded".format(classname=self.ClassName))
		self.SetState("INIT")

		# Start local node dervice thread
		if self.IsNodeLocalServerEnabled is True:
			self.StartLocalNode()

		# Waiting here till SIGNAL from OS will come.
		while self.IsMainNodeRunnig:
			# State machine management
			self.Method = self.States[self.State]
			self.Method()

			# User callback
			if ("WORKING" == self.GetState() and self.SystemLoaded is True):
				#TODO - Services section must be in differebt thread
				self.ServicesManager()
				self.WorkingCallback()
				if self.IsLocalUIEnabled is True:
					# This check is for client nodes
					if (self.Type not in [1, 2]):
						if self.LocalWSManager is not None:
							if self.LocalWSManager.IsServerRunnig() is False and self.LocalMasterConnection is None:
								self.Logger.Log("({classname})# Exiting main thread ... ({0}, {1}) ...".format(self.LocalWSManager.IsServerRunnig(), self.LocalMasterConnection.Socket, classname=self.ClassName))
								self.Exit("Exiting main thread")

			self.Ticker += 1
			time.sleep(0.5)
		
		self.Logger.Log("({classname})# Start Exiting Node ...".format(classname=self.ClassName))
		# self.ExitEvent.set()
		if self.IsNodeWSServiceEnabled is True:
			if self.Network is not None:
				self.Network.Disconnect()

		if self.IsHardwareBased is True:
			self.Connector.Disconnect()
		
		# TODO - Don't think we need this event.
		# self.ExitEvent.wait()
		if self.IsListenerEnabled is True:
			self.ExitLocalServerEvent.wait()
	
	def Stop (self, reason):
		self.Logger.Log("({classname})# Stop Node ... ({0})".format(reason,classname=self.ClassName))
		self.IsMainNodeRunnig 		= False
		self.IsLocalSocketRunning 	= False
	
	def Pause (self):
		pass
	
	def Exit (self, reason):
		self.Stop(reason)
