#!/usr/bin/python

'''
			This is a Master Node (inherites AbstractNode)
				1. Handle Websocket connection to Gateway.
				2. Managing local client sockets.
				3. Port "DHCP like" manager.
				4. Etc...
			
			Author
				Name:	Yevgeniy Kiveisha
				E-Mail:	yevgeniy.kiveisha@gmail.com

'''

import os
import sys
import json
import time
import threading
import socket
import Queue
#from flask import Flask, render_template, jsonify, Response, request

if sys.version_info[0] < 3:
	import thread
else:
	import _thread

import MkSGlobals
from mksdk import MkSFile
from mksdk import MkSNetMachine
from mksdk import MkSAbstractNode
from mksdk import MkSShellExecutor
from mksdk import MkSLogger

class MasterNode(MkSAbstractNode.AbstractNode):
	def __init__(self):
		MkSAbstractNode.AbstractNode.__init__(self)
		self.ClassName 							= "Master Node"
		# Members
		self.PortsForClients					= [item for item in range(1,33)]
		self.MasterVersion						= "1.0.1"
		self.InstalledNodes 					= []
		self.IsMaster 							= True
		self.IsLocalUIEnabled					= False
		# Debug & Logging
		self.DebugMode							= True
		# Node connection to WS information
		self.GatewayIP 							= ""
		self.ApiPort 							= "8080"
		self.WsPort 							= "1981"
		self.ApiUrl 							= ""
		self.WsUrl								= ""
		self.UserName 							= ""
		self.Password 							= ""
		# Locks and Events
		self.NetworkAccessTickLock 				= threading.Lock()
		# Sates
		self.States 							= {
			'IDLE': 							self.State_Idle,
			'INIT':								self.State_Init,
			'INIT_GATEWAY':						self.State_InitGateway,
			'ACCESS_GATEWAY': 					self.State_AccessGetway,
			'ACCESS_WAIT_GATEWAY':				self.State_AccessWaitGatway,
			'INIT_LOCAL_SERVER':				self.State_InitLocalServer,
			'WORKING': 							self.State_Work
		}
		# Handlers
		self.NodeRequestHandlers['get_port'] 		= self.GetPortRequestHandler
		self.NodeRequestHandlers['get_local_nodes'] = self.GetLocalNodesRequestHandler
		# Callbacks
		self.GatewayDataArrivedCallback 		= None
		self.GatewayConnectedCallback 			= None
		self.GatewayConnectionClosedCallback 	= None
		self.OnCustomCommandRequestCallback		= None
		self.OnCustomCommandResponseCallback	= None
		# Flags
		self.IsListenerEnabled 					= False
		self.PipeStdoutRun						= False
	
	''' 
		Description: 	N/A
		Return: 		N/A
	'''	
	def EnableLogs(self, name):
		self.Logger = MkSLogger.Logger(name)
		self.Logger.EnablePrint()
		self.Logger.EnableLogger()

	''' 
		Description: 	State [IDLE]
		Return: 		None
	'''	
	def State_Idle (self):
		self.LogMSG("({classname})# Note, in IDLE state ...".format(classname=self.ClassName))
		time.sleep(1)

	''' 
		Description: 	State [INIT]
		Return: 		None
	'''	
	def State_Init (self):
		self.SetState("INIT_LOCAL_SERVER")

	''' 
		Description: 	State [INIT_GATEWAY]
		Return: 		None
	'''	
	def State_InitGateway(self):
		if self.IsNodeWSServiceEnabled is True:
			# Create Network instance
			self.Network = MkSNetMachine.Network(self.ApiUrl, self.WsUrl)
			self.Network.SetLogger(self.Logger)
			self.Network.SetDeviceType(self.Type)
			self.Network.SetDeviceUUID(self.UUID)
			# Register to events
			self.Network.OnConnectionCallback  		= self.WebSocketConnectedCallback
			self.Network.OnDataArrivedCallback 		= self.WebSocketDataArrivedCallback
			self.Network.OnConnectionClosedCallback = self.WebSocketConnectionClosedCallback
			self.Network.OnErrorCallback 			= self.WebSocketErrorCallback
			self.AccessTick = 0

			self.SetState("ACCESS_GATEWAY")
		else:
			if self.IsNodeLocalServerEnabled is True:
				self.SetState("INIT_LOCAL_SERVER")
			else:
				self.SetState("WORKING")

	''' 
		Description: 	State [ACCESS_GATEWAY]
		Return: 		None
	'''	
	def State_AccessGetway (self):
		if self.IsNodeWSServiceEnabled is True:
			self.Network.AccessGateway(self.Key, json.dumps({
				'node_name': str(self.Name),
				'node_type': self.Type
			}))

			self.SetState("ACCESS_WAIT_GATEWAY")
		else:
			self.SetState("WORKING")

	''' 
		Description: 	State [ACCESS_WAIT_GATEWAY]
		Return: 		None
	'''		
	def State_AccessWaitGatway (self):
		if self.AccessTick > 10:
			self.SetState("ACCESS_WAIT_GATEWAY")
			self.AccessTick = 0
		else:
			self.AccessTick += 1

	''' 
		Description: 	State [INIT_LOCAL_SERVER]
		Return: 		None
	'''	
	def State_InitLocalServer(self):
		self.SocketServer.EnableListener(16999)
		self.SocketServer.Start()
		if self.SocketServer.GetListenerStatus() is True:
			self.SetState("INIT_GATEWAY")
		time.sleep(1)

	''' 
		Description: 	State [WORKING]
		Return: 		None
	'''	
	def State_Work (self):
		if self.SystemLoaded is False:
			self.SystemLoaded = True # Update node that system done loading.
			if self.NodeSystemLoadedCallback is not None:
				self.NodeSystemLoadedCallback()
			
		if 0 == self.Ticker % 60:
			self.SendGatewayPing()
	
	''' 
		Description: 	N/A
		Return: 		N/A
	'''	
	def WebSocketConnectedCallback (self):
		self.SetState("WORKING")
		self.GatewayConnectedEvent()
		if self.GatewayConnectedCallback is not None:
			self.GatewayConnectedCallback()

	''' 
		Description: 	N/A
		Return: 		N/A
	'''		
	def WebSocketConnectionClosedCallback (self):
		if self.GatewayConnectionClosedCallback is not None:
			self.GatewayConnectionClosedCallback()
		self.NetworkAccessTickLock.acquire()
		self.AccessTick = 0
		self.NetworkAccessTickLock.release()
		self.SetState("ACCESS_GATEWAY")

	''' 
		Description: 	N/A
		Return: 		N/A
	'''	
	def WebSocketDataArrivedCallback (self, packet):
		try:
			# self.SetState("WORKING")
			messageType = self.BasicProtocol.GetMessageTypeFromJson(packet)
			direction 	= self.BasicProtocol.GetDirectionFromJson(packet)
			destination = self.BasicProtocol.GetDestinationFromJson(packet)
			source 		= self.BasicProtocol.GetSourceFromJson(packet)
			command 	= self.BasicProtocol.GetCommandFromJson(packet)

			packet["additional"]["client_type"] = "global_ws"
			self.LogMSG("({classname})# WS [{direction}] {source} -> {dest} [{cmd}]".format(
						classname=self.ClassName,
						direction=direction,
						source=source,
						dest=destination,
						cmd=command))
			
			if messageType == "BROADCAST":
				pass
		
			if destination in source:
				return

			# Is this packet for me?
			if destination in self.UUID:
				if messageType == "CUSTOM":
					return
				elif messageType in ["DIRECT", "PRIVATE", "WEBFACE"]:
					if command in self.NodeRequestHandlers.keys():
						message = self.NodeRequestHandlers[command](None, packet)
						self.SendPacketGateway(message)
					else:
						if self.GatewayDataArrivedCallback is not None:
							message = self.GatewayDataArrivedCallback(None, packet)
							self.SendPacketGateway(message)
				else:
					self.LogMSG("({classname})# [Websocket INBOUND] ERROR - Not support {0} request type.".format(messageType, classname=self.ClassName))
			else:
				self.LogMSG("(Master Node)# Not mine ... Sending to slave ... " + destination)
				# Find who has this destination adderes.
				self.HandleExternalRequest(packet)
		except Exception as e:
			self.LogMSG("({classname})# WebSocket Error - Data arrived issue\nPACKET#\n{0}\n(EXEPTION)# {error}".format(
				packet,
				classname=self.ClassName,
				error=str(e)))

	''' 
		Description: 	N/A
		Return: 		N/A
	'''	
	def WebSocketErrorCallback (self):
		self.LogMSG("(Master Node)# ERROR - Gateway socket error")
		# TODO - Send callback "OnWSError"
		self.NetworkAccessTickLock.acquire()
		self.AccessTick = 0
		self.NetworkAccessTickLock.release()
		self.SetState("ACCESS_WAIT_GATEWAY")
	
	''' 
		Description: 	Master as proxy server.
		Return: 		N/A
	'''	
	def HandleExternalRequest(self, packet):
		self.LogMSG("({classname})# External request (PROXY)".format(classname=self.ClassName))
		destination = self.BasicProtocol.GetDestinationFromJson(packet)
		conn 		= self.GetNodeByUUID(destination)
		
		if conn is not None:
			message = self.BasicProtocol.StringifyPacket(packet)
			message = self.BasicProtocol.AppendMagic(message)
			# Send via server (multithreaded and safe)
			conn.Socket.send(message)
		else:
			self.LogMSG("[MasterNode] HandleInternalReqest NODE NOT FOUND")
			# Need to look at other masters list.
			pass

	''' 
		Description: 	[HANDLERS]
		Return: 		N/A
	'''	
	def GetNodeInfoRequestHandler(self, sock, packet):
		payload = self.NodeInfo
		payload["is_master"] 		= self.IsMaster
		payload["master_uuid"] 		= self.UUID
		payload["pid"]				= self.MyPID
		payload["listener_port"]	= self.SocketServer.GetListenerPort()
		return self.BasicProtocol.BuildResponse(packet, payload)
	
	''' 
		Description: 	Handler [get_node_info] RESPONSE
		Return: 		N/A
	'''	
	def GetNodeInfoResponseHandler(self, sock, packet):
		source  	= self.BasicProtocol.GetSourceFromJson(packet)
		payload 	= self.BasicProtocol.GetPayloadFromJson(packet)
		additional 	= self.BasicProtocol.GetAdditionalFromJson(packet)
		self.LogMSG("({classname})# [GetNodeInfoResponseHandler] (NO LOGIC) {0}".format(payload, classname=self.ClassName))

		conn = self.SocketServer.GetConnectionBySock(sock)
		conn.Obj["uuid"] 			= payload["uuid"]
		conn.Obj["type"] 			= payload["type"]
		conn.Obj["pid"] 			= payload["pid"]
		conn.Obj["name"] 			= payload["name"]
		conn.Obj["listener_port"]	= payload["listener_port"]
		conn.Obj["status"] 			= 1

	''' 
		Description: 	
						1. Forging response with port for slave to use as listenning port.
						2. Sending new node connected event to all connected nodes.
						3. Sending request with slave details to Gateway.
		Return: 		N/A
	'''
	def GetPortRequestHandler(self, sock, packet):
		self.LogMSG("({classname})# [GetPortRequestHandler]".format(classname=self.ClassName))

		if sock is None:
			return ""
		
		node_info = self.BasicProtocol.GetPayloadFromJson(packet)
		nodetype 	= node_info['type']
		uuid 		= node_info['uuid']
		name 		= node_info['name']

		self.LogMSG("({classname})# [GET_PORT] {uuid} {name} {nodetype}".format(
						classname=self.ClassName,
						uuid=uuid,
						name=name,
						nodetype=nodetype))

		# Do we have available port.
		if self.PortsForClients:
			conn = self.SocketServer.GetConnectionBySock(sock)
			if conn.Obj["listener_port"] == 0:
				# New request
				port = 10000 + self.PortsForClients.pop()
				# Update node
				conn.Obj["type"] 			= nodetype
				conn.Obj["listener_port"] 	= port
				conn.Obj["uuid"] 			= uuid
				conn.Obj["name"] 			= name
				conn.Obj["status"] 			= int(conn.Obj["status"]) | 4
				conn.Obj["is_slave"]		= 1

				# [TODO] Update installed node list (UI will be updated)
				# [TODO] What will happen when slave node will try to get port when we are not connected to AWS?

				# Send message to Gateway
				payload = { 
					'node': { 	
						'ip':	str(conn.IP), 
						'port':	port, 
						'uuid':	uuid, 
						'type':	nodetype,
						'name':	name
					} 
				}
				message = self.BasicProtocol.BuildRequest("MASTER", "GATEWAY", self.UUID, "node_connected", payload, {})
				self.SendPacketGateway(message)

				# Send message (master_append_node) to all nodes.
				connection_map = self.SocketServer.GetConnections()
				for key in connection_map:
					item = connection_map[key]
					if item.Socket != self.SocketServer.GetListenerSocket():
						message = self.BasicProtocol.BuildMessage("response", "DIRECT", item.Obj["uuid"], self.UUID, "master_append_node", node_info, {})
						message = self.BasicProtocol.AppendMagic(message)
						self.SocketServer.SendData(item.IP, item.Port, message)
				
				# Store UUID if it is a service
				if nodetype == 101:
					self.EMailServiceUUID 		= uuid
				elif nodetype == 102:
					self.SMSServiceUUID 		= uuid
				elif nodetype == 103:
					self.IPScannerServiceUUID 	= uuid
					self.RegisterOnNodeChangeEvent(self.IPScannerServiceUUID)

				return self.BasicProtocol.BuildResponse(packet, { 'port': port })
			else:
				# Already assigned port (resending)
				return self.BasicProtocol.BuildResponse(packet, { 'port': conn.Obj["listener_port"] })
		else:
			# No available ports
			return self.BasicProtocol.BuildResponse(packet, { 'port': 0 })

	''' 
		Description: 	[HANDLERS]
		Return: 		N/A
	'''	
	def LocalServerTerminated(self):
		connection_map = self.SocketServer.GetConnections()
		for key in connection_map:
			conn = connection_map[key]
			payload = { 
				'node': { 	
					'ip':	str(conn.IP), 
					'port':	conn.Obj["listener_port"], 
					'uuid':	conn.Obj["uuid"],
					'type':	conn.Obj["type"]
				} 
			}
			message = self.BasicProtocol.BuildRequest("MASTER", "GATEWAY", self.UUID, "node_disconnected", payload, {})
			self.SendPacketGateway(message)

	''' 
		Description: 	[HANDLERS]
		Return: 		N/A
	'''	
	def NodeDisconnectedHandler(self, connection):
		self.LogMSG("({classname})# [NodeDisconnectedHandler] ({name} {uuid})".format(
						classname=self.ClassName,
						name=connection.Obj["name"],
						uuid=connection.Obj["uuid"]))
		if connection is not None:
			if connection.Obj["is_slave"] == 1:
				self.PortsForClients.append(connection.Obj["listener_port"] - 10000)
				# [TODO] Update installed node list (UI will be updated)
				
				# Send message to Gateway
				payload = { 
					'node': { 	
						'ip':	connection.IP, 
						'port':	connection.Obj["listener_port"], 
						'uuid':	connection.Obj["uuid"], 
						'type':	connection.Obj["type"]
					} 
				}
				message = self.BasicProtocol.BuildRequest("MASTER", "GATEWAY", self.UUID, "node_disconnected", payload, {})
				self.SendPacketGateway(message)

				# Send message (master_remove_node) to all nodes.
				connection_map = self.SocketServer.GetConnections()
				for key in connection_map:
					node = connection_map[key]
					# Don't send this message to master you your self.
					if node.Socket != self.SocketServer.GetListenerSocket() and node.Socket != connection.Socket:
						message = self.BasicProtocol.BuildMessage("response", "DIRECT", node.Obj["uuid"], self.UUID, "master_remove_node", connection.Obj, {})
						message = self.BasicProtocol.AppendMagic(message)
						self.SocketServer.SendData(node.IP, node.Port, message)

	''' 
		Description: 	[HANDLERS]
		Return: 		N/A
	'''		
	def GetLocalNodesRequestHandler(self, sock, packet):
		nodes = []
		connection_map = self.SocketServer.GetConnections()
		for key in connection_map:
			conn = connection_map[key]
			nodes.append({
				'ip':	str(conn.IP), 
				'port':	conn.Obj["listener_port"], 
				'uuid':	conn.Obj["uuid"],
				'type':	conn.Obj["type"]
			})
		return self.BasicProtocol.BuildResponse(packet, { 'nodes': nodes })

	''' 
		Description: 	[HANDLERS]
		Return: 		N/A
	'''	
	def GetNodeStatusRequestHandler(self, sock, packet):
		payload = {
			"status":"online"
		}
		return self.BasicProtocol.BuildResponse(packet, payload)

	''' 
		Description: 	[HANDLERS]
		Return: 		N/A
	'''	
	def GetNodeStatusResponseHandler(self, sock, packet):
		if self.OnApplicationResponseCallback is not None:
			self.OnApplicationResponseCallback(sock, packet)

	''' 
		Description: 	N/A
		Return: 		N/A
	'''		
	def SendGatewayPing(self):
		message = self.BasicProtocol.BuildRequest("DIRECT", "GATEWAY", self.UUID, "ping", self.NodeInfo, {})
		self.SendPacketGateway(message)

	''' 
		Description: 	N/A
		Return: 		N/A
	'''	
	def SendPacketGateway(self, packet):
		self.Network.SendWebSocket(packet)

	''' 
		Description: 	N/A
		Return: 		N/A
		Note:			TODO - Check if we need to send it via Gateway
	'''	
	def SendRequest(self, uuid, msg_type, command, payload, additional):
		# Generate request
		message = self.BasicProtocol.BuildRequest(msg_type, uuid, self.UUID, command, payload, additional)
		# Send message
		self.SendPacketGateway(message)

	''' 
		Description: 	N/A
		Return: 		N/A
	'''	
	def GatewayConnectedEvent(self):
		self.LogMSG("(Master Node)# Connection to Gateway established ...")
		# Send registration of all slaves to Gateway.
		connection_map = self.SocketServer.GetConnections()
		for key in connection_map:
			conn = connection_map[key]
			if conn.Obj["status"] == 5: # Mean - CONNECTED | PORT_AVAILABLE
				# Send message to Gateway
				payload = { 
					'node': { 	
						'ip':	conn.IP, 
						'port':	conn.Port, 
						'uuid':	conn.Obj["uuid"], 
						'type':	conn.Obj["type"],
						'name':	conn.Obj["name"]
					} 
				}
				message = self.BasicProtocol.BuildRequest("MASTER", "GATEWAY", self.UUID, "node_connected", payload, {})
				self.SendPacketGateway(message)
