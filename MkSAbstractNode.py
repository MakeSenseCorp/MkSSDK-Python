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
import hashlib
import xml.etree.ElementTree as ET
import random

import MkSGlobals
from mksdk import MkSFile
from mksdk import MkSUtils
from mksdk import MkSBasicNetworkProtocol
from mksdk import MkSSecurity
from mksdk import MkSLocalSocketMngr
from mksdk import MkSStreamSocket

from collections import OrderedDict
from geventwebsocket import WebSocketServer, WebSocketApplication, Resource

class MkSLocalWebsocketServer():
	def __init__(self):
		self.ClassName 				= "MkSLocalWebsocketServer"
		self.ApplicationSockets 	= {}
		self.ServerRunning 			= False
		# Events
		self.OnWSConnected 			= None
		self.OnDataArrivedEvent 	= None
		self.OnWSDisconnected 		= None
		self.OnSessionsEmpty 		= None
		self.Port 					= 0
	
	def RegisterCallbacks(self, connected, data, disconnect, empty):
		print ("({classname})# [RegisterCallbacks]".format(classname=self.ClassName))
		self.OnWSConnected		= connected
		self.OnDataArrivedEvent = data
		self.OnWSDisconnected 	= disconnect
		self.OnSessionsEmpty 	= empty

	def SetPort(self, port):
		self.Port = port
	
	def AppendSocket(self, ws_id, ws):
		print ("({classname})# [LOCAL WS] Append ({0})".format(ws_id, classname=self.ClassName))
		self.ApplicationSockets[ws_id] = ws
		if self.OnWSConnected is not None:
			self.OnWSConnected(ws_id)
	
	def RemoveSocket(self, ws_id):
		print ("({classname})# [LOCAL WS] Remove ({0})".format(ws_id, classname=self.ClassName))
		del self.ApplicationSockets[ws_id]
		if self.OnWSDisconnected is not None:
			self.OnWSDisconnected(ws_id)
		if len(self.ApplicationSockets) == 0:
			if self.OnSessionsEmpty is not None:
				self.OnSessionsEmpty()
	
	def WSDataArrived(self, ws, data):
		# TODO - Append webface type
		packet = json.loads(data)
		if ("HANDSHAKE" == packet['header']['message_type']):
			return
		
		packet["additional"]["ws_id"] 	= id(ws)
		packet["additional"]["pipe"]  	= "LOCAL_WS"
		packet["stamping"] 				= ['local_ws']

		# print ("({classname})# [WSDataArrived] {0} {1} {2}".format(id(ws),packet,self.OnDataArrivedEvent,classname=self.ClassName))
		if self.OnDataArrivedEvent is not None:
			self.OnDataArrivedEvent(ws, packet)
	
	def Send(self, ws_id, data):
		if ws_id in self.ApplicationSockets:
			self.ApplicationSockets[ws_id].send(data)
		else:
			print ("({classname})# ERROR - This socket ({0}) does not exist. (Might be closed)".format(ws_id, classname=self.ClassName))
	
	def EmitEvent(self, data):
		for key in self.ApplicationSockets:
			self.ApplicationSockets[key].send(data)
	
	def IsServerRunnig(self):
		return self.ServerRunning

	def Worker(self):
		try:
			server = WebSocketServer(('', self.Port), Resource(OrderedDict([('/', NodeWSApplication)])))

			self.ServerRunning = True
			print ("({classname})# Staring local WS server ... {0}".format(self.Port, classname=self.ClassName))
			server.serve_forever()
		except Exception as e:
			print ("({classname})# [ERROR] Stoping local WS server ... {0}".format(str(e), classname=self.ClassName))
			self.ServerRunning = False
	
	def RunServer(self):
		if self.ServerRunning is False:
			thread.start_new_thread(self.Worker, ())

WSManager = MkSLocalWebsocketServer()

class NodeWSApplication(WebSocketApplication):
	def __init__(self, *args, **kwargs):
		self.ClassName = "NodeWSApplication"
		super(NodeWSApplication, self).__init__(*args, **kwargs)
	
	def on_open(self):
		print ("({classname})# [LOCAL WS] CONNECTION OPENED".format(classname=self.ClassName))
		WSManager.AppendSocket(id(self.ws), self.ws)

	def on_message(self, message):
		# print ("({classname})# MESSAGE RECIEVED {0} {1}".format(id(self.ws),message,classname=self.ClassName))
		if message is not None:
			WSManager.WSDataArrived(self.ws, message)
		else:
			print ("({classname})# ERROR - Message is not valid".format(classname=self.ClassName))

	def on_close(self, reason):
		print ("({classname})# [LOCAL WS] CONNECTION CLOSED".format(classname=self.ClassName))
		WSManager.RemoveSocket(id(self.ws))

