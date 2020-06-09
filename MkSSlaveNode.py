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

from flask import Flask, render_template, jsonify, Response, request
import logging

import MkSGlobals
from mksdk import MkSFile
from mksdk import MkSAbstractNode
from mksdk import MkSLogger

class SlaveNode(MkSAbstractNode.AbstractNode):
	def __init__(self):
		MkSAbstractNode.AbstractNode.__init__(self)
		self.ClassName								= "Slave Node"
		self.MasterNodesList						= [] # For future use (slave to slave communication)
		self.SlaveListenerPort 						= 0
		self.MasterInfo 							= None
		self.MasterUUID 							= ""
		self.IsLocalUIEnabled						= False
		# Sates
		self.States 								= {
			'IDLE': 								self.State_Idle,
			'INIT':									self.State_Init,
			'CONNECT_MASTER':						self.State_ConnectMaster,
			'FIND_PORT_MANUALY':					self.State_FindPortManualy,
			'GET_MASTER_INFO':						self.State_GetMasterInfo,
			'GET_PORT': 							self.State_GetPort,
			'WAIT_FOR_PORT':						self.State_WaitForPort,
			'START_LISTENER':						self.State_StartListener,
			'WORKING':								self.State_Working,
			'EXIT':									self.State_Exit
		}
		# Handlers
		self.NodeResponseHandlers['get_port'] 		= self.GetPortResponseHandler
		self.NodeRequestHandlers['shutdown'] 		= self.ShutdownRequestHandler
		# Callbacks
		self.OnGetNodeInfoCallback 					= None
		self.OnGetSensorInfoRequestCallback			= None
		self.OnSetSensorInfoRequestCallback 		= None
		# Flags
		self.IsListenerEnabled 						= False
		# Counters
		self.MasterConnectionTries 					= 0
		self.MasterInformationTries 				= 0
		self.MasterTickTimeout 						= 4
		self.EnableLog								= True

	''' 
		Description: 	N/A
		Return: 		N/A
	'''	
	def EnableLogs(self, name):
		self.Logger = MkSLogger.Logger(name)
		self.Logger.EnablePrint()
		self.Logger.SetLogLevel(self.System["log_level"])
		self.Logger.EnableLogger()

	''' 
		Description: 	State [IDLE]
		Return: 		None
	'''	
	def State_Idle(self):
		self.LogMSG("({classname})# Note, in IDLE state ...".format(classname=self.ClassName),1)
		time.sleep(1)

	''' 
		Description: 	State [INIT]
		Return: 		None
	'''		
	def State_Init (self):
		self.MasterConnectionTries	= 0
		self.MasterInformationTries	= 0	
		self.SetState("CONNECT_MASTER")

	''' 
		Description: 	State [CONNECT_MASTER]
		Return: 		None
	'''	
	def State_ConnectMaster(self):
		if 0 == self.Ticker % self.MasterTickTimeout or 0 == self.MasterConnectionTries:
			if self.MasterConnectionTries > 3:
				self.SetState("EXIT")
				# self.SetState("FIND_PORT_MANUALY")
			else:
				self.LogMSG("({classname})# Trying to connect Master ({tries}) ...".format(classname=self.ClassName, tries=self.MasterConnectionTries),1)
				if self.ConnectLocalMaster() is True:
					self.SetState("GET_MASTER_INFO")
					self.SocketServer.Start()
				else:
					self.SetState("CONNECT_MASTER")
					self.MasterConnectionTries += 1

	''' 
		Description: 	State [GET_MASTER_INFO]
		Return: 		None
	'''		
	def State_GetMasterInfo(self):
		if 0 == self.Ticker % 10 or 0 == self.MasterInformationTries:
			if self.MasterInformationTries > 3:
				self.SetState("EXIT")
				# self.SetState("FIND_PORT_MANUALY")
			else:
				self.LogMSG("({classname})# Send <get_node_info> request ...".format(classname=self.ClassName),5)
				# Send request
				message = self.BasicProtocol.BuildRequest("DIRECT", "MASTER", self.UUID, "get_node_info", {}, {})
				packet  = self.BasicProtocol.AppendMagic(message)
				if self.LocalMasterConnection is not None:
					self.SocketServer.Send(self.LocalMasterConnection.Socket, packet)
				self.MasterInformationTries += 1

	''' 
		Description: 	State [GET_PORT]
		Return: 		None
	'''	
	def State_GetPort(self):
		self.LogMSG("({classname})# Sending <get_port> request ...".format(classname=self.ClassName),5)
		# Send request
		message = self.BasicProtocol.BuildRequest("DIRECT", self.MasterUUID, self.UUID, "get_port", self.NodeInfo, {})
		packet  = self.BasicProtocol.AppendMagic(message)
		if self.LocalMasterConnection is not None:
			self.SocketServer.Send(self.LocalMasterConnection.Socket, packet)
		self.SetState("WAIT_FOR_PORT")

	''' 
		Description: 	State [FIND_PORT_MANUALY] (This state disabled for now)
		Return: 		None
	'''		
	def State_FindPortManualy(self):
		self.LogMSG("({classname})# Trying to find port manualy ...".format(classname=self.ClassName),5)
		if self.SlaveListenerPort == 0:
			for idx in range(1,33):
				port = 10000 + idx
				sock, status = self.SocketServer.Connect((self.MyLocalIP, port))
				if status is True:
					self.SlaveListenerPort = port
					self.SetState("START_LISTENER")
					return
				else:
					sock.close()
		else:
			self.SetState("START_LISTENER")

	''' 
		Description: 	State [WAIT_FOR_PORT]
		Return: 		None
	'''	
	def State_WaitForPort(self):
		if 0 == self.Ticker % 20:
			if 0 == self.SlaveListenerPort:
				self.SetState("GET_PORT")
			else:
				self.SetState("START_LISTENER")

	''' 
		Description: 	State [START_LISTENER]
		Return: 		None
	'''	
	def State_StartListener(self):
		self.LogMSG("({classname})# [State_StartListener]".format(classname=self.ClassName),5)
		self.SocketServer.EnableListener(self.SlaveListenerPort)
		self.SocketServer.StartListener()
		# Let socket listener start
		time.sleep(0.1)
		# Update connection database.
		conn = self.SocketServer.GetConnectionBySock(self.SocketServer.GetListenerSocket())
		conn.Obj["listener_port"] = self.SocketServer.GetListenerPort()
		# Change state
		self.SetState("WORKING")
		
	''' 
		Description: 	State [WORKING]
		Return: 		None
	'''		
	def State_Working(self):
		if self.SocketServer.GetListenerStatus() is True:
			if self.SystemLoaded is False:
				self.SystemLoaded = True # Update node that system done loading.
				if self.NodeSystemLoadedCallback is not None:
					self.NodeSystemLoadedCallback()
			
			if 0 == self.Ticker % 60:
				self.SendGatewayPing()

	''' 
		Description: 	State [EXIT]
		Return: 		None
	'''	
	def State_Exit(self):
		self.Exit("Exit state initiated")

	''' 
		Description: 	Handler [get_node_info] REQUEST
		Return: 		N/A
	'''	
	def GetNodeInfoRequestHandler(self, sock, packet):
		self.LogMSG("({classname})# [GetNodeInfoRequestHandler]".format(classname=self.ClassName),5)
		payload = self.NodeInfo
		payload["is_master"] 		= False
		payload["master_uuid"] 		= self.MasterUUID
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
		self.LogMSG("({classname})# [GetNodeInfoResponseHandler] [{0}, {1}, {2}, {3}]".format(payload["uuid"],payload["type"],payload["pid"],payload["name"], classname=self.ClassName),5)

		conn = self.SocketServer.GetConnectionBySock(sock)
		conn.Obj["uuid"] 			= payload["uuid"]
		conn.Obj["type"] 			= payload["type"]
		conn.Obj["pid"] 			= payload["pid"]
		conn.Obj["name"] 			= payload["name"]
		conn.Obj["listener_port"]	= payload["listener_port"]
		conn.Obj["status"] 	= 1
		
		if source in "MASTER":
			# We are here because this is a response for slave boot sequence
			self.MasterInfo = payload
			self.MasterUUID = payload["uuid"]
			if self.GetState() in "GET_MASTER_INFO":
				self.SetState("GET_PORT")
		else:
			if self.OnGetNodeInfoCallback is not None:
				self.OnGetNodeInfoCallback(payload)

	''' 
		Description: 	Handler [get_port] RESPONSE
		Return: 		N/A
	'''		
	def GetPortResponseHandler(self, sock, packet):
		source  = self.BasicProtocol.GetSourceFromJson(packet)
		payload = self.BasicProtocol.GetPayloadFromJson(packet)
		self.LogMSG("({classname})# [GetPortResponseHandler]".format(classname=self.ClassName),5)

		if source in self.MasterUUID:
			self.SlaveListenerPort = payload["port"]
			self.SetState("START_LISTENER")

	''' 
		Description: 	Override method to send request
		Return: 		N/A
	'''	
	def SendRequest(self, uuid, msg_type, command, payload, additional):
		# Generate request
		message = self.BasicProtocol.BuildRequest(msg_type, uuid, self.UUID, command, payload, additional)
		packet  = self.BasicProtocol.AppendMagic(message)
		if self.LocalMasterConnection is not None:
			self.SocketServer.Send(self.LocalMasterConnection.Socket, packet)

	''' 
		Description: 	Emit event to webface via local websocket.
		Return: 		N/A
	'''	
	def EmitOnNodeChange_WebfaceLocalWebsocket(self, payload, data):
		ws_id = payload["ws_id"]
		message = self.BasicProtocol.BuildRequest("DIRECT", "WEBFACE", self.UUID, "on_node_change", data, {
			'identifier':-1
		})
		if self.LocalWSManager is not None:
			self.LocalWSManager.Send(ws_id, message)
	
	''' 
		Description: 	Emit event to webface via gateway.
		Return: 		N/A
	'''	
	def EmitOnNodeChange_WebfaceGateway(self, payload, data):
		webface_indexer = payload["webface_indexer"]
		message = self.BasicProtocol.BuildRequest("DIRECT", "WEBFACE", self.UUID, "on_node_change", data, {
			'identifier':-1,
			'webface_indexer':webface_indexer
		})

		packet  = self.BasicProtocol.AppendMagic(message)
		if self.LocalMasterConnection.Socket is not None:
			self.SocketServer.Send(self.LocalMasterConnection.Socket, packet)

	''' 
		Description: 	Emit event to webface.
		Return: 		N/A
	'''		
	def EmitOnNodeChange(self, data):
		self.LogMSG("({classname})# [EmitOnNodeChange]".format(classname=self.ClassName),1)
		self.DeviceChangeListLock.acquire()
		# Itterate over registered nodes.
		for item in self.OnDeviceChangeList:
			payload 	= item["payload"]
			item_type	= payload["item_type"] # (1 - Node, 2 - Webface)

			# Node
			if item_type == 1:
				uuid = payload["uuid"]
				message = self.BasicProtocol.BuildRequest("DIRECT", uuid, self.UUID, "on_node_change", data, {})
				packet  = self.BasicProtocol.AppendMagic(message)
				if self.LocalMasterConnection is not None:
					self.SocketServer.Send(self.LocalMasterConnection.Socket, packet)
			# Webface
			elif item_type == 2:
				# The connected socket is via gateway.
				if payload["pipe"] == "GATEWAY":
					self.EmitOnNodeChange_WebfaceGateway(payload, data)
				# The connected socket is via local websocket.
				elif payload["pipe"] == "LOCAL_WS":
					self.EmitOnNodeChange_WebfaceLocalWebsocket(payload, data)
			else:
				self.LogMSG("({classname})# [EmitOnNodeChange] Unsupported item type".format(classname=self.ClassName),3)
		self.DeviceChangeListLock.release()

	''' 
		Description: 	Send <ping> request to gateway with node information.
		Return: 		N/A
	'''		
	def SendGatewayPing(self):
		# Send request
		message = self.BasicProtocol.BuildRequest("DIRECT", "GATEWAY", self.UUID, "ping", self.NodeInfo, {})
		packet  = self.BasicProtocol.AppendMagic(message)

		if self.LocalMasterConnection is not None:
			self.LogMSG("({classname})# Sending ping request ...".format(classname=self.ClassName),1)
			self.SocketServer.Send(self.LocalMasterConnection.Socket, packet)

	''' 
		Description: 	Local handler - Node disconnected event.
		Return: 		N/A
	'''		
	def NodeDisconnectedHandler(self, connection):
		self.LogMSG("({classname})# [NodeDisconnectedHandler]".format(classname=self.ClassName),5)
		# Check if disconneced connection is a master.
		for node in self.MasterNodesList:
			if connection.Socket == node.Socket:
				self.MasterNodesList.remove(node)
				# Need to close listener port because we are going to get this port again
				self.LocalMasterConnection.Socket.close()
				# If master terminated we need to close node.
				self.SetState("CONNECT_MASTER")
				self.LocalMasterConnection = None
				if self.OnMasterDisconnectedCallback is not None:
					self.OnMasterDisconnectedCallback()
		else:
			# Raise event for user
			if self.OnTerminateConnectionCallback is not None:
				self.OnTerminateConnectionCallback(connection)

	''' 
		Description: 	List of masters.
		Return: 		List of masters.
	'''			
	def GetMasters(self):
		return self.MasterNodesList

	''' 
		Description: 	Handler [get_node_status] RESPONSE
		Return: 		N/A
	'''		
	def GetNodeStatusResponseHandler(self, sock, packet):
		if self.OnApplicationResponseCallback is not None:
			self.OnApplicationResponseCallback(sock, packet)

	''' 
		Description: 	Handler [shutdown] REQUEST
		Return: 		N/A
	'''
	def ShutdownRequestHandler(self, sock, packet):
		self.LogMSG("({classname})# [ShutdownRequestHandler]".format(classname=self.ClassName),5)
		if self.OnShutdownCallback is not None:
			self.OnShutdownCallback()

		# Send message to requestor.
		message = self.BasicProtocol.BuildResponse(packet, {"status":"shutdown"})
		packet  = self.BasicProtocol.AppendMagic(message)
		self.SocketServer.Send(sock, packet)

		# Let the messsage propogate to local server.
		time.sleep(1)
		self.Exit("Shutdown request received")
		return None		
