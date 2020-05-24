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

class SlaveNode(MkSAbstractNode.AbstractNode):
	def __init__(self):
		MkSAbstractNode.AbstractNode.__init__(self)
		self.ClassName							= "Slave Node"
		self.MasterNodesList					= [] # For future use (slave to slave communication)
		self.SlaveListenerPort 					= 0
		self.MasterSocket						= None
		self.MasterInfo 						= None
		self.MasterUUID 						= ""
		self.IsLocalUIEnabled					= False
		# Sates
		self.States 							= {
			'IDLE': 							self.StateIdle,
			'INIT':								self.StateInit,
			'CONNECT_MASTER':					self.StateConnectMaster,
			'FIND_PORT_MANUALY':				self.StateFindPortManualy,
			'GET_MASTER_INFO':					self.StateGetMasterInfo,
			'GET_PORT': 						self.StateGetPort,
			'WAIT_FOR_PORT':					self.StateWaitForPort,
			'START_LISTENER':					self.StateStartListener,
			'WORKING':							self.StateWorking,
			'EXIT':								self.StateExit
		}
		# Handlers
		self.NodeResponseHandlers['get_port'] 			= self.GetPortResponseHandler
		#self.ResponseHandlers	= {
		#	'get_local_nodes': 						self.GetLocalNodeResponseHandler,
		#	'get_master_info': 						self.GetMasterInfoResponseHandler,
		#	'set_sensor_info': 						self.SetSensorInfoResponseHandler,
		#	'get_node_info':						self.GetNodeInfoHandler,
		#	'undefined':							self.UndefindHandler
		#}
		#self.RequestHandlers	= {
		#	'set_sensor_info': 						self.SetSensorInfoRequestHandler,
		#	'upload_file':							self.UploadFileHandler,
		#	'exit':									self.ExitHandler,
		#	'undefined':							self.UndefindHandler
		#}
		# Callbacks
		self.OnGetNodeInfoCallback 					= None
		self.OnGetSensorInfoRequestCallback			= None
		self.OnSetSensorInfoRequestCallback 		= None
		self.OnUploadFileRequestCallback 			= None
		# Flags
		self.IsListenerEnabled 						= False
		# Counters
		self.MasterConnectionTries 					= 0
		self.MasterInformationTries 				= 0
		self.MasterTickTimeout 						= 1

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
			if self.MasterSocket is None:
				pass
			else:
				self.AppendTXRequest(self.MasterSocket, packet)
				#self.MasterSocket.send(packet)
		else:
			self.SetState("CONNECT_MASTER")

	def StateConnectMaster(self):
		if 0 == self.Ticker % self.MasterTickTimeout:
			if self.MasterConnectionTries > 3:
				# self.SetState("EXIT")
				self.SetState("FIND_PORT_MANUALY")
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
				# self.SetState("EXIT")
				self.SetState("FIND_PORT_MANUALY")
			else:
				print ("({classname})# Send get_node_info request ...".format(classname=self.ClassName))
				# Send request
				message = self.BasicProtocol.BuildRequest("DIRECT", "MASTER", self.UUID, "get_node_info", {}, {})
				packet  = self.BasicProtocol.AppendMagic(message)
				if self.MasterSocket is None:
					pass
				else:
					self.AppendTXRequest(self.MasterSocket, packet)
					#self.MasterSocket.send(packet)
				self.MasterInformationTries += 1

	def StateGetPort(self):
		print ("({classname})# Sending get_port request ...".format(classname=self.ClassName))
		# Send request
		message = self.BasicProtocol.BuildRequest("DIRECT", self.MasterUUID, self.UUID, "get_port", self.NodeInfo, {})
		packet  = self.BasicProtocol.AppendMagic(message)
		if self.MasterSocket is None:
			pass
		else:
			self.AppendTXRequest(self.MasterSocket, packet)
			#self.MasterSocket.send(packet)
		self.SetState("WAIT_FOR_PORT")
	
	def StateFindPortManualy(self):
		print ("({classname})# Trying to find port manualy ...".format(classname=self.ClassName))
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

	def StateWaitForPort(self):
		if 0 == self.Ticker % 20:
			if 0 == self.SlaveListenerPort:
				self.SetState("GET_PORT")
			else:
				self.SetState("START_LISTENER")

	def StateStartListener(self):
		print ("({classname})# Trying to start listener ...".format(classname=self.ClassName))
		self.ServerAdderss = ('', self.SlaveListenerPort)
		status = self.TryStartListener()
		if status is True:
			self.IsListenerEnabled = True
			if self.IsLocalUIEnabled is True:
				self.LocalWSManager.RunServer()
			self.SetState("WORKING")
	
	def StateWorking(self):
		if self.SystemLoaded is False:
			self.SystemLoaded = True # Update node that system done loading.
			if self.NodeSystemLoadedCallback is not None:
				self.NodeSystemLoadedCallback()
		
		if 0 == self.Ticker % 60:
			self.SendGatewayPing()

	def StateExit(self):
		self.Exit("Exit state initiated")

	#
	# ###### SLAVE NODE STATES <-
	#

	#
	# ###### SLAVE NODE GATAWAY CALLBACKS ->
	#

	def GetNodeInfoRequestHandler(self, sock, packet):
		print ("({classname})# Node Info Request ...".format(classname=self.ClassName))
		payload = self.NodeInfo
		payload["is_master"] 	= False
		payload["master_uuid"] 	= self.MasterUUID
		return self.BasicProtocol.BuildResponse(packet, payload)

	def GetNodeInfoResponseHandler(self, sock, packet):
		source  	= self.BasicProtocol.GetSourceFromJson(packet)
		payload 	= self.BasicProtocol.GetPayloadFromJson(packet)
		additional 	= self.BasicProtocol.GetAdditionalFromJson(packet)
		print ("({classname})# Node Info Response ...".format(classname=self.ClassName))
		if source in "MASTER":
			# We are here because this is a response for slave boot sequence
			self.MasterInfo = payload
			self.MasterUUID = payload["uuid"]
			if self.GetState() in "GET_MASTER_INFO":
				self.SetState("GET_PORT")
		else:
			if self.OnGetNodeInfoCallback is not None:
				self.OnGetNodeInfoCallback(payload, additional["online"])
	
	def GetPortResponseHandler(self, sock, packet):
		source  = self.BasicProtocol.GetSourceFromJson(packet)
		payload = self.BasicProtocol.GetPayloadFromJson(packet)

		if source in self.MasterUUID:
			self.SlaveListenerPort = payload["port"]
			self.SetState("START_LISTENER")

	#
	# ###### SLAVE NODE GATAWAY CALLBACKS <-
	#

	def SendRequest(self, uuid, msg_type, command, payload, additional):
		# Generate request
		message = self.BasicProtocol.BuildRequest(msg_type, uuid, self.UUID, command, payload, additional)
		packet  = self.BasicProtocol.AppendMagic(message)
		if self.MasterSocket is None:
			pass
			# TODO - Send over local websocket
		else:
			self.AppendTXRequest(self.MasterSocket, packet)
			#self.MasterSocket.send(packet)

	def EmitOnNodeChange(self, data):
		# print ("({classname})# Emit onNodeChange event ...".format(classname=self.ClassName))
		self.DeviceChangeListLock.acquire()
		for item in self.OnDeviceChangeList:
			payload 	= item["payload"]
			item_type	= payload["item_type"]

			# Node
			if item_type == 1:
				uuid = payload["uuid"]
				message = self.BasicProtocol.BuildRequest("DIRECT", uuid, self.UUID, "on_node_change", data, {})
				packet  = self.BasicProtocol.AppendMagic(message)
				if self.MasterSocket is None:
					pass
				else:
					self.AppendTXRequest(self.MasterSocket, packet)
					#self.MasterSocket.send(packet)
			# Webface
			elif item_type == 2:
				if payload["pipe"] == "GATEWAY":
					webface_indexer = payload["webface_indexer"]
					message = self.BasicProtocol.BuildRequest("DIRECT", "WEBFACE", self.UUID, "on_node_change", data, {
						'identifier':-1,
						'webface_indexer':webface_indexer
					})

					packet  = self.BasicProtocol.AppendMagic(message)
					if self.MasterSocket is None:
						pass
					else:
						self.AppendTXRequest(self.MasterSocket, packet)
						#self.MasterSocket.send(packet)
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

		if self.MasterSocket is None:
			pass
		else:
			print ("({classname})# Sending ping request ...".format(classname=self.ClassName))
			self.AppendTXRequest(self.MasterSocket, packet)
			#self.MasterSocket.send(packet)
	
	def PreUILoaderHandler(self):
		print ("({classname})# PreUILoaderHandler ...".format(classname=self.ClassName))
		port = 8000 + (self.ServerAdderss[1] - 10000)
		self.InitiateLocalServer(port)
		# UI RestAPI
		self.UI.AddEndpoint("/get/node_widget/<key>",		"get_node_widget",	self.GetNodeWidgetHandler)
		self.UI.AddEndpoint("/get/node_config/<key>",		"get_node_config",	self.GetNodeConfigHandler)
	
	def NodeDisconnectHandler(self, sock):
		print ("({classname})# [NodeDisconnectHandler]".format(classname=self.ClassName))
		# Check if disconneced connection is a master.
		for node in self.MasterNodesList:
			if sock == node.Socket:
				self.MasterNodesList.remove(node)
				# Need to close listener port because we are going to get this port again
				self.ServerSocket.close()
				# If master terminated we need to close node.
				self.SetState("CONNECT_MASTER")
				self.MasterSocket = None
				if self.OnMasterDisconnectedCallback is not None:
					self.OnMasterDisconnectedCallback()
	
	def GetMasters(self):
		return self.MasterNodesList
	
	#
	# ############################################################################################
	#
	
	def GetNodeInfoHandler(self, sock, packet):
		if self.OnGetNodeInfoCallback is not None:
			self.OnGetNodeInfoCallback(packet)

	# TODO - Implement this method.
	def GetNodeStatusRequestHandler(self, sock, packet):
		pass

	def GetNodeStatusRequestHandler(self, sock, packet):
		pass
	
	def GetNodeStatusResponseHandler(self, sock, packet):
		if self.OnApplicationResponseCallback is not None:
			self.OnApplicationResponseCallback(sock, packet)
	
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
	# TODO - NO master change.
	def SendSensorInfoChange(self, sensors):
		json = self.Commands.GenerateJsonProxyRequest(self.UUID, "WEBFACE", "get_sensor_info", {})
		msg  = self.Commands.ProxyResponse(json, sensors)
		if self.MasterSocket is None:
			pass
		else:
			self.AppendTXRequest(self.MasterSocket, packet)
			#self.MasterSocket.send(msg)
	
	def GetListOfNodeFromGateway(self):
		print ("[SlaveNode] GetListOfNodeFromGateway")
		payload = self.Commands.SendListOfNodesRequest("GATEWAY", self.UUID)
		if self.MasterSocket is None:
			pass
		else:
			self.AppendTXRequest(self.MasterSocket, packet)
			#self.MasterSocket.send(payload)
	
	# TODO - NO master change.
	def GetNodeInfo(self, uuid):
		print ("[SlaveNode] GetNodeInfo")
		payload = self.Commands.NodeInfoRequest(uuid, self.UUID)
		if self.MasterSocket is None:
			pass
		else:
			self.AppendTXRequest(self.MasterSocket, packet)
			#self.MasterSocket.send(payload)

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

	def NodeMasterAvailable(self, sock):
		print ("NodeMasterAvailable")
		# Append new master to the list
		conn = self.GetNodeBySock(sock)
		# TODO - Check if we don't have this connection already
		self.MasterNodesList.append(conn)
		# Get Master slave nodes.
		packet = self.CommandsGetLocalNodes()
		self.AppendTXRequest(sock, packet)
		#sock.send(packet)

	def GetLocalNodeResponseHandler(self, sock, packet):
		pass

	def GetMasterInfoResponseHandler(self, sock, packet):
		pass

	def GetSensorInfoResponseHandler(self, sock, packet):
		pass

	def SetSensorInfoResponseHandler(self, sock, packet):
		pass

	def UploadFileHandler(self, sock, packet):
		if self.OnUploadFileRequestCallback is not None:
			self.OnUploadFileRequestCallback(packet, sock)

	def ExitHandler(self, sock, packet):
		if self.OnExitCallback is not None:
			self.OnExitCallback()
			packet = self.Commands.ExitResponse("OK")
			self.AppendTXRequest(sock, packet)
			#sock.send(packet)
			
