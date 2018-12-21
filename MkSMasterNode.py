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

class MasterNode(MkSAbstractNode.AbstractNode):
	def __init__(self):
		MkSAbstractNode.AbstractNode.__init__(self)
		# Members
		self.Commands 						= MkSLocalNodesCommands.LocalNodeCommands()
		self.PortsForClients				= [1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32]
		self.MasterHostName					= socket.gethostname()
		self.MasterVersion					= "1.0.1"
		self.PackagesList					= ["Gateway","LinuxTerminal","USBManager"] # Default Master capabilities.
		self.LocalSlaveList					= [] # Used ONLY by Master.
		# Sates
		self.States = {
			'IDLE': 						self.StateIdle,
			'WORKING': 						self.StateWorking
		}
		# Handlers
		self.RequestHandlers				= {
			'get_port': 					self.GetPortRequestHandler,
			'get_local_nodes': 				self.GetLocalNodesRequestHandler,
			'get_master_info':				self.GetMasterInfoRequestHandler
		}
		self.ResponseHandlers 				= {
		}
		# Flags
		self.IsListenerEnabled 				= False

		self.ChangeState("IDLE")

	def StateIdle (self):
		self.ServerAdderss = ('', 16999)
		status = self.TryStartListener()
		if True == status:
			self.IsListenerEnabled = True
			self.ChangeState("WORKING")
		time.sleep(1)

	def StateWorking(self):
		if 0 == self.Ticker % 20:
			pass

	def GetPortRequestHandler(self, json_data, sock):
		nodeType = json_data['type']
		uuid = json_data['uuid']
		# Do we have available port.
		if self.PortsForClients:
			node = self.GetConnection(sock)
			existingSlave = None
			for slave in self.LocalSlaveList:
				if slave.UUID == node.UUID:
					existingSlave = slave
					continue
			if None == existingSlave:
				# New request
				port = 10000 + self.PortsForClients.pop()
				# Update node
				node.Type = nodeType
				node.Port = port
				node.UUID = uuid

				# Send message to all nodes.
				paylod = self.Commands.MasterAppendNodeResponse(node.IP, port, node.UUID, nodeType)
				for client in self.Connections:
					if client.Socket == self.ServerSocket:
						pass
					else:
						client.Socket.send(paylod)
				self.LocalSlaveList.append(node)
				payload = self.Commands.GetPortResponse(port)
				print payload
				sock.send(payload)
			else:
				# Already assigned port (resending)
				payload = self.Commands.GetPortResponse(node.Port)
				sock.send(payload)
		else:
			# No available ports
			payload = self.Commands.GetPortResponse(0)
			sock.send(payload)

	def GetLocalNodesRequestHandler(self, json_data, sock):
		nodes = ""
		if self.LocalSlaveList:
			for node in self.LocalSlaveList:
				nodes += "{\"ip\":\"" + str(node.IP) + "\",\"port\":" + str(node.Port) + ",\"uuid\":\"" + node.UUID + "\",\"type\":" + str(node.Type) + "},"
			nodes = nodes[:-1]
		payload = self.Commands.GetLocalNodesResponse(nodes)
		sock.send(payload)

	def GetMasterInfoRequestHandler(self, json_data, sock):
		nodes = ""
		if self.LocalSlaveList:
			for node in self.LocalSlaveList:
				nodes += "{\"ip\":\"" + str(node.IP) + "\",\"port\":" + str(node.Port) + ",\"uuid\":\"" + node.UUID + "\",\"type\":" + str(node.Type) + "},"
			nodes = nodes[:-1]
		payload = self.Commands.GetMasterInfoResponse(self.UUID, self.MasterHostName, nodes)
		sock.send(payload)

	def HandlerRouter(self, sock, data):
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

	def NodeDisconnectHandler(self, sock):
		print "NodeDisconnectHandler"
		for slave in self.LocalSlaveList:
			if slave.Socket == sock:
				self.PortsForClients.append(slave.Port - 10000)
				payload = self.Commands.MasterAppendNodeResponse(slave.IP, slave.Port, slave.UUID, slave.Type)
				# Send to all nodes
				for client in self.Connections:
					if client.Socket == self.ServerSocket:
						pass
					else:
						if client.Socket is not None:
							client.Socket.send(payload)
				self.LocalSlaveList.remove(slave)
				continue

	def GetSlaveNode(self, uuid):
		for item in self.LocalSlaveList:
			if item.UUID == uuid:
				return item
		return None

	def ExitRemoteNode(self, uuid):
		node = self.GetNodeByUUID(uuid)
		if node is not None:
			payload = self.Commands.ExitRequest()
			node.Socket.send(payload)

	def StartRemoteNode(type, uuid):
		pass