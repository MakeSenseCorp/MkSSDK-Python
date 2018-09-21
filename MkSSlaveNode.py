#!/usr/bin/python
import os
import sys
import json
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
			'undefined':							self.UndefindHandler
		}
		# Callbacks
		self.LocalServerDataArrivedCallback			= None
		self.OnGetLocalNodesResponeCallback 		= None
		self.OnGetMasterInfoResponseCallback		= None
		self.OnMasterAppendNodeResponseCallback		= None
		self.OnMasterRemoveNodeResponseCallback 	= None
		self.OnGetSensorInfoResponseCallback 		= None
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
			# Save socket as master socket
			self.MasterSocket = sock
		else:
			self.ChangeState("CONNECT_MASTER")

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
		payload = self.Commands.GetPort(self.UUID, self.Type)
		self.MasterSocket.send(payload)
		self.ChangeState("WAIT_FOR_PORT")

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
		jsonData 	= json.loads(data)
		command 	= jsonData['command']
		direction 	= jsonData['direction']

		if command in self.ResponseHandlers:
			if "response" == direction:
				self.ResponseHandlers[command](jsonData)
		elif command in self.RequestHandlers:
			pass

	def NodeConnectHandler(self, conn, addr):
		pass

	def NodeDisconnectHandler(self, sock):
		# If disconnected socket is master, slave need to find 
		# a master again and send request for port.
		pass

	def NodeMasterAvailable(self, sock):
		# Get Master slave nodes.
		packet = self.CommandsGetLocalNodes()
		sock.send(packet)


	def GetLocalNodeResponseHandler(self):
		pass

	def GetMasterInfoResponseHandler(self):
		pass

	def GetSensorInfoResponseHandler(self):
		pass

	def SetSensorInfoResponseHandler(self):
		pass

	def GetSensorInfoRequestHandler(self):
		pass

	def SetSensorInfoRequestHandler(self):
		pass

	def GetPortResponseHandler(self, json_data):
		self.SlaveListenerPort = json_data["port"]
		self.ChangeState("START_LISTENER")
		# Raise event

	def UndefindHandler(self):
		pass
