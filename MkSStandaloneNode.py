#!/usr/bin/python
import os
import sys
import json
import time
if sys.version_info[0] < 3:
	import thread
else:
	import _thread
import threading
import socket
import subprocess
from subprocess import call
import urllib
import logging

import MkSGlobals
from mksdk import MkSFile
from mksdk import MkSNetMachine
from mksdk import MkSAbstractNode
from mksdk import MkSShellExecutor
from mksdk import MkSLogger

class StandaloneNode(MkSAbstractNode.AbstractNode):
	def __init__(self, port):
		MkSAbstractNode.AbstractNode.__init__(self)
		self.ClassName 							= "Standalone Node"
		# Members
		self.HostName							= socket.gethostname()
		self.IsMaster 							= False
		self.LocalPort 							= port
		self.IsLocalUIEnabled					= False
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
		# Callbacks
		self.GatewayDataArrivedCallback 		= None
		self.GatewayConnectedCallback 			= None
		self.GatewayConnectionClosedCallback 	= None
		self.OnCustomCommandRequestCallback		= None
		self.OnCustomCommandResponseCallback	= None
		# Flags
		self.IsListenerEnabled 					= False

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
				if self.SocketServer.GetListenerStatus() is True:
					self.SetState("WORKING")
				else:
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
		self.SocketServer.EnableListener(self.LocalPort)
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

		if self.IsNodeWSServiceEnabled is True:	
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
		try:
			self.AccessTick = 0
		finally:
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
		self.LogMSG("({classname})# ERROR - Gateway socket error".format(classname=self.ClassName))
		# TODO - Send callback "OnWSError"
		self.NetworkAccessTickLock.acquire()
		try:
			self.AccessTick = 0
		finally:
			self.NetworkAccessTickLock.release()
		self.SetState("ACCESS_WAIT_GATEWAY")

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
	def GatewayConnectedEvent(self):
		self.LogMSG("({classname})# Connection to Gateway established ...".format(classname=self.ClassName))
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