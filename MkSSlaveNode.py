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
		self.Commands 						= MkSLocalNodesCommands.LocalNodeCommands()
		self.MasterNodesList				= [] # For future use (slave to slave communication)
		self.SlaveListenerPort 				= 0
		self.MasterSocket					= None
		# Sates
		self.States = {
			'IDLE': 						self.StateIdle,
			'CONNECT_MASTER':				self.StateConnectMaster,
			'GET_PORT': 					self.StateGetPort,
			'WAIT_FOR_PORT':				self.StateWaitForPort,
			'START_LISTENER':				self.StateStartListener,
			'WORKING':						self.StateWorking,
			'EXIT':							self.StateExit
		}
		# Handlers
		# Response - Handler when rresponse returned to slave (slave is a requestor)
		self.ResponseHandlers	= {
			'get_local_nodes': 						self.GetLocalNodeResponseHandler,
			'get_master_info': 						self.GetMasterInfoResponseHandler,
			'get_sensor_info': 						self.GetSensorInfoResponseHandler,
			'set_sensor_info': 						self.SetSensorInfoResponseHandler,
			'get_port':								self.GetPortResponseHandler,
			'undefined':							self.UndefindHandler
		}
		# Request - Response handler to sent request.
		self.RequestHandlers	= {
			'get_sensor_info': 						self.GetSensorInfoRequestHandler,
			'set_sensor_info': 						self.SetSensorInfoRequestHandler,
			'get_file':								self.GetFileHandler,
			'upload_file':							self.UploadFileHandler,
			'exit':									self.ExitHandler,
			'undefined':							self.UndefindHandler
		}
		# Callbacks
		self.LocalServerDataArrivedCallback			= None
		self.OnGetLocalNodesResponeCallback 		= None
		self.OnGetMasterInfoResponseCallback		= None
		self.OnMasterAppendNodeResponseCallback		= None
		self.OnMasterRemoveNodeResponseCallback 	= None
		self.OnGetSensorInfoResponseCallback 		= None

		self.OnGetSensorInfoRequestCallback			= None
		self.OnSetSensorInfoRequestCallback 		= None
		self.OnUploadFileRequestCallback 			= None
		self.OnCustomCommandRequestCallback			= None
		self.OnCustomCommandResponseCallback		= None
		self.OnGetNodeInfoRequestCallback 			= None
		# Flags
		self.IsListenerEnabled 						= False
		# Counters
		self.MasterConnectionTries 					= 0
		self.Ticker 								= 0

		self.ChangeState("IDLE")

	def GetFileHandler(self, sock, packet):
		print ("[SlaveNode] GetFileHandler")

		objFile 	= MkSFile.File()
		uiType 		= packet["payload"]["data"]["ui_type"]
		fileType 	= packet["payload"]["data"]["file_type"]
		fileName 	= packet["payload"]["data"]["file_name"]

		folder = {
			'config': 		'config',
			'app': 			'app',
			'thumbnail': 	'thumbnail'
		}

		path = os.path.join(".","ui",folder[uiType],"ui." + fileType)
		print path
		content = objFile.LoadStateFromFile(path)
		
		payload = {
			'file_type': fileType,
			'ui_type': uiType,
			'content': content.encode('hex')
		}
		
		msg = self.Commands.ProxyResponse(packet, payload)
		self.MasterSocket.send(msg)

	# GET_NODE_INFO
	def GetNodeInfoRequestHandler(self, sock, packet):
		print ("[SlaveNode] GetNodeInfoHandler")
		if self.OnGetNodeInfoRequestCallback is not None:
			self.OnGetNodeInfoRequestCallback(sock, packet)

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
		js = objFile.LoadStateFromFile("static/js/node/widget.js")
		return js

	def GetNodeConfigHandler(self, key):
		print ("[SlaveNode]# GetNodeConfigHandler", self.Pwd + "static/js/node/widget_config.js")
		objFile = MkSFile.File()
		js = objFile.LoadStateFromFile("static/js/node/widget_config.js")
		return js
	"""
	Local Face RESP API methods
	"""
	def SendSensorInfoChange(self, sensors):
		json = self.Commands.GenerateJsonProxyRequest(self.UUID, "WEBFACE", "get_sensor_info", {})
		msg  = self.Commands.ProxyResponse(json, sensors)
		self.MasterSocket.send(msg)

	def SendGatewayPing(self):
		print ("[SlaveNode] SendGatewayPing")
		payload = self.Commands.SendPingRequest("GATEWAY", self.UUID)
		# self.MasterSocket.send(payload)
	
	def GetListOfNodeFromGateway(self):
		print ("[SlaveNode] GetListOfNodeFromGateway")
		payload = self.Commands.SendListOfNodesRequest("GATEWAY", self.UUID)
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
			self.ChangeState("GET_PORT")
			self.MasterNodesList.append(node)
			if self.OnMasterFoundCallback is not None:
				self.OnMasterFoundCallback([sock, self.MyLocalIP])
			# Save socket as master socket
			self.MasterSocket = sock
		else:
			self.ChangeState("CONNECT_MASTER")
			time.sleep(5)

	def StateIdle(self):
		# Init state logic must be here.
		print ("StateIdle")
		self.ConnectMaster()

	def StateConnectMaster(self):
		print ("StateConnectMaster")
		if 0 == self.Ticker % 20:
			if self.MasterConnectionTries > 3:
				self.ChangeState("EXIT")

			self.ConnectMaster()
			self.MasterConnectionTries += 1

	def StateGetPort(self):
		print ("StateGetPort")
		payload = self.Commands.GetPortRequest(self.UUID, self.Type)
		self.MasterSocket.send(payload)
		self.ChangeState("WAIT_FOR_PORT")
	
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

	def StateWaitForPort(self):
		print ("StateWaitForPort")
		if 0 == self.Ticker % 20:
			if 0 == self.SlaveListenerPort:
				self.ChangeState("GET_PORT")
			else:
				self.ChangeState("START_LISTENER")

	def StateStartListener(self):
		print ("StateStartListener")
		self.ServerAdderss = ('', self.SlaveListenerPort)
		status = self.TryStartListener()
		if True == status:
			self.IsListenerEnabled = True
			self.ChangeState("WORKING")

	def StateWorking(self):
		if 0 == self.Ticker % 30:
			self.SendGatewayPing()

	def StateExit(self):
		print ("StateExit")

	# INBOUND
	def HandlerRouter_Request(self, sock, json_data):
		command = json_data['command']
		# TODO - IF command type is not in list call unknown callback in user code.
		if command in self.RequestHandlers:
			self.RequestHandlers[command](sock, json_data)
		else:
			if self.OnCustomCommandRequestCallback is not None:
				self.OnCustomCommandRequestCallback(sock, json_data)

	# OUTBOUND
	def HandlerRouter_Response(self, sock, json_data):
		command = json_data['command']
		# TODO - IF command type is not in list call unknown callback in user code.
		if command in self.ResponseHandlers:
			self.ResponseHandlers[command](sock, json_data)
		else:
			if self.OnCustomCommandResponseCallback is not None:
				self.OnCustomCommandResponseCallback(sock, json_data)

	# TODO - Master and Slave have same HandleRouter, consider moving to abstruct class
	def HandlerRouter(self, sock, data):
		jsonData 	= json.loads(data)
		direction 	= jsonData['direction']

		if direction in ["response", "proxy_response"]:
			self.HandlerRouter_Response(sock, jsonData)
		elif direction in ["request", "proxy_request"]:
			self.HandlerRouter_Request(sock, jsonData)

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

	def GetPortResponseHandler(self, sock, packet):
		self.SlaveListenerPort = packet["port"]
		self.ChangeState("START_LISTENER")
		# Raise event

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
			
