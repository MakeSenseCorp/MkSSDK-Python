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
import Queue

from flask import Flask, render_template, jsonify, Response, request
import logging

import MkSGlobals
from mksdk import MkSFile
from mksdk import MkSNetMachine
from mksdk import MkSAbstractNode
from mksdk import MkSShellExecutor
from mksdk import MkSLogger

# TODO - Remove this class from here.
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

class MasterNode(MkSAbstractNode.AbstractNode):
	def __init__(self):
		MkSAbstractNode.AbstractNode.__init__(self)
		self.ClassName 							= "Master Node"
		# Members
		self.Terminal 							= MkSShellExecutor.ShellExecutor()
		self.PortsForClients					= [item for item in range(1,33)]
		self.MasterHostName						= socket.gethostname()
		self.MasterVersion						= "1.0.1"
		self.PackagesList						= ["Gateway","LinuxTerminal"] # Default Master capabilities.
		self.LocalSlaveList						= [] # Used ONLY by Master.
		self.InstalledNodes 					= []
		self.Pipes 								= []
		self.IsMaster 							= True
		self.InstalledApps 						= None
		self.IsLocalUIEnabled					= False
		# Queue
		self.GatewayRXQueueLock      	    	= threading.Lock()
		self.GatewayRXQueue						= Queue.Queue()
		self.GatewayRXWorkerRunning 			= False
		self.GatewayTXQueueLock      	    	= threading.Lock()
		self.GatewayTXQueue						= Queue.Queue()
		self.GatewayTXWorkerRunning 			= False
		# Debug & Logging
		self.DebugMode							= True
		# Node connection to WS information
		self.GatewayIP 							= ""
		self.ApiPort 							= "8080"
		self.WsPort 							= "1981"
		self.ApiUrl 							= ""
		self.WsUrl								= ""
		self.UserName 							= ""
		self.Password 							= ""
		# Locks and Events
		self.NetworkAccessTickLock 				= threading.Lock()
		# Sates
		self.States 							= {
			'IDLE': 							self.StateIdle,
			'INIT':								self.StateInit,
			'INIT_GATEWAY':						self.StateInitGateway,
			'ACCESS_GATEWAY': 					self.StateAccessGetway,
			'ACCESS_WAIT_GATEWAY':				self.StateAccessWaitGatway,
			'INIT_LOCAL_SERVER':				self.StateInitLocalServer,
			'WORKING': 							self.StateWork
		}
		# Handlers
		self.NodeRequestHandlers['get_port'] 		= self.GetPortRequestHandler
		self.NodeRequestHandlers['get_local_nodes'] = self.GetLocalNodesRequestHandler
		self.NodeRequestHandlers['get_master_info'] = self.GetMasterInfoRequestHandler
		self.NodeRequestHandlers['upload_file'] 	= self.UploadFileHandler
		# Callbacks
		self.GatewayDataArrivedCallback 		= None
		self.GatewayConnectedCallback 			= None
		self.GatewayConnectionClosedCallback 	= None
		self.OnCustomCommandRequestCallback		= None
		self.OnCustomCommandResponseCallback	= None
		# Flags
		self.IsListenerEnabled 					= False
		self.PipeStdoutRun						= False

		#self.SetState("INIT")

		thread.start_new_thread(self.GatewayRXQueueWorker, ())
		thread.start_new_thread(self.GatewayTXQueueWorker, ())
	
	def EnableLogs(self, name):
		self.Logger = MkSLogger.Logger(name)
		self.Logger.EnablePrint()
		self.Logger.EnableLogger()

	#def Initiate(self):
	#	print("TODO - (MkSMasterNode.MasterNode) Who stops PipeStdoutListener_Thread thread?")
	#	thread.start_new_thread(self.PipeStdoutListener_Thread, ())

	def StateIdle (self):
		self.Logger.Log("(Master Node)# Note, in IDLE state ...")
		time.sleep(1)
	
	def StateInit (self):
		self.SetState("INIT_LOCAL_SERVER")
	
	def StateInitGateway(self):
		if self.IsNodeWSServiceEnabled is True:
			# Create Network instance
			self.Network = MkSNetMachine.Network(self.ApiUrl, self.WsUrl)
			self.Network.SetLogger(self.Logger)
			self.Network.SetDeviceType(self.Type)
			self.Network.SetDeviceUUID(self.UUID)
			# Register to events
			self.Network.OnConnectionCallback  		= self.WebSocketConnectedCallback
			self.Network.OnDataArrivedCallback 		= self.WebSocketDataArrivedCallback
			self.Network.OnConnectionClosedCallback = self.WebSocketConnectionClosedCallback
			self.Network.OnErrorCallback 			= self.WebSocketErrorCallback
			self.AccessTick = 0

			self.SetState("ACCESS_GATEWAY")
		else:
			if self.IsNodeLocalServerEnabled is True:
				self.SetState("INIT_LOCAL_SERVER")
			else:
				self.SetState("WORKING")

	def StateAccessGetway (self):
		if self.IsNodeWSServiceEnabled is True:
			self.Network.AccessGateway(self.Key, json.dumps({
				'node_name': str(self.Name),
				'node_type': self.Type
			}))

			self.SetState("ACCESS_WAIT_GATEWAY")
		else:
			self.SetState("WORKING")
	
	def StateAccessWaitGatway (self):
		if self.AccessTick > 10:
			self.SetState("ACCESS_WAIT_GATEWAY")
			self.AccessTick = 0
		else:
			self.AccessTick += 1
	
	def StateInitLocalServer(self):
		self.SocketServer.Start(16999)
		#self.ServerAdderss = ('', 16999)
		#status = self.TryStartListener()
		#if status is True:
		#	self.IsListenerEnabled = True
		#	self.SetState("INIT_GATEWAY")
		#time.sleep(1)

	def StateWork (self):
		if self.SystemLoaded is False:
			self.SystemLoaded = True # Update node that system done loading.
			if self.NodeSystemLoadedCallback is not None:
				self.NodeSystemLoadedCallback()
			
		if 0 == self.Ticker % 60:
			self.SendGatewayPing()

	def WebSocketConnectedCallback (self):
		self.SetState("WORKING")
		self.GatewayConnectedEvent()
		if self.GatewayConnectedCallback is not None:
			self.GatewayConnectedCallback()
	
	def WebSocketConnectionClosedCallback (self):
		if self.GatewayConnectionClosedCallback is not None:
			self.GatewayConnectionClosedCallback()
		self.NetworkAccessTickLock.acquire()
		self.AccessTick = 0
		self.NetworkAccessTickLock.release()
		self.SetState("ACCESS_GATEWAY")

	# TODO - Must be dealt with different thread (we must have thread poll)
	def WebSocketDataArrivedCallback (self, packet):
		self.GatewayRXQueueLock.acquire()
		try:
			self.SetState("WORKING")
			self.GatewayRXQueue.put(packet)
		except Exception as e:
			self.Logger.Log("({classname})# WebSocket Error - Data arrived issue\nPACKET#\n{0}\n(EXEPTION)# {error}".format(
						packet,
						classname=self.ClassName,
						error=str(e)))
		self.GatewayRXQueueLock.release()
	
	def WebSocketErrorCallback (self):
		self.Logger.Log("(Master Node)# ERROR - Gateway socket error")
		# TODO - Send callback "OnWSError"
		self.NetworkAccessTickLock.acquire()
		self.AccessTick = 0
		self.NetworkAccessTickLock.release()
		self.SetState("ACCESS_WAIT_GATEWAY")
	
	def GatewayRXQueueWorker(self):
		self.GatewayRXWorkerRunning = True
		while self.GatewayRXWorkerRunning is True:
			try:
				packet 		= self.GatewayRXQueue.get(block=True,timeout=None)
				messageType = self.BasicProtocol.GetMessageTypeFromJson(packet)
				direction 	= self.BasicProtocol.GetDirectionFromJson(packet)
				destination = self.BasicProtocol.GetDestinationFromJson(packet)
				source 		= self.BasicProtocol.GetSourceFromJson(packet)
				command 	= self.BasicProtocol.GetCommandFromJson(packet)

				packet["additional"]["client_type"] = "global_ws"

				self.Logger.Log("({classname})# WS [{direction}] {source} -> {dest} [{cmd}]".format(
							classname=self.ClassName,
							direction=direction,
							source=source,
							dest=destination,
							cmd=command))
				
				if messageType == "BROADCAST":
					pass
			
				if destination in source:
					return

				# Is this packet for me?
				if destination in self.UUID:
					if messageType == "CUSTOM":
						return
					elif messageType in ["DIRECT", "PRIVATE", "WEBFACE"]:
						if command in self.NodeRequestHandlers.keys():
							message = self.NodeRequestHandlers[command](None, packet)
							self.SendPacketGateway(message)
						else:
							if self.GatewayDataArrivedCallback is not None:
								message = self.GatewayDataArrivedCallback(None, packet)
								self.SendPacketGateway(message)
					else:
						self.Logger.Log("({classname})# [Websocket INBOUND] ERROR - Not support {0} request type.".format(messageType, classname=self.ClassName))
				else:
					self.Logger.Log("(Master Node)# Not mine ... Sending to slave ... " + destination)
					# Find who has this destination adderes.
					self.HandleExternalRequest(packet)
			except Exception as e:
				print ("({classname})# [ERROR] (GatewayRXQueueWorker) {0}".format(str(e), classname=self.ClassName))
	
	def GatewayTXQueueWorker(self):
		self.GatewayTXWorkerRunning = True
		while self.GatewayTXWorkerRunning is True:
			packet = self.GatewayTXQueue.get(block=True,timeout=None)
			self.Network.SendWebSocket(packet)
	
	# Master as proxy server.
	def HandleExternalRequest(self, packet):
		self.Logger.Log("({classname})# External request (PROXY)".format(classname=self.ClassName))
		destination = self.Network.BasicProtocol.GetDestinationFromJson(packet)
		node 		= self.GetSlaveNode(destination)
		
		if node is not None:
			message = self.BasicProtocol.StringifyPacket(packet)
			message = self.BasicProtocol.AppendMagic(message)
			node.Socket.send(message)
		else:
			self.Logger.Log("[MasterNode] HandleInternalReqest NODE NOT FOUND")
			# Need to look at other masters list.
			pass

	def GetNodeInfoRequestHandler(self, sock, packet):
		payload = self.NodeInfo
		payload["is_master"] 	= self.IsMaster
		payload["master_uuid"] 	= ""
		return self.Network.BasicProtocol.BuildResponse(packet, payload)
	
	# Description:
	#	1. Forging response with port for slave to use as listenning port.
	#	2. Sending new node connected event to all connected nodes.
	#	3. Sending request with slave details to Gateway.
	def GetPortRequestHandler(self, sock, packet):
		if sock is None:
			return ""
		
		node_info = self.BasicProtocol.GetPayloadFromJson(packet)

		nodetype 	= node_info['type']
		uuid 		= node_info['uuid']
		name 		= node_info['name']

		self.Logger.Log("({classname})# {uuid} {name} {nodetype}".format(
						classname=self.ClassName,
						uuid=uuid,
						name=name,
						nodetype=nodetype))

		# Do we have available port.
		if self.PortsForClients:
			node = self.GetNodeBySock(sock)
			existingSlave = None
			for slave in self.LocalSlaveList:
				if slave.UUID == node.UUID:
					existingSlave = slave
					continue
			if None == existingSlave:
				# New request
				port = 10000 + self.PortsForClients.pop()
				# Update node
				node.Type = nodetype
				node.ListenerPort = port
				node.UUID = uuid
				node.SetNodeName(name)
				node.Info = node_info

				# Update installed node list (UI will be updated)
				for item in self.InstalledNodes:
					if item.UUID == node.UUID:
						item.IP 			= node.IP
						item.ListenerPort 	= node.ListenerPort
						item.Status 		= "Running"

				self.LocalSlaveList.append(node)
				# TODO - What will happen when slave node will try to get port when we are not connected to AWS?
				# Send message to Gateway
				payload = 	{ 
								'node': { 	
									'ip':	str(node.IP), 
									'port':	port, 
									'uuid':	node.UUID, 
									'type':	nodetype,
									'name':	str(node.Name)
								} 
							}
				message = self.Network.BasicProtocol.BuildRequest("MASTER", "GATEWAY", self.UUID, "node_connected", payload, {})
				self.SendPacketGateway(message)

				# Send message (master_append_node) to all nodes.
				for key in self.OpenConnections:
					node = self.OpenConnections[key]
					if node.Socket != self.ServerSocket:
						message = self.Network.BasicProtocol.BuildMessage("response", "DIRECT", node.UUID, self.UUID, "master_append_node", node_info, {})
						message = self.Network.BasicProtocol.AppendMagic(message)
						self.SendNodePacket(node.IP, node.Port, message)
						#node.Socket.send(message)
				
				# Store UUID if it is a service
				if nodetype == 101:
					self.EMailServiceUUID 		= node.UUID
				elif nodetype == 102:
					self.SMSServiceUUID 		= node.UUID
				elif nodetype == 103:
					self.IPScannerServiceUUID 	= node.UUID
					self.RegisterOnNodeChangeEvent(self.IPScannerServiceUUID)

				return self.Network.BasicProtocol.BuildResponse(packet, { 'port': port })
			else:
				# Already assigned port (resending)
				return self.Network.BasicProtocol.BuildResponse(packet, { 'port': node.ListenerPort })
		else:
			# No available ports
			return self.Network.BasicProtocol.BuildResponse(packet, { 'port': 0 })
	
	def LocalServerTerminated(self):
		for slave in self.LocalSlaveList:
			payload = 	{ 
							'node': { 	
								'ip':	str(slave.IP), 
								'port':	slave.ListenerPort, 
								'uuid':	slave.UUID, 
								'type':	slave.Type
							} 
						}
			message = self.Network.BasicProtocol.BuildRequest("MASTER", "GATEWAY", self.UUID, "node_disconnected", payload, {})
			self.SendPacketGateway(message)

	def NodeDisconnectHandler(self, sock):
		print ("({classname})# [NodeDisconnectHandler]".format(classname=self.ClassName))
		for slave in self.LocalSlaveList:
			if slave.Socket == sock:
				self.PortsForClients.append(slave.ListenerPort - 10000)

				self.Logger.Log("({classname})# Slave ({name}) {uuid} has disconnected".format(
						classname=self.ClassName,
						name=slave.Name,
						uuid=slave.UUID))

				# Update installed node list (UI will be updated)
				for item in self.InstalledNodes:
					if item.UUID == slave.UUID:
						item.IP 	= ""
						item.ListenerPort 	= 0
						item.Status = "Stopped"
				
				# Send message to Gateway
				payload = 	{ 
								'node': { 	
									'ip':	str(slave.IP), 
									'port':	slave.ListenerPort, 
									'uuid':	slave.UUID, 
									'type':	slave.Type
								} 
							}
				message = self.Network.BasicProtocol.BuildRequest("MASTER", "GATEWAY", self.UUID, "node_disconnected", payload, {})
				self.SendPacketGateway(message)

				# Send message (master_remove_node) to all nodes.
				for key in self.OpenConnections:
					node = self.OpenConnections[key]
					if node.Socket == self.ServerSocket or node.Socket == sock:
						pass
					else:
						message = self.Network.BasicProtocol.BuildMessage("response", "DIRECT", node.UUID, self.UUID, "master_remove_node", slave.Info, {})
						message = self.Network.BasicProtocol.AppendMagic(message)
						self.SendNodePacket(node.IP, node.Port, message)

				self.LocalSlaveList.remove(slave)
				continue
	
	def GetLocalNodesRequestHandler(self, sock, packet):
		if self.LocalSlaveList:
			nodes =[]
			for node in self.LocalSlaveList:
				nodes.append({
					'ip': str(node.IP),
					'port': str(node.ListenerPort),
					'uuid': node.UUID,
					'type': str(node.Type)
				})
		return self.Network.BasicProtocol.BuildResponse(packet, { 'nodes': nodes })

	def GetMasterInfoRequestHandler(self, sock, packet):
		return self.Network.BasicProtocol.BuildResponse(packet, { })
	
	def UploadFileHandler(self, sock, packet):
		return self.Network.BasicProtocol.BuildResponse(packet, { })

	def GetNodeStatusRequestHandler(self, sock, packet):
		payload = {
			"status":"online"
		}
		return self.Network.BasicProtocol.BuildResponse(packet, payload)
	
	def GetNodeStatusResponseHandler(self, sock, packet):
		if self.OnApplicationResponseCallback is not None:
			self.OnApplicationResponseCallback(sock, packet)
	
	def SendGatewayPing(self):
		# Send request
		message = self.BasicProtocol.BuildRequest("DIRECT", "GATEWAY", self.UUID, "ping", self.NodeInfo, {})
		self.SendPacketGateway(message)

	def SendPacketGateway(self, packet):
		self.GatewayTXQueueLock.acquire()
		try:
			self.GatewayTXQueue.put(packet)
		except Exception as e:
			self.Logger.Log("({classname})# ERROR - [SendPacketGateway]\nPACKET#\n{0}\n(EXEPTION)# {error}".format(
						packet,
						classname=self.ClassName,
						error=str(e)))
		self.GatewayTXQueueLock.release()

	def SendRequest(self, uuid, msg_type, command, payload, additional):
		# Generate request
		message = self.Network.BasicProtocol.BuildRequest(msg_type, uuid, self.UUID, command, payload, additional)
		# TODO - Check if we need to send it via Gateway
		# Send message
		self.SendPacketGateway(message)

	def GatewayConnectedEvent(self):
		self.Logger.Log("(Master Node)# Connection to Gateway established ...")
		# Send registration of all slaves to Gateway.
		for slave in self.LocalSlaveList:
			# Send message to Gateway
			payload = 	{ 
							'node': { 	
								'ip':	str(slave.IP), 
								'port':	slave.Port, 
								'uuid':	slave.UUID, 
								'type':	slave.Type,
								'name':	str(slave.Name)
							} 
						}
			message = self.Network.BasicProtocol.BuildRequest("MASTER", "GATEWAY", self.UUID, "node_connected", payload, {})
			self.SendPacketGateway(message)
		
	def GetSlaveNode(self, uuid):
		for item in self.LocalSlaveList:
			if item.UUID == uuid:
				return item
		return None

	#
	# ################################ Under Refactoring ###############################################
	#

	"""
	Local Face RESP API methods
	"""
	"""
	def GetNodeListHandler(self, key):
		if "ykiveish" in key:
			response = "{\"response\":\"OK\",\"payload\":{\"list\":["
			for idx, item in enumerate(self.GetInstalledNodes()):
				response += "{\"uuid\":\"" + str(item.UUID) + "\",\"type\":\"" + str(item.Type) + "\",\"ip\":\"" + str(item.IP) + "\",\"port\":" + str(item.Port) + ",\"widget_port\":" + str(item.Port - 10000) + ",\"status\":\"" + str(item.Status) + "\"},"
			response = response[:-1] + "]}}"
			return jsonify(response)
		else:
			return ""

	def GetNodeListByTypeHandler(self, key):
		print ("[MasterNode]# GetNodeListByTypeHandler")
		fields = [k for k in request.form]
		values = [request.form[k] for k in request.form]

		req   = request.form["request"]
		data  = json.loads(request.form["json"])

		if "ykiveish" in key:
			response = "{\"response\":\"OK\",\"payload\":{\"list\":["
			for idx, item in enumerate(self.InstalledNodes):
				if item.Type in data["types"]:
					response += "{\"uuid\":\"" + str(item.UUID) + "\",\"type\":\"" + str(item.Type) + "\",\"ip\":\"" + str(item.IP) + "\",\"port\":" + str(item.Port) + ",\"widget_port\":" + str(item.Port - 10000) + ",\"status\":\"" + str(item.Status) + "\"},"
			response = response[:-1] + "]}}"
			return jsonify(response)
		else:
			return ""

	# TODO - Is this method in use?
	def SetNodeActionHandler(self, key):
		fields = [k for k in request.form]
		values = [request.form[k] for k in request.form]

		req   = request.form["request"]
		data  = json.loads(request.form["json"])

		action = data["action"]
		uuid = data["uuid"]
		if action in "Stop":
			self.ExitRemoteNode(uuid)
		elif action in "Start":
			self.StartRemoteNode(uuid)
		elif action in "shell":
			shell = self.GetShellScreen(uuid)
			return "{\"response\":\"OK\",\"shell\":" + str(json.dumps(shell)) + "}"

		# Send response
		return "{\"response\":\"OK\"}"

	def GetNodeShellCommandHandler(self, key):
		fields = [k for k in request.form]
		values = [request.form[k] for k in request.form]

		req   = request.form["request"]
		data  = json.loads(request.form["json"])

		shell = self.Terminal.ExecuteCommand(data["cmd"])
		rows = shell.split("\n")

		for idx, item in enumerate(rows):
			rows[idx] = "\"" + item + "\""
		
		return "{\"response\":\"OK\",\"shell\":" + str(json.dumps(rows)) + "}"

	def GetNodeConfigInfoHandler(self, key):
		return str(json.dumps(self.MachineInfo.GetInfo()))

	def GetApplicationListHandler(self, key):
		jsonCxt = self.InstalledApps
		if (jsonCxt is not "" and jsonCxt is not None):
			apps 	= jsonCxt["installed"]

			for item in apps:
				if MkSGlobals.OS_TYPE in ["linux", "linux2"]:
					image = self.File.LoadContent(item["path"] + "/app.png")
				elif MkSGlobals.OS_TYPE == "win32":
					image = self.File.LoadContent(item["path"] + "\\app.png")
				item["image"] = image.encode('base64')

			print (str(json.dumps(apps)))
			return "{\"response\":\"OK\",\"apps\":" + str(json.dumps(apps)) + "}"
		return "{\"response\":\"FAILED\"}"

	def GetApplicationHTMLHandler(self, key):
		fields = [k for k in request.form]
		values = [request.form[k] for k in request.form]

		req   = request.form["request"]
		data  = json.loads(request.form["json"])

		jsonCxt = self.InstalledApps
		apps 	= jsonCxt["installed"]
		html = ""
		for item in apps:
			if str(item["id"]) == str(data["id"]):
				if MkSGlobals.OS_TYPE in ["linux", "linux2"]:
					html = self.File.LoadContent(item["path"] + "/app.html")
				elif MkSGlobals.OS_TYPE == "win32":
					html = self.File.LoadContent(item["path"] + "\\app.html")
				return html

		return html

	def GetApplicationJavaScriptHandler(self, key):
		fields = [k for k in request.form]
		values = [request.form[k] for k in request.form]

		req   = request.form["request"]
		data  = json.loads(request.form["json"])

		jsonCxt = self.InstalledApps
		apps 	= jsonCxt["installed"]
		js = ""
		for item in apps:
			if str(item["id"]) == str(data["id"]):
				if MkSGlobals.OS_TYPE in ["linux", "linux2"]:
					js = self.File.LoadContent(item["path"] + "/app.js")
				elif MkSGlobals.OS_TYPE == "win32":
					js = self.File.LoadContent(item["path"] + "\\app.js")
				js = js.replace("[IPANDPORT]", str(self.MyLocalIP) + ":8080")
				return js

		return js

	# Avoid CORS
	def GenericNodeGETRequestHandler(self, key):
		print ("[MasterNode]# GenericNodeGETRequestHandler")
		fields = [k for k in request.form]
		values = [request.form[k] for k in request.form]

		req   = request.form["request"]
		data  = json.loads(request.form["json"])

		requestUrl = data["url"]
		try:
			req = urllib2.urlopen(requestUrl, timeout=1)
			if req != None:
				data = req.read()
				return data
			else:
				return ""
		except:
			return ""
	"""
	"""
	Local Face RESP API methods
	"""	
	"""
	def GetInstalledNodes(self):
		return self.InstalledNodes

	def ExitRemoteNode(self, uuid):
		node = self.GetNodeByUUID(uuid)
		if node is not None:
			# payload = self.Commands.ExitRequest()
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

	def PipeStdoutListener_Thread(self):
		print(("(Master Node)# Starting PIPE listener thread ..."))
		self.PipeStdoutRun = True
		while self.PipeStdoutRun:
			for item in self.Pipes:
				if item.IsPipeError():
					print (str(item.GetError()))
				item.ReadToBuffer()
			time.sleep(0.5)

	def StartRemoteNode(self, uuid):
		path = "/home/yevgeniy/workspace/makesense/mksnodes/1981"
		proc = subprocess.Popen(["python", '-u', "../1981/1981.py", "--path", path], stdout=subprocess.PIPE)

		pipe = LocalPipe(uuid, proc)
		self.Pipes.append(pipe)

	def ExitRoutine(self):
		self.Terminal.Stop()
	"""