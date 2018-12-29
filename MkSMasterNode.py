#!/usr/bin/python
import os
import sys
import json
import time
import thread
import threading
import socket
import subprocess
from subprocess import call

from mksdk import MkSFile
from mksdk import MkSAbstractNode
from mksdk import MkSLocalNodesCommands
from mksdk import MkSShellExecutor

class LocalPipe():
	def __init__(self, uuid, pipe):
		self.Uuid 	= uuid
		self.Pipe 	= pipe
		self.Buffer = []

	def ReadToBuffer(self):
		if (len(self.Buffer) > 20):
			self.Buffer = []
		self.Buffer.append(self.Pipe.stdout.readline())

	def ReadBuffer(self):
		return self.Buffer

	def IsPipeError(self):
		return self.Pipe.returncode is not None

	def GetError(self):
		return self.Pipe.returncode

class LocalNode():
	def __init__(self, ip, port, uuid, node_type, sock):
		self.IP 		= ip
		self.Port 		= port
		self.UUID 		= uuid
		self.Socket 	= sock
		self.Type 		= node_type
		self.LocalType 	= "UNKNOWN"
		self.Status 	= "Stopped"
		self.Obj 		= None

class MasterNode(MkSAbstractNode.AbstractNode):
	def __init__(self):
		MkSAbstractNode.AbstractNode.__init__(self)
		# Members
		self.File 							= MkSFile.File()
		self.Commands 						= MkSLocalNodesCommands.LocalNodeCommands()
		self.Terminal 						= MkSShellExecutor.ShellExecutor()
		self.PortsForClients				= [1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32]
		self.MasterHostName					= socket.gethostname()
		self.MasterVersion					= "1.0.1"
		self.PackagesList					= ["Gateway","LinuxTerminal","USBManager"] # Default Master capabilities.
		self.LocalSlaveList					= [] # Used ONLY by Master.
		self.InstalledNodes 				= []
		self.Pipes 							= []
		self.InstalledApps 					= None
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
		self.PipeStdoutRun					= False

		self.ChangeState("IDLE")
		self.LoadNodesOnMasterStart()
		self.OnAceptNewConnectionCallback   = self.OnAceptNewConnectionHandler

		thread.start_new_thread(self.PipeStdoutListener, ())
		
	def LoadNodesOnMasterStart(self):
		jsonInstalledNodesStr 	= self.File.LoadStateFromFile("../../configure/installed_nodes.json")
		jsonData 				= json.loads(jsonInstalledNodesStr)

		jsonInstalledAppsStr 	= self.File.LoadStateFromFile("../../configure/installed_apps.json")
		self.InstalledApps		= json.loads(jsonInstalledAppsStr)

		for item in jsonData["installed"]:
			if 1 == item["type"]:
				node = LocalNode("", 16999, item["uuid"], item["type"], None)
				node.Status = "Running"
			else:
				node = LocalNode("", 0, item["uuid"], item["type"], None)
			self.InstalledNodes.append(node)

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

				# Update installed node list (UI will be updated)
				for item in self.InstalledNodes:
					print item.UUID + "<?>" + node.UUID
					if item.UUID == node.UUID:
						item.IP 	= node.IP
						item.Port 	= node.Port
						item.Status = "Running"

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

				# Update installed node list (UI will be updated)
				for item in self.InstalledNodes:
					if item.UUID == slave.UUID:
						item.IP 	= ""
						item.Port 	= 0
						item.Status = "Stopped"

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

	def OnAceptNewConnectionHandler(self, conn):
		pass

	def GetSlaveNode(self, uuid):
		for item in self.LocalSlaveList:
			if item.UUID == uuid:
				return item
		return None

	def GetInstalledNodes(self):
		return self.InstalledNodes

	def ExitRemoteNode(self, uuid):
		node = self.GetNodeByUUID(uuid)
		if node is not None:
			payload = self.Commands.ExitRequest()
			node.Socket.send(payload)
			# Remove pipe (note better to do it on response of exit command)
			for item in self.Pipes:
				if item.Uuid == uuid:
					self.Pipes.remove(item)
					return

	def GetShellScreen(self, uuid):
		for item in self.Pipes:
			if item.Uuid == uuid:
				return item.ReadBuffer()

	def PipeStdoutListener(self):
		self.PipeStdoutRun = True
		while True == self.PipeStdoutRun:
			for item in self.Pipes:
				if item.IsPipeError():
					print str(item.GetError())
				item.ReadToBuffer()
			time.sleep(0.5)

	def StartRemoteNode(self, uuid):
		path = "/home/yevgeniy/workspace/makesense/mksnodes/1981"
		proc = subprocess.Popen(["python", '-u', "../1981/1981.py", "--path", path], stdout=subprocess.PIPE)

		pipe = LocalPipe(uuid, proc)
		self.Pipes.append(pipe)

	def ExitRoutine(self):
		self.Terminal.Stop()