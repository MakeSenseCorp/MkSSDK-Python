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
import subprocess
from subprocess import call
import urllib2
import urllib

from flask import Flask, render_template, jsonify, Response, request
import logging

import MkSGlobals
from mksdk import MkSFile
from mksdk import MkSNetMachine
from mksdk import MkSAbstractNode
from mksdk import MkSShellExecutor

# TODO - Move this clss to other location.
class MachineInformation():
	def __init__(self):
		self.Terminal	= MkSShellExecutor.ShellExecutor()
		self.Json 		= {
			"cpu": {
				"arch": "N/A"
			},
			"hdd": {
				"capacity_ratio": "N/A"
			},
			"ram": {
				"capacity_ratio": "N/A"
			},
			"sensors": {
				"temp": "N/A",
				"freq": "N/A"
			},
			"network": {
				"ip": "N/A"
			}
		}

		thread.start_new_thread(self.MachineInformationWorker_Thread, ())

	def MachineInformationWorker_Thread(self):
		while True:
			if MkSGlobals.OS_TYPE in ["linux", "linux2"]:
				self.Json["sensors"]["temp"] = str(self.Terminal.ExecuteCommand("cat /sys/devices/virtual/thermal/thermal_zone0/temp"))
			time.sleep(5)

	def GetInfo(self):
		return self.Json

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
		self.MachineInfo 						= MachineInformation()
		self.PortsForClients					= [item for item in range(1,33)]
		self.MasterHostName						= socket.gethostname()
		self.MasterVersion						= "1.0.1"
		self.PackagesList						= ["Gateway","LinuxTerminal"] # Default Master capabilities.
		self.LocalSlaveList						= [] # Used ONLY by Master.
		self.InstalledNodes 					= []
		self.Pipes 								= []
		self.InstalledApps 						= None
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
			'WORK': 							self.StateWork
		}
		# Handlers
		self.NodeRequestHandlers['get_port'] 		= self.GetPortRequestHandler
		self.NodeRequestHandlers['get_local_nodes'] = self.GetLocalNodesRequestHandler
		self.NodeRequestHandlers['get_master_info'] = self.GetMasterInfoRequestHandler
		self.NodeRequestHandlers['get_file'] 		= self.GetFileHandler
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
		self.SetState("INIT")

	#
	# ###### MASTER NODE INITIATE ->
	#

	def Initiate(self):
		self.LoadNodesOnMasterStart()

		print("TODO - (MkSMasterNode.MasterNode) Who stops PipeStdoutListener_Thread thread?")
		thread.start_new_thread(self.PipeStdoutListener_Thread, ())

	#
	# ###### MASTER NODE INITIATE <-
	#

	#
	# ###### MASTER NODE STATES ->
	#

	def StateIdle (self):
		print("(Master Node)# Note, in IDLE state ...")
		time.sleep(1)
	
	def StateInit (self):
		self.SetState("INIT_LOCAL_SERVER")
	
	def StateInitGateway(self):
		if self.IsNodeWSServiceEnabled is True:
			# Create Network instance
			self.Network = MkSNetMachine.Network(self.ApiUrl, self.WsUrl)
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
				self.SetState("WORK")

	def StateAccessGetway (self):
		if self.IsNodeWSServiceEnabled is True:
			self.Network.AccessGateway(self.Key, json.dumps({
				'node_name': str(self.Name),
				'node_type': self.Type
			}))

			self.SetState("ACCESS_WAIT_GATEWAY")
		else:
			self.SetState("WORK")
	
	def StateAccessWaitGatway (self):
		if self.AccessTick > 10:
			self.SetState("ACCESS_WAIT_GATEWAY")
			self.AccessTick = 0
		else:
			self.AccessTick += 1
	
	def StateInitLocalServer(self):
		self.ServerAdderss = ('', 16999)
		status = self.TryStartListener()
		if status is True:
			self.IsListenerEnabled = True
			self.SetState("INIT_GATEWAY")
		time.sleep(1)

	def StateWork (self):
		if self.SystemLoaded is False:
			self.SystemLoaded = True # Update node that system done loading.
			if self.NodeSystemLoadedCallback is not None:
				self.NodeSystemLoadedCallback()
	
	#
	# ###### MASTER NODE STATES <-
	#
	
	#
	# ###### MASTER NODE GATAWAY CALLBACKS ->
	#

	def WebSocketConnectedCallback (self):
		self.SetState("WORK")
		if self.GatewayConnectedCallback is not None:
			self.GatewayConnectedCallback()
	
	def WebSocketConnectionClosedCallback (self):
		if self.GatewayConnectionClosedCallback is not None:
			self.GatewayConnectionClosedCallback()
		self.NetworkAccessTickLock.acquire()
		try:
			self.AccessTick = 0
		finally:
			self.NetworkAccessTickLock.release()
		self.SetState("ACCESS_GATEWAY")

	def WebSocketDataArrivedCallback (self, packet):
		try:
			self.SetState("WORK")
			messageType = self.BasicProtocol.GetMessageTypeFromJson(packet)
			destination = self.BasicProtocol.GetDestinationFromJson(packet)
			command 	= self.BasicProtocol.GetCommandFromJson(packet)

			print ("({classname})# [REQUEST] Gateway -> Node [{cmd}, {dest}]".format(
						classname=self.ClassName,
						cmd=str(command),
						dest=destination))

			# Is this packet for me?
			if destination in self.UUID:
				if messageType == "CUSTOM":
					return
				elif messageType in ["DIRECT", "PRIVATE", "BROADCAST", "WEBFACE"]:
					if command in self.NodeRequestHandlers.keys():
						message = self.NodeRequestHandlers[command](None, packet)
						self.Network.SendWebSocket(message)
					else:
						if self.GatewayDataArrivedCallback is not None:
							self.GatewayDataArrivedCallback(None, packet)
				else:
					print ("(Master Node)# [Websocket INBOUND] ERROR - Not support " + request + " request type.")
			else:
				print ("(Master Node)# Not mine ... Sending to slave ... " + destination)
				# Find who has this destination adderes.
				self.HandleExternalRequest(packet)
		except Exception as e:
			print("({classname})# ERROR - Data arrived issue\n(EXEPTION)# {error}".format(
						classname=self.ClassName,
						error=str(e)))
	
	def WebSocketErrorCallback (self):
		print ("(Master Node)# ERROR - Gateway socket error")
		# TODO - Send callback "OnWSError"
		self.NetworkAccessTickLock.acquire()
		try:
			self.AccessTick = 0
		finally:
			self.NetworkAccessTickLock.release()
		self.SetState("ACCESS_WAIT_GATEWAY")
	
	#
	# ###### MASTER NODE GATAWAY CALLBACKS <-
	#

	def GetNodeInfoRequestHandler(self, sock, packet):
		payload = self.NodeInfo
		return self.Network.BasicProtocol.BuildResponse(packet, payload)
	
	def GetPortRequestHandler(self, sock, packet):
		if sock is None:
			return ""
		
		payload = self.BasicProtocol.GetPayloadFromJson(packet)

		nodetype 	= payload['type']
		uuid 		= payload['uuid']
		name 		= payload['name']

		print ("({classname})# {uuid} {name} {nodetype}".format(
						classname=self.ClassName,
						uuid=uuid,
						name=name,
						nodetype=nodetype))

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
				node.Type = nodetype
				node.Port = port
				node.UUID = uuid
				node.SetNodeName(name)

				# Update installed node list (UI will be updated)
				for item in self.InstalledNodes:
					if item.UUID == node.UUID:
						item.IP 	= node.IP
						item.Port 	= node.Port
						item.Status = "Running"

				self.LocalSlaveList.append(node)
				return self.Network.BasicProtocol.BuildResponse(packet, { 'port': port })

				# Send message to all nodes.
				# paylod = self.Commands.MasterAppendNodeResponse(node.IP, port, node.UUID, nodetype)
				# for client in self.Connections:
				#	if client.Socket == self.ServerSocket:
				#		pass
				#	else:
				#		client.Socket.send(paylod)
				# self.LocalSlaveList.append(node)
				# payload = self.Commands.GetPortResponse(port)
				# sock.send(payload)

				# TODO - What will happen when slave node will try to get port when we are not connected to AWS?
				# Send message to Gateway
				# if self.ServiceNewNodeCallback is not None:
				#	self.ServiceNewNodeCallback({ 	
				#									'ip':	str(node.IP), 
				#							 		'port':	port, 
				#							 		'uuid':	node.UUID, 
				#							 		'type':	nodetype,
				#							 		'name':	str(node.Name)
				#								})
			else:
				pass
				# Already assigned port (resending)
				# payload = self.Commands.GetPortResponse(node.Port)
				# sock.send(payload)
		else:
			pass
			# No available ports
			# payload = self.Commands.GetPortResponse(0)
			# sock.send(payload)
	
	def NodeDisconnectHandler(self, sock):		
		for slave in self.LocalSlaveList:
			if slave.Socket == sock:
				self.PortsForClients.append(slave.Port - 10000)

				print ("({classname})# Slave ({name}) {uuid} has disconnected".format(
						classname=self.ClassName,
						name=slave.Name,
						uuid=slave.UUID))

				# Update installed node list (UI will be updated)
				for item in self.InstalledNodes:
					if item.UUID == slave.UUID:
						item.IP 	= ""
						item.Port 	= 0
						item.Status = "Stopped"

				# payload = self.Commands.MasterRemoveNodeResponse(slave.IP, slave.Port, slave.UUID, slave.Type)
				# Send to all nodes
				# for client in self.Connections:
				#	if client.Socket == self.ServerSocket or client.Socket == sock:
				#		pass
				#	else:
				#		if client.Socket is not None:
				#			client.Socket.send(payload)

				# Send message to Gateway
				# if self.OnSlaveNodeDisconnectedCallback is not None:
				#	self.OnSlaveNodeDisconnectedCallback({ 'ip':	str(slave.IP), 
				#										 'port':	slave.Port, 
				#										 'uuid':	slave.UUID, 
				#										 'type':	slave.Type 
				#										})

				self.LocalSlaveList.remove(slave)
				continue
	
	def GetFileHandler(self, sock, packet):
		objFile 	= MkSFile.File()
		payload 	= self.BasicProtocol.GetPayloadFromJson(packet)
		uiType 		= payload["ui_type"]
		fileType 	= payload["file_type"]
		fileName 	= payload["file_name"]

		folder = {
			'config': 		'config',
			'app': 			'app',
			'thumbnail': 	'thumbnail'
		}

		path 	= os.path.join(".","ui",folder[uiType],"ui." + fileType)
		content = objFile.Load(path)

		print ("({classname})# Requested file: {path} ({fileName}.{fileType})".format(
				classname=self.ClassName,
				path=path,
				fileName=fileName,
				fileType=fileType))
		
		if ("html" in fileType):
			content = content.replace("[NODE_UUID]", self.UUID)
			content = content.replace("[GATEWAY_IP]", self.GatewayIP)
		
		return self.BasicProtocol.BuildResponse(packet, {
								'file_type': fileType,
								'ui_type': uiType,
								'content': content.encode('hex')
		})

		# self.Network.SendWebSocket(message)
		#if self.SendGatewayMessageCallback is not None:
		#	self.SendGatewayMessageCallback(message)
	
	def UploadFileHandler(self, packet):
		pass

	"""
	Local Face RESP API methods
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
	Local Face RESP API methods
	"""

	def GatewayConnectedEvent(self):
		print ("(Master Node)# Connection to Gateway established ...")
		for slave in self.LocalSlaveList:
			if self.ServiceNewNodeCallback is not None:
				self.ServiceNewNodeCallback({ 
												'ip':	str(slave.IP), 
										 		'port':	slave.Port, 
										 		'uuid':	slave.UUID, 
										 		'type':	slave.Type 
											})

	# TODO - Implement this method.
	def GetNodeStatusRequestHandler(self, sock, packet):
		pass

	def GetNodeInfoResponseHandler(self, sock, packet):
		pass

	# Sending response to "get_node_info" request (mostly for proxy request)
	#def GetNodeInfoResponseHandler(self, sock, packet):
	#	print ("[DEBUG MASTER] GetNodeInfoResponseHandler")
	#	source 		= packet["payload"]["header"]["source"]
	#	destination = packet["payload"]["header"]["destination"]
	#	command 	= packet["command"]
	#	payload 	= packet["payload"]["data"]
	#	# This data traveling from App request and back to App
	#	piggy  		= packet["piggybag"]
	#
	#	# TODO - If this is a proxy response then trigger OnSlaveResponseCallback.
	#	# 		 Otherwise this is a response to master request. (MUST HANDLE IT LOCALY)
	#
	#	if self.OnSlaveResponseCallback is not None:
	#		self.OnSlaveResponseCallback("response", destination, source, command, payload, piggy)
		
	def GetNodeStatusResponseHandler(self, sock, packet):
		pass

	# PROXY - Application -> Slave Node
	def HandleExternalRequest(self, packet):
		destination = packet["header"]["destination"]
		source 		= packet["header"]["source"]
		direction 	= packet["header"]["direction"]
		data 		= packet["data"]["payload"]
		command 	= packet["data"]["header"]["command"]
		piggy  		= packet["piggybag"]

		node = self.GetSlaveNode(destination)
		if node is not None:
			if (direction in "response"):
				# TODO - Incorrect translation between websocket prot to socket prot
				# msg = self.Commands.GatewayToProxyResponse(destination, source, command, data, piggy)
				node.Socket.send(msg)
				print ("[MasterNode] HandleInternalReqest RESPONSE")
			elif (direction in "request"):
				# msg = self.Commands.ProxyRequest(destination, source, command, data, piggy)
				node.Socket.send(msg)
				print ("[MasterNode] HandleInternalReqest REQUEST")
		else:
			print ("[MasterNode] HandleInternalReqest NODE NOT FOUND")
			# Need to look at other masters list.
			pass

	def LoadNodesOnMasterStart(self):
		jsonInstalledNodesStr 	= ""
		jsonInstalledAppsStr 	= ""

		if MkSGlobals.OS_TYPE == "win32":
			jsonInstalledNodesStr = self.File.Load("G:\\workspace\\Development\\Git\\makesense\\misc\\configure\\" + MkSGlobals.OS_TYPE + "\\installed_nodes.json")
		elif MkSGlobals.OS_TYPE in ["linux", "linux2"]:
			jsonInstalledNodesStr = self.File.Load("../../configure/installed_nodes.json")

		if (jsonInstalledNodesStr is not "" and jsonInstalledNodesStr is not None):
			# Load installed nodes.
			jsonData = json.loads(jsonInstalledNodesStr)
			for item in jsonData["installed"]:
				if 1 == item["type"]:
					node = MkSAbstractNode.LocalNode("", 16999, item["uuid"], item["type"], None)
					node.Status = "Running"
				else:
					node = MkSAbstractNode.LocalNode("", 0, item["uuid"], item["type"], None)
				self.InstalledNodes.append(node)

		if MkSGlobals.OS_TYPE == "win32":
			jsonInstalledAppsStr = self.File.Load("G:\\workspace\\Development\\Git\\makesense\\misc\\configure\\" + MkSGlobals.OS_TYPE + "\\installed_apps.json")
		elif MkSGlobals.OS_TYPE in ["linux", "linux2"]:
			jsonInstalledAppsStr = self.File.Load("../../configure/installed_apps.json")

		if (jsonInstalledAppsStr is not "" and jsonInstalledAppsStr is not None):
			# Load installed applications
			self.InstalledApps = json.loads(jsonInstalledAppsStr)

		#self.InitiateLocalServer(8080)
		# UI RestAPI
		#self.UI.AddEndpoint("/get/node_list/<key>", 				"get_node_list", 				self.GetNodeListHandler)
		#self.UI.AddEndpoint("/get/node_list_by_type/<key>", 		"get_node_list_by_type", 		self.GetNodeListByTypeHandler, 			method=['POST'])
		#self.UI.AddEndpoint("/set/node_action/<key>", 				"set_node_action", 				self.SetNodeActionHandler, 				method=['POST'])
		#self.UI.AddEndpoint("/get/node_shell_cmd/<key>", 			"get_node_shell_cmd", 			self.GetNodeShellCommandHandler, 		method=['POST'])
		#self.UI.AddEndpoint("/get/node_config_info/<key>", 			"get_node_config_info", 		self.GetNodeConfigInfoHandler)
		#self.UI.AddEndpoint("/get/app_list/<key>", 					"get_app_list", 				self.GetApplicationListHandler)
		#self.UI.AddEndpoint("/get/app_html/<key>", 					"get_app_html",					self.GetApplicationHTMLHandler, 		method=['POST'])
		#self.UI.AddEndpoint("/get/app_js/<key>", 					"get_app_js", 					self.GetApplicationJavaScriptHandler, 	method=['POST'])
		#self.UI.AddEndpoint("/generic/node_get_request/<key>", 		"generic_node_get_request", 	self.GenericNodeGETRequestHandler, 		method=['POST'])

	def GetLocalNodesRequestHandler(self, sock, packet):
		nodes = ""
		if self.LocalSlaveList:
			for node in self.LocalSlaveList:
				# TODO - nodes += "{\"ip\":\"{ip}\",\"port\":\"{port}\",\"uuid\":\"{uuid}\",\"type\":\"{type}\"},".format(ip = str(node.IP), port = str(node.Port), uuid = node.UUID, type = str(node.Type))
				nodes += "{\"ip\":\"" + str(node.IP) + "\",\"port\":" + str(node.Port) + ",\"uuid\":\"" + node.UUID + "\",\"type\":" + str(node.Type) + "},"
			if nodes is not "":
				nodes = nodes[:-1]
		# payload = self.Commands.GetLocalNodesResponse(nodes)
		sock.send(payload)

	def GetMasterInfoRequestHandler(self, sock, packet):
		nodes = ""
		if self.LocalSlaveList:
			for node in self.LocalSlaveList:
				# TODO - nodes += "{\"ip\":\"{ip}\",\"port\":\"{port}\",\"uuid\":\"{uuid}\",\"type\":\"{type}\"},".format(ip = str(node.IP), port = str(node.Port), uuid = node.UUID, type = str(node.Type))
				nodes += "{\"ip\":\"" + str(node.IP) + "\",\"port\":" + str(node.Port) + ",\"uuid\":\"" + node.UUID + "\",\"type\":" + str(node.Type) + "},"
			if nodes is not "":
				nodes = nodes[:-1]
		# payload = self.Commands.GetMasterInfoResponse(self.UUID, self.MasterHostName, nodes)
		sock.send(payload)

	#def GetNodeInfoRequestHandler(self, sock, packet):
	#	direction = self.BasicProtocol.GetDirectionFromJson(json)
	#	if (direction in "proxy_request"):
	#		# Send data response to requestor via Master Node module.
	#		if self.OnSlaveResponseCallback is not None:
	#			command 	= packet['command']
	#			source 		= packet["payload"]["header"]["source"]
	#			destination = packet["payload"]["header"]["destination"]
	#			payload 	= packet["payload"]["data"]
	#			piggy 		= packet["piggybag"]
	#			self.OnSlaveResponseCallback("request", destination, source, command, payload, piggy)
	
	# INBOUND
	
	#
	# DELETE
	#
	
	def HandlerRouter_Request(self, sock, packet):
		command = packet['command']
		# TODO - IF command type is not in list call unknown callback in user code.
		if command in self.RequestHandlers:
			self.RequestHandlers[command](sock, packet)
		else:
			if self.OnCustomCommandRequestCallback is not None:
				self.OnCustomCommandRequestCallback(sock, packet)

	# OUTBOUND
	def HandlerRouter_Response(self, sock, packet):
		command = packet['command']
		# TODO - IF command type is not in list call unknown callback in user code.
		if command in self.ResponseHandlers:
			self.ResponseHandlers[command](sock, packet)
		else:
			if self.OnCustomCommandResponseCallback is not None:
				self.OnCustomCommandResponseCallback(sock, packet)

	# OUTBOUND PROXY
	def HandlerRouter_Proxy(self, sock, json_data):
		print ("[MasterNode] HandlerRouter_ProxyResponse")
		command 	= json_data['command']
		source 		= json_data["payload"]["header"]["source"]
		destination = json_data["payload"]["header"]["destination"]
		payload 	= json_data["payload"]["data"]
		piggy 		= json_data["piggybag"]
		direction 	= json_data['direction']

		# Send data response to requestor via Master Node module.
		if self.OnSlaveResponseCallback is not None:
			if (direction in "proxy_request"):
				self.OnSlaveResponseCallback("request", destination, source, command, payload, piggy)
			elif (direction in "proxy_response"):
				self.OnSlaveResponseCallback("response", destination, source, command, payload, piggy)
			else:
				print("[MasterNode] ERROR - HandlerRouter_Proxy")

	# Description - Handling input date from local server.
	def HandlerRouter(self, sock, data):
		jsonData 	= json.loads(data)
		direction 	= jsonData['direction']

		if "response" == direction:
			self.HandlerRouter_Response(sock, jsonData)
		elif "request" == direction:
			self.HandlerRouter_Request(sock, jsonData)
		elif direction in ["proxy_request", "proxy_response"]:
			self.HandlerRouter_Proxy(sock, jsonData)

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
		# TODO - Is this method in use?
		path = "/home/yevgeniy/workspace/makesense/mksnodes/1981"
		proc = subprocess.Popen(["python", '-u', "../1981/1981.py", "--path", path], stdout=subprocess.PIPE)

		pipe = LocalPipe(uuid, proc)
		self.Pipes.append(pipe)

	def ExitRoutine(self):
		self.Terminal.Stop()