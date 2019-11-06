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
from mksdk import MkSLocalNodesCommands

class SlaveNode(MkSAbstractNode.AbstractNode):
	def __init__(self):
		MkSAbstractNode.AbstractNode.__init__(self)
		self.ClassName						= "Slave Node"
		self.MasterNodesList				= [] # For future use (slave to slave communication)
		self.SlaveListenerPort 				= 0
		self.MasterSocket					= None
		self.MasterInfo 					= None
		self.MasterUUID 					= ""
		# Sates
		self.States 						= {
			'IDLE': 						self.StateIdle,
			'INIT':							self.StateInit,
			'CONNECT_MASTER':				self.StateConnectMaster,
			'GET_MASTER_INFO':				self.StateGetMasterInfo,
			'GET_PORT': 					self.StateGetPort,
			'WAIT_FOR_PORT':				self.StateWaitForPort,
			'START_LISTENER':				self.StateStartListener,
			'WORKING':						self.StateWorking,
			'EXIT':							self.StateExit
		}
		# Handlers
		# Response - Handler when response returned to slave (slave is a requestor)
		self.NodeResponseHandlers['get_port'] 		= self.GetPortResponseHandler
		#self.ResponseHandlers	= {
		#	'get_local_nodes': 						self.GetLocalNodeResponseHandler,
		#	'get_master_info': 						self.GetMasterInfoResponseHandler,
		#	'get_sensor_info': 						self.GetSensorInfoResponseHandler,
		#	'set_sensor_info': 						self.SetSensorInfoResponseHandler,
		#	'get_port':								self.GetPortResponseHandler,
		#	'nodes_list':							self.GetNodesListHandler,
		#	'get_node_info':						self.GetNodeInfoHandler,
		#	'master_append_node':					self.MasterAppendNode,
		#	'master_remove_node':					self.MasterRemoveNodeHandler,
		#	'undefined':							self.UndefindHandler
		#}
		# Request - Response handler to sent request. (slave is responder)
		#self.RequestHandlers	= {
		#	'get_sensor_info': 						self.GetSensorInfoRequestHandler,
		#	'set_sensor_info': 						self.SetSensorInfoRequestHandler,
		#	'get_file':								self.GetFileHandler,
		#	'upload_file':							self.UploadFileHandler,
		#	'exit':									self.ExitHandler,
		#	'undefined':							self.UndefindHandler
		#}
		# Callbacks
		self.LocalServerDataArrivedCallback			= None
		self.OnGetLocalNodesResponeCallback 		= None
		self.OnGetMasterInfoResponseCallback		= None
		self.OnMasterAppendNodeResponseCallback		= None
		self.OnMasterRemoveNodeResponseCallback 	= None
		self.OnGetSensorInfoResponseCallback 		= None
		self.OnGetNodesListCallback 				= None
		self.OnGetNodeInfoCallback 					= None

		self.OnGetSensorInfoRequestCallback			= None
		self.OnSetSensorInfoRequestCallback 		= None
		self.OnUploadFileRequestCallback 			= None
		self.OnGetNodeInfoRequestCallback 			= None
		self.OnMasterAppendNodeCallback 			= None
		self.OnMasterRemoveNodeCallback 			= None
		# Flags
		self.IsListenerEnabled 						= False
		# Counters
		self.MasterConnectionTries 					= 0
		self.MasterInformationTries 				= 0	

	#
	# ###### SLAVE NODE INITIATE ->
	#

	def Initiate(self):
		self.SetState("INIT")

	#
	# ###### SLAVE NODE INITIATE <-
	#

	#
	# ###### SLAVE NODE STATES ->
	#

	def StateIdle(self):
		print ("({classname})# Note, in IDLE state ...".format(classname=self.ClassName))
		time.sleep(1)
	
	def StateInit (self):
		self.MasterConnectionTries	= 0
		self.MasterInformationTries	= 0	

		print ("({classname})# Trying to connect Master ({tries}) ...".format(classname=self.ClassName, tries=self.MasterConnectionTries))
		self.MasterConnectionTries += 1
		if self.ConnectMaster() is True:
			self.SetState("GET_MASTER_INFO")
			print ("({classname})# Send get_node_info request ...".format(classname=self.ClassName))
			# Send request
			message = self.BasicProtocol.BuildRequest("DIRECT", "MASTER", self.UUID, "get_node_info", {}, {})
			packet  = self.BasicProtocol.AppendMagic(message)
			self.MasterSocket.send(packet)
		else:
			self.SetState("CONNECT_MASTER")

	def StateConnectMaster(self):
		if 0 == self.Ticker % 10:
			if self.MasterConnectionTries > 3:
				self.SetState("EXIT")
			else:
				print ("({classname})# Trying to connect Master ({tries}) ...".format(classname=self.ClassName, tries=self.MasterConnectionTries))
				if self.ConnectMaster() is True:
					self.SetState("GET_MASTER_INFO")
				else:
					self.SetState("CONNECT_MASTER")
					self.MasterConnectionTries += 1
	
	def StateGetMasterInfo(self):
		if 0 == self.Ticker % 10:
			if self.MasterInformationTries > 3:
				self.SetState("EXIT")
			else:
				print ("({classname})# Send get_node_info request ...".format(classname=self.ClassName))
				# Send request
				message = self.BasicProtocol.BuildRequest("DIRECT", "MASTER", self.UUID, "get_node_info", {}, {})
				packet  = self.BasicProtocol.AppendMagic(message)
				self.MasterSocket.send(packet)
				self.MasterInformationTries += 1

	def StateGetPort(self):
		print ("({classname})# Sending get_port request ...".format(classname=self.ClassName))
		# Send request
		message = self.BasicProtocol.BuildRequest("DIRECT", self.MasterUUID, self.UUID, "get_port", self.NodeInfo, {})
		packet  = self.BasicProtocol.AppendMagic(message)
		self.MasterSocket.send(packet)
		self.SetState("WAIT_FOR_PORT")

	def StateWaitForPort(self):
		if 0 == self.Ticker % 20:
			if 0 == self.SlaveListenerPort:
				self.SetState("GET_PORT")
			else:
				self.SetState("START_LISTENER")

	def StateStartListener(self):
		print ("StateStartListener")
		self.ServerAdderss = ('', self.SlaveListenerPort)
		status = self.TryStartListener()
		if True == status:
			self.IsListenerEnabled = True
			self.SetState("WORKING")

	def StateWorking(self):
		if 0 == self.Ticker % 60:
			self.SendGatewayPing()

	def StateExit(self):
		self.Exit()

	#
	# ###### SLAVE NODE STATES <-
	#

	#
	# ###### SLAVE NODE GATAWAY CALLBACKS ->
	#

	def GetNodeInfoRequestHandler(self, sock, packet):
		print ("[SlaveNode] GetNodeInfoHandler")
		payload = self.NodeInfo
		return self.BasicProtocol.BuildResponse(packet, payload)

	def GetNodeInfoResponseHandler(self, sock, packet):
		source  = self.BasicProtocol.GetSourceFromJson(packet)
		payload = self.BasicProtocol.GetPayloadFromJson(packet)
		if source in "MASTER":
			# We are here because this is a response for slave boot sequence
			self.MasterInfo = payload
			self.MasterUUID = payload["uuid"]
			if self.GetState() in "GET_MASTER_INFO":
				self.SetState("GET_PORT")
	
	def GetPortResponseHandler(self, sock, packet):
		source  = self.BasicProtocol.GetSourceFromJson(packet)
		payload = self.BasicProtocol.GetPayloadFromJson(packet)

		if source in self.MasterUUID:
			self.SlaveListenerPort = payload["port"]
			self.SetState("START_LISTENER")

	#
	# ###### SLAVE NODE GATAWAY CALLBACKS <-
	#

	def SendGatewayPing(self):
		print ("({classname})# Sending ping request ...".format(classname=self.ClassName))
		# Send request
		message = self.BasicProtocol.BuildRequest("DIRECT", "GATEWAY", self.UUID, "ping", self.NodeInfo, {})
		packet  = self.BasicProtocol.AppendMagic(message)
		self.MasterSocket.send(packet)
	
	def PreUILoaderHandler(self):
		print ("[SlaveNode] PreUILoaderHandler")
		port = 8000 + (self.ServerAdderss[1] - 10000)
		self.InitiateLocalServer(port)
		# UI RestAPI
		self.UI.AddEndpoint("/get/node_widget/<key>",		"get_node_widget",	self.GetNodeWidgetHandler)
		self.UI.AddEndpoint("/get/node_config/<key>",		"get_node_config",	self.GetNodeConfigHandler)

	def ConnectMaster(self):
		sock, status = self.ConnectNodeSocket((self.MyLocalIP, 16999))
		if status is True:
			node = self.AppendConnection(sock, self.MyLocalIP, 16999)
			node.LocalType = "MASTER"
			self.MasterNodesList.append(node)
			if self.OnMasterFoundCallback is not None:
				self.OnMasterFoundCallback([sock, self.MyLocalIP])
			# Save socket as master socket
			self.MasterSocket = sock
			return True

		return False
	
	#
	# ############################################################################################
	#

	def MasterAppendNode(self, sock, packet):
		if self.OnMasterAppendNodeCallback is not None:
			self.OnMasterAppendNodeCallback(packet["node"]["uuid"], 
											packet["node"]["type"], 
											packet["node"]["ip"],
											packet["node"]["port"])
	
	def MasterRemoveNodeHandler(self, sock, packet):
		if self.OnMasterRemoveNodeCallback is not None:
			self.OnMasterRemoveNodeCallback(packet["node"]["uuid"], 
											packet["node"]["type"], 
											packet["node"]["ip"],
											packet["node"]["port"])
	
	def GetNodesListHandler(self, sock, packet):
		if self.OnGetNodesListCallback is not None:
			self.OnGetNodesListCallback(packet["payload"]["data"])
	
	def GetNodeInfoHandler(self, sock, packet):
		if self.OnGetNodeInfoCallback is not None:
			self.OnGetNodeInfoCallback(packet)

	# TODO - Implement this method.
	def GetNodeStatusRequestHandler(self, sock, packet):
		pass

	def GetNodeStatusRequestHandler(self, sock, packet):
		pass
	
	def GetNodeStatusResponseHandler(self, sock, packet):
		pass
	# ############

	"""
	Local Face RESP API methods
	"""
	def GetNodeWidgetHandler(self, key):
		print ("[SlaveNode]# GetNodeWidgetHandler", self.Pwd + "static/js/node/widget.js")
		objFile = MkSFile.File()
		js = objFile.Load("static/js/node/widget.js")
		return js

	def GetNodeConfigHandler(self, key):
		print ("[SlaveNode]# GetNodeConfigHandler", self.Pwd + "static/js/node/widget_config.js")
		objFile = MkSFile.File()
		js = objFile.Load("static/js/node/widget_config.js")
		return js
	"""
	Local Face RESP API methods
	"""
	def SendSensorInfoChange(self, sensors):
		json = self.Commands.GenerateJsonProxyRequest(self.UUID, "WEBFACE", "get_sensor_info", {})
		msg  = self.Commands.ProxyResponse(json, sensors)
		self.MasterSocket.send(msg)
	
	def GetListOfNodeFromGateway(self):
		print ("[SlaveNode] GetListOfNodeFromGateway")
		payload = self.Commands.SendListOfNodesRequest("GATEWAY", self.UUID)
		self.MasterSocket.send(payload)
	
	def GetNodeInfo(self, uuid):
		print ("[SlaveNode] GetNodeInfo")
		payload = self.Commands.NodeInfoRequest(uuid, self.UUID)
		self.MasterSocket.send(payload)
	
	def SendMessageToNodeViaGateway(self, uuid, message_type, data):
		print ("[SlaveNode] SendMessageToNodeViaGateway")
		payload = self.Commands.SendMessageToNodeViaGatewayRequest(message_type, uuid, self.UUID, data)
		self.MasterSocket.send(payload)

	def CleanMasterList(self):
		for node in self.MasterNodesList:
			self.RemoveConnection(node.Socket)
		self.MasterNodesList = []

	def SearchForMasters(self):
		if self.OnMasterSearchCallback is not None:
			self.OnMasterSearchCallback()
		# Clean master nodes list.
		if False == self.SearchDontClean:
			self.CleanMasterList()
		# Find all master nodes on the network.
		return self.FindMasters()

	

	def SendCustomCommandResponse(self, sock, packet, payload):
		direction = packet["direction"]
		if ("proxy" in direction):
			print (" P R O X Y ")
			msg = self.Commands.ProxyResponse(packet, payload)
			sock.send(msg)
		else:
			print (" R E G U L A R")

	def SendSensorInfoResponse(self, sock, packet, sensors):
		direction = packet["direction"]
		if ("proxy" in direction):
			print (" P R O X Y ")
			msg = self.Commands.ProxyResponse(packet, sensors)
			sock.send(msg)
		else:
			print (" R E G U L A R")

		#payload = self.Commands.GetSensorInfoResponse(self.UUID, sensors)
		#sock.send(payload)

	def NodeDisconnectHandler(self, sock):
		print ("NodeDisconnectHandler")
		# Check if disconneced connection is a master.
		for node in self.MasterNodesList:
			if sock == node.Socket:
				self.MasterNodesList.remove(node)
				# If master terminated we need to close node.
				self.ChangeState("CONNECT_MASTER")
				if self.OnMasterDisconnectedCallback is not None:
					self.OnMasterDisconnectedCallback()

	def NodeMasterAvailable(self, sock):
		print ("NodeMasterAvailable")
		# Append new master to the list
		conn = self.GetConnection(sock)
		# TODO - Check if we don't have this connection already
		self.MasterNodesList.append(conn)
		# Get Master slave nodes.
		packet = self.CommandsGetLocalNodes()
		sock.send(packet)

	# RESPONSE Handlers >

	def GetLocalNodeResponseHandler(self, sock, packet):
		pass

	def GetMasterInfoResponseHandler(self, sock, packet):
		pass

	def GetSensorInfoResponseHandler(self, sock, packet):
		pass

	def SetSensorInfoResponseHandler(self, sock, packet):
		pass

	# RESPONSE Handlers <
	# REQUEST Handlers <

	def GetSensorInfoRequestHandler(self, sock, packet):
		if self.OnGetSensorInfoRequestCallback is not None:
			self.OnGetSensorInfoRequestCallback(packet, sock)

	def SetSensorInfoRequestHandler(self, sock, packet):
		if self.OnSetSensorInfoRequestCallback is not None:
			self.OnSetSensorInfoRequestCallback(packet, sock)

	def UploadFileHandler(self, sock, packet):
		if self.OnUploadFileRequestCallback is not None:
			self.OnUploadFileRequestCallback(packet, sock)

	# REQUEST Handlers <	

	def UndefindHandler(self, sock, packet):
		if None is not self.LocalServerDataArrivedCallback:
			self.LocalServerDataArrivedCallback(packet, sock)

	def GetMasters(self):
		return self.MasterNodesList

	def ExitHandler(self, sock, packet):
		if self.OnExitCallback is not None:
			self.OnExitCallback()
			packet = self.Commands.ExitResponse("OK")
			sock.send(packet)
			
