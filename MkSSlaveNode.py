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
		self.OnGetNodeInfoRequestCallback 			= None
		# Flags
		self.IsListenerEnabled 						= False
		# Counters
		self.MasterConnectionTries 					= 0
		self.Ticker 								= 0

		self.ChangeState("IDLE")

	# GET_NODE_INFO
	def GetNodeInfoRequestHandler(self, sock, packet):
		print "[DEBUG SLAVE] GetNodeInfoHandler"
		if self.OnGetNodeInfoRequestCallback is not None:
			self.OnGetNodeInfoRequestCallback(sock, packet)

	def GetNodeStatusRequestHandler(self, sock, packet):
		pass
		
	def GetNodeInfoResponseHandler(self, sock, packet):
		pass
	
	def GetNodeStatusResponseHandler(self, sock, packet):
		pass
	# ############

	def SendGatewayPing(self):
		payload = self.Commands.SendPingRequest("GATEWAY", self.UUID)
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
		print "StateIdle"
		self.ConnectMaster()

	def StateConnectMaster(self):
		print "StateConnectMaster"
		if 0 == self.Ticker % 20:
			if self.MasterConnectionTries > 3:
				self.ChangeState("EXIT")

			self.ConnectMaster()
			self.MasterConnectionTries += 1

	def StateGetPort(self):
		print "StateGetPort"
		payload = self.Commands.GetPortRequest(self.UUID, self.Type)
		self.MasterSocket.send(payload)
		self.ChangeState("WAIT_FOR_PORT")

	def SendSensorInfoResponse(self, sock, packet, sensors):
		direction = packet["direction"]
		if ("proxy" in direction):
			print " P R O X Y "
			msg = self.Commands.ProxyResponse(packet, sensors)
			sock.send(msg)
		else:
			print " R E G U L A R"

		#payload = self.Commands.GetSensorInfoResponse(self.UUID, sensors)
		#sock.send(payload)

	def StateWaitForPort(self):
		print "StateWaitForPort"
		if 0 == self.Ticker % 20:
			if 0 == self.SlaveListenerPort:
				self.ChangeState("GET_PORT")
			else:
				self.ChangeState("START_LISTENER")

	def StateStartListener(self):
		print "StateStartListener"
		self.ServerAdderss = ('', self.SlaveListenerPort)
		status = self.TryStartListener()
		if True == status:
			self.IsListenerEnabled = True
			self.ChangeState("WORKING")

	def StateWorking(self):
		if 0 == self.Ticker % 30:
			self.SendGatewayPing()

	def StateExit(self):
		print "StateExit"
		pass

	# TODO - Master and Slave have same HandleRouter, consider moving to abstruct class
	def HandlerRouter(self, sock, data):
		jsonData 	= json.loads(data)
		command 	= jsonData['command']
		direction 	= jsonData['direction']

		# TODO - IF command type is not in list call unknown callback in user code.
		if "response" == direction:
			if command in self.ResponseHandlers:
				self.ResponseHandlers[command](sock, jsonData)
		elif "request" == direction:
			if command in self.RequestHandlers:
				self.RequestHandlers[command](sock, jsonData)
		elif "proxy_request" == direction:
			if command in self.RequestHandlers:
				self.RequestHandlers[command](sock, jsonData)
		elif "proxy_response" == direction:
			if command in self.ResponseHandlers:
				self.ResponseHandlers[command](sock, jsonData)

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
			
