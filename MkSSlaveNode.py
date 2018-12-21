#!/usr/bin/python
import os
import sys
import json
import time
import thread
import threading
import socket

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
		self.ResponseHandlers	= {
			'get_local_nodes': 						self.GetLocalNodeResponseHandler,
			'get_master_info': 						self.GetMasterInfoResponseHandler,
			'get_sensor_info': 						self.GetSensorInfoResponseHandler,
			'set_sensor_info': 						self.SetSensorInfoResponseHandler,
			'get_port':								self.GetPortResponseHandler,
			'undefined':							self.UndefindHandler
		}
		self.RequestHandlers	= {
			'get_sensor_info': 						self.GetSensorInfoRequestHandler,
			'set_sensor_info': 						self.SetSensorInfoRequestHandler,
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
		# Flags
		self.IsListenerEnabled 						= False
		# Counters
		self.MasterConnectionTries 					= 0

		self.ChangeState("IDLE")

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
		self.ConnectMaster()

	def StateConnectMaster(self):
		if 0 == self.Ticker % 20:
			if self.MasterConnectionTries > 3:
				self.ChangeState("EXIT")

			self.ConnectMaster()
			self.MasterConnectionTries += 1

	def StateGetPort(self):
		payload = self.Commands.GetPortRequest(self.UUID, self.Type)
		self.MasterSocket.send(payload)
		self.ChangeState("WAIT_FOR_PORT")

	def SendSensorInfoResponse(self, sock, sensors):
		payload = self.Commands.GetSensorInfoResponse(self.UUID, sensors)
		sock.send(payload)

	def StateWaitForPort(self):
		if 0 == self.Ticker % 20:
			if 0 == self.SlaveListenerPort:
				self.ChangeState("GET_PORT")
			else:
				self.ChangeState("START_LISTENER")

	def StateStartListener(self):
		self.ServerAdderss = ('', self.SlaveListenerPort)
		status = self.TryStartListener()
		if True == status:
			self.IsListenerEnabled = True
			self.ChangeState("WORKING")

	def StateWorking(self):
		pass

	def StateExit(self):
		pass

	def HandlerRouter(self, sock, data):
		print data
		jsonData 	= json.loads(data)
		command 	= jsonData['command']
		direction 	= jsonData['direction']

		# TODO - IF command type is not in list call unknown callback in user code.
		if "response" == direction:
			if command in self.ResponseHandlers:
				self.ResponseHandlers[command](jsonData)
		elif "request" == direction:
			if command in self.RequestHandlers:
				self.RequestHandlers[command](jsonData, sock)

	# Only used for socket listening.
	def NodeConnectHandler(self, conn, addr):
		pass

	def NodeDisconnectHandler(self, sock):
		print "NodeDisconnectHandler"
		# Check if disconneced connection is a master.
		for node in self.MasterNodesList:
			if sock == node.Socket:
				self.MasterNodesList.remove(node)
				# If master terminated we need to close node.
				self.ChangeState("CONNECT_MASTER")
				if self.OnMasterDisconnectedCallback is not None:
					self.OnMasterDisconnectedCallback()

	def NodeMasterAvailable(self, sock):
		print "NodeMasterAvailable"
		# Append new master to the list
		conn = self.GetConnection(sock)
		# TODO - Check if we don't have this connection already
		self.MasterNodesList.append(conn)
		# Get Master slave nodes.
		packet = self.CommandsGetLocalNodes()
		sock.send(packet)

	# RESPONSE Handlers >

	def GetLocalNodeResponseHandler(self):
		pass

	def GetMasterInfoResponseHandler(self):
		pass

	def GetSensorInfoResponseHandler(self):
		pass

	def SetSensorInfoResponseHandler(self):
		pass

	def GetPortResponseHandler(self, json_data):
		self.SlaveListenerPort = json_data["port"]
		self.ChangeState("START_LISTENER")
		# Raise event

	# RESPONSE Handlers <
	# REQUEST Handlers <

	def GetSensorInfoRequestHandler(self, json_data, sock):
		if self.OnGetSensorInfoRequestCallback is not None:
			self.OnGetSensorInfoRequestCallback(json_data, sock)

	def SetSensorInfoRequestHandler(self, json_data, sock):
		if self.OnSetSensorInfoRequestCallback is not None:
			self.OnSetSensorInfoRequestCallback(json_data, sock)

	# REQUEST Handlers <	

	def UndefindHandler(self, data, sock):
		if None is not self.LocalServerDataArrivedCallback:
			self.LocalServerDataArrivedCallback(data, sock)

	def GetMasters(self):
		return self.MasterNodesList

	def ExitHandler(self, json_data, sock):
		if self.OnExitCallback is not None:
			self.OnExitCallback()
			packet = self.Commands.ExitResponse("OK")
			sock.send(packet)
			