class AbstractNode():
	def __init__(self):
		self.ClassName								= ""
		self.File 									= MkSFile.File()
		self.SocketServer							= MkSLocalSocketMngr.Manager()
		self.Network								= None
		self.MKSPath								= ""
		self.HostName								= socket.gethostname()
		self.StreamSocksMngr 						= MkSStreamSocket.MkSStreamManager(self)
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
		self.IsLocalSockInUse						= False
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
		self.OnStreamSocketCreatedEvent				= None
		self.OnStreamSocketDataEvent				= None
		self.OnStreamSocketDisconnectedEvent 		= None
		# Registered items
		self.OnDeviceChangeList						= [] # Register command "register_on_node_change"
		# Synchronization
		self.DeviceChangeListLock 					= threading.Lock()
		# Services
		#self.IPScannerServiceUUID					= None
		#self.EMailServiceUUID						= None
		#self.SMSServiceUUID						= None
		self.Services 								= {}
		self.NetworkOnlineDevicesList 				= []
		# Timers
		self.ServiceSearchTS						= time.time()
		## Unused
		self.DeviceConnectedCallback 				= None
		# Initialization methods
		self.MyPID 									= os.getpid()
		self.MyLocalIP 								= "N/A"
		self.NetworkCards 							= MkSUtils.GetIPList()
		# Network
		#self.MasterSocket							= None
		self.LocalMasterConnection					= None
		# Handlers
		self.NodeRequestHandlers					= {
			'get_node_info': 						self.GetNodeInfoRequestHandler,
			'get_node_status': 						self.GetNodeStatusRequestHandler,
			'get_file': 							self.GetFileRequestHandler,
			'get_resource':							self.GetResourceRequestHandler,
			'register_on_node_change':				self.RegisterOnNodeChangeRequestHandler,
			'unregister_on_node_change':			self.UnregisterOnNodeChangeRequestHandler,
			'find_node':							self.FindNodeRequestHandler,
			'master_append_node':					self.MasterAppendNodeRequestHandler,
			'master_remove_node':					self.MasterRemoveNodeRequestHandler,
			'close_local_socket':					self.CloseLocalSocketRequestHandler,
			'open_stream_socket':					self.OpenStreamSocketRequestHandler,
		}
		self.NodeResponseHandlers					= {
			'get_node_info': 						self.GetNodeInfoResponseHandler,
			'get_node_status': 						self.GetNodeStatusResponseHandler,
			'find_node': 							self.FindNodeResponseHandler,
			'master_append_node':					self.MasterAppendNodeResponseHandler,
			'master_remove_node':					self.MasterRemoveNodeResponseHandler,
			'get_online_devices':					self.GetOnlineDevicesResponseHandler,
			'register_on_node_change':				self.RegisterOnNodeChangeResponseHandler,
			'unregister_on_node_change':			self.UnregisterOnNodeChangeResponseHandler,
			'open_stream_socket':					self.OpenStreamSocketResponseHandler,
		}
		self.NodeFilterCommands 					= [
			'on_node_change'
		]
		# LocalFace UI
		self.UI 									= None
		self.LocalWebPort							= ""
		self.BasicProtocol 							= None
		print(self.NetworkCards)

		self.Services[101] = {
			'uuid': "",
			'name': "SMS",
			'enabled': 0,
			'registered': 0
		}
		self.Services[102] = {
			'uuid': "",
			'name': "eMail",
			'enabled': 0,
			'registered': 0
		}
		self.Services[103] = {
			'uuid': "",
			'name': "IP Scanner",
			'enabled': 0,
			'registered': 0
		}
		# FS Area
		self.UITypes = {
			'config': 		'config',
			'app': 			'app',
			'thumbnail': 	'thumbnail'
		}

		parser = argparse.ArgumentParser(description='Execution module called Node')
		parser.add_argument('--path', action='store', dest='pwd', help='Root folder of a Node')
		parser.add_argument('--type', action='store', dest='type', help='Type of node')
		args = parser.parse_args()

		if args.pwd is not None:
			os.chdir(args.pwd)
		
		if args.type is not None:
			pass
		
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

	# Overwrite
	def RegisterOnNodeChangeResponseHandler(self, sock, packet):
		self.LogMSG("({classname})# [RegisterOnNodeChangeResponseHandler]".format(classname=self.ClassName),5)
	
	# Overload
	def LocalSocketDataInputExternalHandler(self, conn, packet, raw_data):
		pass

	def LocalWebsockConnectedHandler(self, ws_id):
		self.LogMSG("({classname})# [LocalWebsockConnectedHandler] {0}".format(ws_id,classname=self.ClassName),5)
		self.IsLocalSockInUse = True

	def LocalWebsockDataArrivedHandler(self, ws, packet):
		messageType = self.BasicProtocol.GetMessageTypeFromJson(packet)
		direction 	= self.BasicProtocol.GetDirectionFromJson(packet)
		destination = self.BasicProtocol.GetDestinationFromJson(packet)
		source 		= self.BasicProtocol.GetSourceFromJson(packet)
		command 	= self.BasicProtocol.GetCommandFromJson(packet)

		#packet["additional"]["client_type"] = "global_ws"
		self.LogMSG("({classname})# LocalWebsock [{direction}] {source} -> {dest} [{cmd}]".format(
					classname=self.ClassName,
					direction=direction,
					source=source,
					dest=destination,
					cmd=command),5)
		
		if messageType == "BROADCAST":
			pass
	
		if destination in source:
			return
		
		if destination in self.UUID:
			if messageType == "CUSTOM":
				pass
			elif messageType in ["DIRECT", "PRIVATE", "WEBFACE"]:
				if command in self.NodeRequestHandlers.keys():
					message = self.NodeRequestHandlers[command](None, packet)
					WSManager.Send(id(ws),message)
				else:
					# This command belongs to the application level
					if self.OnApplicationRequestCallback is not None:
						try:
							message = self.OnApplicationRequestCallback(None, packet)
							if message == "" or message is None:
								return
							
							WSManager.Send(id(ws),message)
						except Exception as e:
							self.LogException("[DataSocketInputHandler #2]",e,3)
			else:
				self.LogMSG("({classname})# [Websocket INBOUND] ERROR - Not support {0} request type.".format(messageType, classname=self.ClassName),4)
		else:
			pass

	def LocalWebsockDisconnectedHandler(self, ws_id):
		self.LogMSG("({classname})# [LocalWebsockDisconnectedHandler] {0}".format(ws_id,classname=self.ClassName),5)
	
	def LocalWebsockSessionsEmpty(self):
		self.LogMSG("({classname})# [LocalWebsockSessionsEmpty]".format(classname=self.ClassName),5)
		self.IsLocalSockInUse = False
	
	def EmitEventViaLocalWebsocket(self, data):
		WSManager.EmitEvent(data)
	
	def StartLocalWebsocketServer(self, port):
		self.LogMSG("({classname})# [LocalWebsockDStartLocalWebsocketServerisconnectedHandler] {0}".format(port,classname=self.ClassName),5)
		WSManager.SetPort(port)
		WSManager.RunServer()

	''' 
		Description:	Connect node (MASTER) over socket, add connection to connections list
						and add node to masters list.
		Return: 		Status (True/False).
	'''
	def ConnectMaster(self, ip):
		connection, status = self.SocketServer.Connect(ip, 16999, "SERVER")
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
		return self.SocketServer.Connect(ip, port, "SOCK")

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
		Description: 	Get local node by IP and Port.
		Return: 		SocketConnection.
	'''	
	def GetNode(self, ip, port):
		return self.SocketServer.GetConnection(ip, port)

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
						if destination in self.UUID or (destination in "MASTER" and 1 == self.Type) or (broadcast is True and "BROADCAST" in destination):
							if direction in "request":
								if command in self.NodeRequestHandlers.keys():
									try:
										handler = self.NodeRequestHandlers[command]
										if handler is not None:
											# Execute framework layer
											message = handler(sock, packet)
											# This handler migth be also in application layer.
											if command in self.NodeFilterCommands:
												if self.OnApplicationRequestCallback is not None:
													# Execute application layer
													message = self.OnApplicationRequestCallback(sock, packet)
											
											# In any case response messgae is empty, don't send response
											if message == "" or message is None:
												return

											# Create response and send back to requestor
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
								# Send to all other
								if broadcast is True:
									self.LocalSocketDataInputExternalHandler(connection, json.loads(raw_data), raw_data)
							elif direction in "response":
								if command in self.NodeResponseHandlers.keys():
									try:
										handler = self.NodeResponseHandlers[command](sock, packet)
										if handler is not None:
											# Execute framework layer
											handler(sock, packet)
											# This handler migth be also in application layer.
											if command in self.NodeFilterCommands:
												if self.OnApplicationRequestCallback is not None:
													# Execute application layer
													self.OnApplicationRequestCallback(sock, packet)
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
							self.LocalSocketDataInputExternalHandler(connection, packet, raw_data)
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
		# Remove from registration list
		# self.RemoveDeviceChangeListNode(connection.Obj["uuid"])
		self.UnregisterItem({
			'item_type': 1,
			'uuid':	connection.Obj["uuid"]
		})
		# Raise event for user
		try:
			if self.OnTerminateConnectionCallback is not None:
				self.OnTerminateConnectionCallback(connection)
		except Exception as e:
			self.LogException("[NodeDisconnectedHandler]",e,3)
		
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
	
	def SearchNodes(self, index):
		self.SendRequest("BROADCAST", "BROADCAST", "operations", {
			"index": 	 index,
			"subindex":	 0x0,
			"direction": 0x1,
			"data": { }
		}, {})

	''' 
		Description: 	Request to open private stream socket to other node [RESPONSE]
		Return: 		None
	'''	
	def OpenStreamSocketRequestHandler(self, sock, packet):
		self.LogMSG("({classname})# [OpenStreamSocketRequestHandler]".format(classname=self.ClassName),5)
		payload = self.BasicProtocol.GetPayloadFromJson(packet)

		if self.OnStreamSocketCreatedEvent is None or self.OnStreamSocketDataEvent is None or self.OnStreamSocketDisconnectedEvent is None:
			return self.BasicProtocol.BuildResponse(packet, { 
				'ip': "",
				'uuid': "",
				'port': 0,
				'ts': 0,
				'status': "NOTSUPPORTED"
			})
		identity = payload["ts"]
		uuid 	 = payload["uuid"]
		ip 	 	 = payload["ip"]

		self.StreamSocksMngr.CreateStream(identity, "server_{0}".format(identity), True)
		self.StreamSocksMngr.RegisterCallbacks(identity, self.OnStreamSocketCreatedEvent, self.OnStreamSocketDataEvent, self.OnStreamSocketDisconnectedEvent)
		stream = self.StreamSocksMngr.GetStream(identity)
		stream.UUID 	= uuid
		stream.ClientIP = ip
		self.StreamSocksMngr.UpdateStream(identity, stream)
		stream.SetServerIP(self.MyLocalIP)
		stream.Listen()

		# Update application layer about stream creation
		if self.OnStreamSocketCreatedEvent is not None:
			self.OnStreamSocketCreatedEvent(stream.Name, identity)
		payload = { 
			'ip': self.MyLocalIP,
			'uuid': self.UUID,
			'port': stream.GetPort(),
			'ts': identity,
			'status': "CREATED"
		}

		return self.BasicProtocol.BuildResponse(packet, payload)
	
	''' 
		Description: 	Requestor for stream private socket get reaponse with status and port [RESPONSE]
		Return: 		None
	'''	
	def OpenStreamSocketResponseHandler(self, sock, packet):
		self.LogMSG("({classname})# [OpenStreamSocketResponseHandler]".format(classname=self.ClassName),5)
		payload = self.BasicProtocol.GetPayloadFromJson(packet)

		ip 			 = payload["ip"]
		port 		 = payload["port"]
		identity 	 = payload["ts"]
		uuid 		 = payload["uuid"]

		stream = self.GetStream(identity)
		stream.SetPort(port)
		stream.SetServerIP(ip)
		stream.Connect()

		# Update application layer about stream creation
		if self.OnStreamSocketCreatedEvent is not None:
			self.OnStreamSocketCreatedEvent(stream.Name, identity)

	''' 
		Description:	Connect node over socket (private stream use), add connection to connections list.
		Return: 		Connection and status
	'''
	def ConnectStream(self, uuid, name):
		# Generate timestamp
		random.seed(time.time())
		identity = int((random.random() * 10000000))
		# Send MKS packet with "open_stream_socket" request with ts
		self.SendRequestToNode(uuid, "open_stream_socket", {
			'ts': identity,
			'uuid': uuid,
			'ip': self.MyLocalIP
		})
		# Create client stream
		self.StreamSocksMngr.CreateStream(identity, name, False)
		self.StreamSocksMngr.RegisterCallbacks(identity, self.OnStreamSocketCreatedEvent, self.OnStreamSocketDataEvent, self.OnStreamSocketDisconnectedEvent)
		self.LogMSG("({classname})# [ConnectStream] {0}".format(identity,classname=self.ClassName),5)
		# Return to app level with identification stream
		return identity
	
	''' 
		Description:	Send data over stream
		Return: 		None
	'''
	def SendStream(self, identity, data):
		stream = self.GetStream(identity)
		if stream is not None:
			if stream.GetState() in ["CONNECT","LISTEN"]:
				stream.Send(data)
		else:
			self.LogMSG("({classname})# STREAM IS NONE".format(classname=self.ClassName),5)
		
	''' 
		Description:	Return created stream.
		Return: 		Stream
	'''
	def GetStream(self, identity):
		return self.StreamSocksMngr.GetStream(identity)
	
	''' 
		Description:	Disconnect stream.
		Return: 		None
	'''
	def DisconnectStream(self, identity):
		pass

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
	
	''' 
		Description: 	This is basicaly event for slave node - When master append a new node 
						connection after providing port to new conneceted node. [RESPONSE]
		Return: 		None
	'''	
	def MasterAppendNodeResponseHandler(self, sock, packet):
		self.LogMSG("({classname})# [MasterAppendNodeResponseHandler]".format(classname=self.ClassName),5)
		payload 	= self.BasicProtocol.GetPayloadFromJson(packet)
		additional 	= self.BasicProtocol.GetAdditionalFromJson(packet)

		additional["online"] = True
		packet = self.BasicProtocol.SetAdditional(packet, additional)

		if payload["tagging"]["cat_1"] == "service":
			self.Services[payload["type"]]["uuid"] 		= payload["uuid"]
			self.Services[payload["type"]]["enabled"] 	= 1

	''' 
		Description: 	This is basicaly event for slave node - When master remove a node
						connection after upon its disconnection. [RESPONSE]
		Return: 		None
	'''	
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

	''' 
		Description: 	N/A
		Return: 		N/A
	'''	
	def UnRegisterOnNodeChangeEvent(self, uuid):
		self.LogMSG("({classname})# [UnRegisterOnNodeChangeEvent] {0}".format(uuid,classname=self.ClassName),5)
		self.SendRequestToNode(uuid, "unregister_on_node_change", {
			'item_type': 1,
			'uuid':	self.UUID
		})

	''' 
		Description: 	Register change event on othr node from this node
		Return: 		N/A
	'''	
	def RegisterOnNodeChangeEvent(self, uuid):
		self.LogMSG("({classname})# [RegisterOnNodeChangeEvent] {0}".format(uuid,classname=self.ClassName),5)
		self.SendRequestToNode(uuid, "register_on_node_change", {
			'item_type': 1,
			'uuid':	self.UUID
		})
	
	''' 
		Description: 	N/A
		Return: 		N/A
	'''	
	def RegisterItem(self, payload):
		self.DeviceChangeListLock.acquire()
		try:
			key = hashlib.md5("{0}".format(json.dumps(payload))).hexdigest()
			# Chek if this devicealready registered
			for item in self.OnDeviceChangeList:
				if key == item["key"]:
					self.DeviceChangeListLock.release()
					return False
			self.LogMSG("({classname})# [RegisterItem] {0} {1}".format(key, payload,classname=self.ClassName),5)
			# Append new registertion item
			self.OnDeviceChangeList.append({
				'ts':		time.time(),
				'payload':	payload,
				'type': 	payload["item_type"],
				'key':		key
			})
		except Exception as e:
			self.LogException("[RegisterItem]",e,3)
		self.DeviceChangeListLock.release()
		return True

	''' 
		Description: 	N/A
		Return: 		N/A
	'''		
	def UnregisterItem(self, payload):
		self.DeviceChangeListLock.acquire()
		try:
			key = hashlib.md5("{0}".format(json.dumps(payload))).hexdigest()
			# Chek if this devicealready registered
			for item in self.OnDeviceChangeList:
				self.LogMSG("({classname})# [UnregisterItem] [{0} {1}] ? [{2} {3}]".format(key,payload,item["key"],item["payload"],classname=self.ClassName),5)
				if key == item["key"]:
					self.LogMSG("({classname})# [UnregisterItem] {0}".format(payload,classname=self.ClassName),5)
					# Remove new registertion item
					self.OnDeviceChangeList.remove(item)
					self.DeviceChangeListLock.release()
					return True
		except Exception as e:
			self.LogException("[RegisterItem]",e,3)
		self.DeviceChangeListLock.release()
		return False

	''' 
		Description: 	N/A
		Return: 		N/A
	'''		
	def RegisterOnNodeChangeRequestHandler(self, sock, packet):
		self.LogMSG("({classname})# [RegisterOnNodeChangeRequestHandler]".format(classname=self.ClassName),5)
		payload 	= self.BasicProtocol.GetPayloadFromJson(packet)
		item_type 	= payload["item_type"]

		# Webface
		if item_type in [2,3]:
			pipe = packet["additional"]["pipe"]
			payload["pipe"] = pipe
			if pipe == "GATEWAY":
				piggy = self.BasicProtocol.GetPiggybagFromJson(packet)
				payload["webface_indexer"] = piggy["webface_indexer"]
			elif pipe == "LOCAL_WS":
				payload["ws_id"] = packet["additional"]["ws_id"]
		
		if self.RegisterItem(payload) is True:
			return self.BasicProtocol.BuildResponse(packet, {
				'registered': "OK",
				'type': self.Type
			})
		else:
			return self.BasicProtocol.BuildResponse(packet, {
				'registered': "FAILED"
			})

	''' 
		Description: 	N/A
		Return: 		N/A
	'''		
	def UnregisterOnNodeChangeRequestHandler(self, sock, packet):
		self.LogMSG("({classname})# [UnregisterOnNodeChangeRequestHandler] {0}".format(packet,classname=self.ClassName),5)
		payload 	= self.BasicProtocol.GetPayloadFromJson(packet)
		item_type 	= payload["item_type"]

		# Webface
		if item_type in [2,3]:
			pipe = packet["additional"]["pipe"]
			payload["pipe"] = pipe
			if pipe == "GATEWAY":
				piggy = self.BasicProtocol.GetPiggybagFromJson(packet)
				payload["webface_indexer"] = piggy["webface_indexer"]
			elif pipe == "LOCAL_WS":
				payload["ws_id"] = packet["additional"]["ws_id"]
		
		if self.UnregisterItem(payload) is True:
			return self.BasicProtocol.BuildResponse(packet, {
				'unregistered': "OK"
			})
		else:
			return self.BasicProtocol.BuildResponse(packet, {
				'unregistered': "FAILED"
			})

	''' 
		Description: 	N/A
		Return: 		N/A
	'''		
	def UnregisterOnNodeChangeResponseHandler(self, sock, packet):
		self.LogMSG("({classname})# [UnregisterOnNodeChangeResponseHandler]".format(classname=self.ClassName),5)

	def GetResourceRequestHandler(self, sock, packet):
		self.LogMSG("({classname})# [GetResourceRequestHandler]".format(classname=self.ClassName),6)
		objFile = MkSFile.File()
		payload = self.BasicProtocol.GetPayloadFromJson(packet)
		
		if "machine_type" not in payload:
			machine_type = "pc"
		else:
			machine_type = payload["machine_type"]

		tag_id  = payload["id"]
		src     = payload["src"]
		tag     = payload["tag"]
		ui_type = payload["ui_type"]
		path 	= os.path.join(".","ui",machine_type,self.UITypes[ui_type],src)
		self.LogMSG("({classname})# [GetResourceRequestHandler] {0}".format(path, classname=self.ClassName),6)
		content = objFile.Load(path)

		if tag == "img":
			content = "data:image/jpeg;base64," + content.encode('base64')

		return self.BasicProtocol.BuildResponse(packet, {
								'id': tag_id,
								'tag': tag,
								'src': src,
								'content': content.encode('hex')
		})

	''' 
		Description: 	Get file handler [REQUEST]
		Return: 		N/A
	'''	
	def GetFileRequestHandler(self, sock, packet):
		objFile 		= MkSFile.File()
		payload 		= self.BasicProtocol.GetPayloadFromJson(packet)
		uiType 			= payload["ui_type"] # Base UI type
		fileType 		= payload["file_type"]
		fileName 		= payload["file_name"]
		client_type 	= packet["additional"]["client_type"]
		stamping 		= packet["stamping"]
		# TODO - Node should get type of machine the node ui running on.
		
		if "machine_type" not in payload:
			machine_type = "pc"
		else:
			machine_type = payload["machine_type"]

		path 	= os.path.join(".","ui",machine_type,self.UITypes[uiType],"ui." + fileType)
		content = objFile.Load(path)
		
		if ("html" in fileType):
			# Create resource section (load script, img,... via mks API)
			resources = ""
			html_rows = content.split("\n")
			for row in html_rows:
				if 'data-obj="mks"' in row:
					xml = "<root>{0}</root>\n".format(row[:-1])
					DOM = ET.fromstring(xml)
					for element in DOM.iter():
						if element.get('data-obj') is not None:
							if element.get('data-obj') == "mks":
								if element.tag == "script":
									resources += "node.API.SendCustomCommand(NodeUUID, 'get_resource', { 'id':'', 'tag':'" + element.tag + "', 'src':'" + element.get('src') + "', 'ui_type': '" + uiType + "' }, function(res) { var payload = res.data.payload; MkSGlobal.ExecuteJS(MkSGlobal.ConvertHEXtoString(payload.content)); });"
								elif element.tag == "css":
									resources += "node.API.SendCustomCommand(NodeUUID, 'get_resource', { 'id':'', 'tag':'" + element.tag + "', 'src':'" + element.get('src') + "', 'ui_type': '" + uiType + "' }, function(res) { var payload = res.data.payload; MkSGlobal.AppendCSS(MkSGlobal.ConvertHEXtoString(payload.content)); });"
								elif element.tag == "img":
									tag_id = element.get('id')
									resources += "node.API.SendCustomCommand(NodeUUID, 'get_resource', { 'id':'" + tag_id + "', 'tag':'" + element.tag + "', 'src':'" + element.get('src') + "', 'ui_type': '" + uiType + "' }, function(res) { var payload = res.data.payload; document.getElementById(payload.id).src = MkSGlobal.ConvertHEXtoString(payload.content); });"
			
			# Append resource section
			content = content.replace("[RESOURCES]", resources)
			
			config = '''
				var GatewayIP 	= "[GATEWAY_IP]";
				var NodeUUID  	= "[NODE_UUID]";
				var LocalWSIP 	= "[LOCAL_WS_IP]";
				var LocalWSPORT = [LOCAL_WS_PORT];
			'''
			
			# Replace UUID
			config = config.replace("[NODE_UUID]", self.UUID)
			if stamping is None:
				self.LogMSG("({classname})# [ERROR] Missing STAMPING in packet ...".format(classname=self.ClassName),3)
				config = config.replace("[GATEWAY_IP]", self.GatewayIP)
			else:
				if "cloud_t" in stamping:
					# TODO - Cloud URL must be in config.json
					config = config.replace("[GATEWAY_IP]", "ec2-54-188-199-33.us-west-2.compute.amazonaws.com")
				else:
					config = config.replace("[GATEWAY_IP]", self.GatewayIP)
			# Configure local websocket
			config = config.replace("[LOCAL_WS_IP]", self.MyLocalIP)
			config = config.replace("[LOCAL_WS_PORT]", str(WSManager.Port))

			self.LogMSG("({classname})# Config: {0}".format(config,classname=self.ClassName),5)

			content = content.replace("[CONFIGURATION]", config)
			
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
			
			self.BasicProtocol = MkSBasicNetworkProtocol.BasicNetworkProtocol(self.UUID)
			self.BasicProtocol.SetKey(self.Key)
			WSManager.RegisterCallbacks(self.LocalWebsockConnectedHandler, self.LocalWebsockDataArrivedHandler, self.LocalWebsockDisconnectedHandler, self.LocalWebsockSessionsEmpty)
			# Start Websocket Server
			if self.IsMaster is True:
				self.StartLocalWebsocketServer(1999)
			
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
			if self.SocketServer.GetListenerStatus() is True:
				self.SocketServer.Stop()
				self.ExitLocalServerEvent.wait()
		
		# TODO - Let user know about closing app
	
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
