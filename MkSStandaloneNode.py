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
			'IDLE': 							self.StateIdle,
			'INIT':								self.StateInit,
			'INIT_GATEWAY':						self.StateInitGateway,
			'ACCESS_GATEWAY': 					self.StateAccessGetway,
			'ACCESS_WAIT_GATEWAY':				self.StateAccessWaitGatway,
			'INIT_LOCAL_SERVER':				self.StateInitLocalServer,
			'WORKING': 							self.StateWork
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
	
	def EnableLogs(self, name):
		self.Logger = MkSLogger.Logger(name)
		self.Logger.EnablePrint()
		self.Logger.EnableLogger()

	def Initiate(self):
		pass

	def StateIdle (self):
		self.LogMSG("({classname})# Note, in IDLE state ...".format(classname=self.ClassName))
		time.sleep(1)
	
	def StateInit (self):
		self.SetState("INIT_LOCAL_SERVER")
	
	def StateInitGateway(self):
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

	def StateAccessGetway (self):
		if self.IsNodeWSServiceEnabled is True:
			self.Network.AccessGateway(self.Key, json.dumps({
				'node_name': str(self.Name),
				'node_type': self.Type
			}))

			self.SetState("ACCESS_WAIT_GATEWAY")
		else:
			self.SetState("WORKING")
	
	def StateAccessWaitGatway (self):
		if self.AccessTick > 10:
			self.SetState("ACCESS_WAIT_GATEWAY")
			self.AccessTick = 0
		else:
			self.AccessTick += 1
	
	def StateInitLocalServer(self):
		self.ServerAdderss = ('', self.LocalPort)
		status = self.TryStartListener()
		if status is True:
			self.IsListenerEnabled = True
			self.SetState("WORKING")
		time.sleep(1)

	def StateWork (self):
		if self.SystemLoaded is False:
			self.SystemLoaded = True # Update node that system done loading.
			if self.NodeSystemLoadedCallback is not None:
				self.NodeSystemLoadedCallback()

	def WebSocketConnectedCallback (self):
		self.SetState("WORKING")
		if self.GatewayConnectedCallback is not None:
			self.GatewayConnectedCallback()
	
	def WebSocketConnectionClosedCallback (self):
		if self.GatewayConnectionClosedCallback is not None:
			self.GatewayConnectionClosedCallback()
		self.NetworkAccessTickLock.acquire()
		try:
			self.AccessTick = 0
		finally:
			self.NetworkAccessTickLock.release()
		self.SetState("ACCESS_GATEWAY")

	# TODO - Must be dealt with different thread (we must have thread poll)
	def WebSocketDataArrivedCallback (self, packet):
		self.NetworkAccessTickLock.acquire()
		try:
			self.SetState("WORKING")
			messageType = self.BasicProtocol.GetMessageTypeFromJson(packet)
			direction 	= self.BasicProtocol.GetDirectionFromJson(packet)
			destination = self.BasicProtocol.GetDestinationFromJson(packet)
			source 		= self.BasicProtocol.GetSourceFromJson(packet)
			command 	= self.BasicProtocol.GetCommandFromJson(packet)

			packet["additional"]["client_type"] = "global_ws"
			self.LogMSG("({classname})# WS [{direction}] {source} -> {dest} [{cmd}]".format(classname=self.ClassName,
						direction=direction,
						source=source,
						dest=destination,
						cmd=command))
			
			if messageType == "BROADCAST":
				pass
		
			if destination in source:
				self.NetworkAccessTickLock.release()
				return

			# Is this packet for me?
			if destination in self.UUID:
				if messageType == "CUSTOM":
					self.NetworkAccessTickLock.release()
					return
				elif messageType in ["DIRECT", "PRIVATE", "WEBFACE"]:
					if command in self.NodeRequestHandlers.keys():
						message = self.NodeRequestHandlers[command](None, packet)
						self.SendPacketGateway(message)
					else:
						if self.GatewayDataArrivedCallback is not None:
							self.GatewayDataArrivedCallback(None, packet)
				else:
					self.LogMSG("({classname})# [Websocket INBOUND] ERROR - Not support {0} request type.".format(messageType, classname=self.ClassName))
			else:
				self.LogMSG("({classname})# Not mine ... Sending to slave ...".format(classname=self.ClassName))
		except Exception as e:
			self.LogMSG("({classname})# WebSocket Error - Data arrived issue\nPACKET#\n{0}\n(EXEPTION)# {error}".format(packet,
						classname=self.ClassName,
						error=str(e)))
		self.NetworkAccessTickLock.release()
	
	def WebSocketErrorCallback (self):
		self.LogMSG("({classname})# ERROR - Gateway socket error".format(classname=self.ClassName))
		# TODO - Send callback "OnWSError"
		self.NetworkAccessTickLock.acquire()
		try:
			self.AccessTick = 0
		finally:
			self.NetworkAccessTickLock.release()
		self.SetState("ACCESS_WAIT_GATEWAY")

	def GetNodeInfoRequestHandler(self, sock, packet):
		payload = self.NodeInfo
		payload["is_master"] 	= False
		payload["master_uuid"] 	= ""
		return self.Network.BasicProtocol.BuildResponse(packet, payload)

	def SendRequest(self, uuid, msg_type, command, payload, additional):
		# Generate request
		message = self.Network.BasicProtocol.BuildRequest(msg_type, uuid, self.UUID, command, payload, additional)
		# Send message
		self.SendPacketGateway(message)

	def GetNodeStatusResponseHandler(self, sock, packet):
		if self.OnApplicationResponseCallback is not None:
			self.OnApplicationResponseCallback(sock, packet)