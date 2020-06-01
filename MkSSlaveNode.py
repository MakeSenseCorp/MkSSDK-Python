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
		self.ClassName							= "Slave Node"
		self.MasterNodesList					= [] # For future use (slave to slave communication)
		self.SlaveListenerPort 					= 0
		self.MasterInfo 						= None
		self.MasterUUID 						= ""
		self.IsLocalUIEnabled					= False
		# Sates
		self.States 							= {
			'IDLE': 							self.State_Idle,
			'INIT':								self.State_Init,
			'CONNECT_MASTER':					self.State_ConnectMaster,
			'FIND_PORT_MANUALY':				self.State_FindPortManualy,
			'GET_MASTER_INFO':					self.State_GetMasterInfo,
			'GET_PORT': 						self.State_GetPort,
			'WAIT_FOR_PORT':					self.State_WaitForPort,
			'START_LISTENER':					self.State_StartListener,
			'WORKING':							self.State_Working,
			'EXIT':								self.State_Exit
		}
		# Handlers
		self.NodeResponseHandlers['get_port'] 			= self.GetPortResponseHandler
		self.NodeRequestHandlers['shutdown'] 			= self.ShutdownRequestHandler
		#self.ResponseHandlers	= {
		#	'get_node_info':						self.GetNodeInfoHandler,
		#	'undefined':							self.UndefindHandler
		#}
		#self.RequestHandlers	= {
		#	'set_sensor_info': 						self.SetSensorInfoRequestHandler,
		#	'upload_file':							self.UploadFileHandler,
		#	'undefined':							self.UndefindHandler
		#}
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
		self.Logger.EnableLogger()

	''' 
		Description: 	State [IDLE]
		Return: 		None
	'''	
	def State_Idle(self):
		self.LogMSG("({classname})# Note, in IDLE state ...".format(classname=self.ClassName))
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
				self.LogMSG("({classname})# Trying to connect Master ({tries}) ...".format(classname=self.ClassName, tries=self.MasterConnectionTries))
				if self.ConnectLocalMaster() is True:
					self.SetState("GET_MASTER_INFO")
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
				self.LogMSG("({classname})# Send <get_node_info> request ...".format(classname=self.ClassName))
				# Send request
				message = self.BasicProtocol.BuildRequest("DIRECT", "MASTER", self.UUID, "get_node_info", {}, {})
				packet  = self.BasicProtocol.AppendMagic(message)
				if self.LocalMasterConnection is not None:
					self.Transceiver.Send({"sock":self.LocalMasterConnection.Socket, "packet":packet})
				self.MasterInformationTries += 1

	''' 
		Description: 	State [GET_PORT]
		Return: 		None
	'''	
	def State_GetPort(self):
		self.LogMSG("({classname})# Sending <get_port> request ...".format(classname=self.ClassName))
		# Send request
		message = self.BasicProtocol.BuildRequest("DIRECT", self.MasterUUID, self.UUID, "get_port", self.NodeInfo, {})
		packet  = self.BasicProtocol.AppendMagic(message)
		if self.LocalMasterConnection is None:
			self.Transceiver.Send({"sock":self.LocalMasterConnection.Socket, "packet":packet})
		self.SetState("WAIT_FOR_PORT")
	
	def State_FindPortManualy(self):
		self.LogMSG("({classname})# Trying to find port manualy ...".format(classname=self.ClassName))
		if self.SlaveListenerPort == 0:
			for idx in range(1,33):
				port = 10000 + idx
				sock, status = self.ConnectNodeSocket((self.MyLocalIP, port))
				if status is False:
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
		self.LogMSG("({classname})# Trying to start listener ...".format(classname=self.ClassName))
		self.SocketServer.Start(self.SlaveListenerPort)
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

	def GetNodeInfoRequestHandler(self, sock, packet):
		self.LogMSG("({classname})# Node Info Request ...".format(classname=self.ClassName))
		payload = self.NodeInfo
		payload["is_master"] 	= False
		payload["master_uuid"] 	= self.MasterUUID
		return self.BasicProtocol.BuildResponse(packet, payload)

	''' 
		Description: 	Handler [node_info] RESPONSE
		Return: 		N/A
	'''	
	def GetNodeInfoResponseHandler(self, sock, packet):
		source  	= self.BasicProtocol.GetSourceFromJson(packet)
		payload 	= self.BasicProtocol.GetPayloadFromJson(packet)
		additional 	= self.BasicProtocol.GetAdditionalFromJson(packet)
		self.LogMSG("({classname})# Node Info Response ...".format(classname=self.ClassName))
		if source in "MASTER":
			# We are here because this is a response for slave boot sequence
			self.MasterInfo = payload
			self.MasterUUID = payload["uuid"]
			if self.GetState() in "GET_MASTER_INFO":
				self.SetState("GET_PORT")
		else:
			if self.OnGetNodeInfoCallback is not None:
				self.OnGetNodeInfoCallback(payload, additional["online"])

	''' 
		Description: 	Handler [get_port] RESPONSE
		Return: 		N/A
	'''		
	def GetPortResponseHandler(self, sock, packet):
		source  = self.BasicProtocol.GetSourceFromJson(packet)
		payload = self.BasicProtocol.GetPayloadFromJson(packet)

		if source in self.MasterUUID:
			self.SlaveListenerPort = payload["port"]
			self.SetState("START_LISTENER")

	def SendRequest(self, uuid, msg_type, command, payload, additional):
		# Generate request
		message = self.BasicProtocol.BuildRequest(msg_type, uuid, self.UUID, command, payload, additional)
		packet  = self.BasicProtocol.AppendMagic(message)
		if self.LocalMasterConnection is None:
			pass
			# TODO - Send over local websocket
		else:
			self.Transceiver.Send({"sock":self.LocalMasterConnection.Socket, "packet":packet})

	def EmitOnNodeChange(self, data):
		# self.LogMSG("({classname})# Emit onNodeChange event ...".format(classname=self.ClassName))
		self.DeviceChangeListLock.acquire()
		for item in self.OnDeviceChangeList:
			payload 	= item["payload"]
			item_type	= payload["item_type"]

			# Node
			if item_type == 1:
				uuid = payload["uuid"]
				message = self.BasicProtocol.BuildRequest("DIRECT", uuid, self.UUID, "on_node_change", data, {})
				packet  = self.BasicProtocol.AppendMagic(message)
				if self.LocalMasterConnection is None:
					pass
				else:
					self.Transceiver.Send({"sock":self.LocalMasterConnection.Socket, "packet":packet})
			# Webface
			elif item_type == 2:
				if payload["pipe"] == "GATEWAY":
					webface_indexer = payload["webface_indexer"]
					message = self.BasicProtocol.BuildRequest("DIRECT", "WEBFACE", self.UUID, "on_node_change", data, {
						'identifier':-1,
						'webface_indexer':webface_indexer
					})

					packet  = self.BasicProtocol.AppendMagic(message)
					if self.LocalMasterConnection.Socket is None:
						pass
					else:
						self.Transceiver.Send({"sock":self.LocalMasterConnection.Socket, "packet":packet})
				elif payload["pipe"] == "LOCAL_WS":
					ws_id = payload["ws_id"]
					message = self.BasicProtocol.BuildRequest("DIRECT", "WEBFACE", self.UUID, "on_node_change", data, {
						'identifier':-1
					})
					self.LocalWSManager.Send(ws_id, message)
		self.DeviceChangeListLock.release()

	def SendGatewayPing(self):
		# Send request
		message = self.BasicProtocol.BuildRequest("DIRECT", "GATEWAY", self.UUID, "ping", self.NodeInfo, {})
		packet  = self.BasicProtocol.AppendMagic(message)

		if self.LocalMasterConnection is None:
			pass
		else:
			print ("({classname})# Sending ping request ...".format(classname=self.ClassName))
			self.Transceiver.Send({"sock":self.LocalMasterConnection.Socket, "packet":packet})
	
	def NodeDisconnectHandler(self, sock):
		self.LogMSG("({classname})# [NodeDisconnectHandler]".format(classname=self.ClassName))
		# Check if disconneced connection is a master.
		for node in self.MasterNodesList:
			if sock == node.Socket:
				self.MasterNodesList.remove(node)
				# Need to close listener port because we are going to get this port again
				self.ServerSocket.close()
				# If master terminated we need to close node.
				self.SetState("CONNECT_MASTER")
				self.LocalMasterConnection = None
				if self.OnMasterDisconnectedCallback is not None:
					self.OnMasterDisconnectedCallback()
	
	def GetMasters(self):
		return self.MasterNodesList
	
	def GetNodeInfoHandler(self, sock, packet):
		if self.OnGetNodeInfoCallback is not None:
			self.OnGetNodeInfoCallback(packet)

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
		self.LogMSG("({classname})# [ShutdownRequestHandler]".format(classname=self.ClassName))
		if self.OnShutdownCallback is not None:
			self.OnShutdownCallback()

		# Send message to requestor.
		message = self.BasicProtocol.BuildResponse(packet, {"status":"shutdown"})
		packet  = self.BasicProtocol.AppendMagic(message)
		self.Transceiver.Send({"sock":sock, "packet":packet})

		# Let the messsage propogate to local server.
		time.sleep(1)
		self.Exit("Shutdown request received")
		return None		
