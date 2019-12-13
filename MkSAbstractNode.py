#!/usr/bin/python
import os
import sys
import json
if sys.version_info[0] < 3:
	import thread
else:
	import _thread
import threading
import time
import socket, select
import argparse

from flask import Flask, render_template, jsonify, Response, request
from flask_socketio import SocketIO, emit
from geventwebsocket import WebSocketServer, WebSocketApplication, Resource
from collections import OrderedDict
#from flask_cors import CORS
import logging

import MkSGlobals
from mksdk import MkSFile
from mksdk import MkSDevice
from mksdk import MkSUtils
from mksdk import MkSBasicNetworkProtocol

class EndpointAction(object):
	def __init__(self, page, args):
		self.Page = page + ".html"
		self.DataToJS = args

	def __call__(self, *args):
		return render_template(self.Page, data=self.DataToJS), 200, {
			'Cache-Control': 'no-cache, no-store, must-revalidate',
			'Pragma': 'no-cache',
			'Expires': '0',
			'Cache-Control': 'public, max-age=0'
		}

class WebInterface():
	def __init__(self, name, port):
		self.ClassName 	= "WebInterface"
		self.App 		= Flask(name)
		self.Port 		= port

		#self.App.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

		#CORS(self.App)
		#self.Log = logging.getLogger('werkzeug')
		#self.Log.disabled = True
		#self.App.logger.disabled = True

	def WebInterfaceWorker_Thread(self):
		print ("({classname})# Starting local webface on port ({port}) ...".format(classname=self.ClassName, port=str(self.Port)))
		self.App.run(host='0.0.0.0', port=self.Port)

	def Run(self):
		thread.start_new_thread(self.WebInterfaceWorker_Thread, ())

	def AddEndpoint(self, endpoint=None, endpoint_name=None, handler=None, args=None, method=['GET']):
		if handler is None:
			self.App.add_url_rule(endpoint, endpoint_name, EndpointAction(endpoint_name, args))
		else:
			self.App.add_url_rule(endpoint, endpoint_name, handler, methods=method)

class MkSLocalWebsocketServer():
	def __init__(self):
		self.ClassName 				= "LocalWebsocketServer"
		self.ApplicationSockets 	= {}
		self.ServerRunning 			= False
		# Events
		self.OnDataArrivedEvent 	= None
	
	def AppendSocket(self, ws_id, ws):
		print ("({classname})# Append new connection".format(classname=self.ClassName))
		self.ApplicationSockets[ws_id] = ws
	
	def RemoveSocket(self, ws_id):
		print ("({classname})# Remove connection".format(classname=self.ClassName))
		del self.ApplicationSockets[ws_id]
	
	def WSDataArrived(self, ws, data):
		# TODO - Append webface type
		packet	= json.loads(data)
		if ("HANDSHAKE" == packet['header']['message_type']):
			return
		
		packet["additional"]["ws_id"] = id(ws)
		packet["additional"]["pipe"]  = "LOCAL_WS"
		data = json.dumps(packet)

		if self.OnDataArrivedEvent is not None:
			self.OnDataArrivedEvent(ws, data)
	
	def Send(self, ws_id, data):
		self.ApplicationSockets[ws_id].send(data)
	
	def IsServerRunnig(self):
		return self.ServerRunning

	def Worker(self):
		try:
			server = WebSocketServer(('', 1982), Resource(OrderedDict([('/', NodeWSApplication)])))

			self.ServerRunning = True
			server.serve_forever()
		except:
			self.ServerRunning = False
	
	def RunServer(self):
		if self.ServerRunning is False:
			thread.start_new_thread(self.Worker, ())

WSManager = MkSLocalWebsocketServer()

class NodeWSApplication(WebSocketApplication):
	def __init__(self, *args, **kwargs):
		self.ClassName = "NodeWSApplication"
		super(NodeWSApplication, self).__init__(*args, **kwargs)
	
	def on_open(self):
		print ("({classname})# CONNECTION OPENED".format(classname=self.ClassName))
		WSManager.AppendSocket(id(self.ws), self.ws)

	def on_message(self, message):
		print ("({classname})# MESSAGE RECIEVED {0} {1}".format(id(self.ws),message,classname=self.ClassName))
		WSManager.WSDataArrived(self.ws, message)

	def on_close(self, reason):
		print ("({classname})# CONNECTION CLOSED".format(classname=self.ClassName))
		WSManager.RemoveSocket(id(self.ws))

class LocalNode():
	def __init__(self, ip, port, uuid, node_type, sock):
		self.IP 		= ip
		self.Port 		= port
		self.UUID 		= uuid
		self.Socket 	= sock
		self.Type 		= node_type
		self.Name 		= ""
		self.LocalType 	= "UNKNOWN"
		self.Status 	= "Stopped"
		self.Obj 		= None
	
	def SetNodeName(self, name):
		self.Name = name

class AbstractNode():
	def __init__(self):
		self.ClassName								= ""
		self.File 									= MkSFile.File()
		self.Connector 								= None
		self.Network								= None
		self.LocalWSManager							= WSManager
		# Device information
		self.Type 									= 0
		self.UUID 									= ""
		self.OSType 								= ""
		self.OSVersion 								= ""
		self.BrandName 								= ""
		self.Description							= ""
		self.DeviceInfo 							= None
		self.BoardType 								= ""
		self.Name 									= "N/A"
		# Misc
		self.IsMainNodeRunnig 						= True
		self.AccessTick 							= 0 	# Network establishment counter
		self.RegisteredNodes  						= []
		self.SystemLoaded							= False
		self.IsHardwareBased 						= False
		self.IsNodeWSServiceEnabled 				= False # Based on HTTP requests and web sockets
		self.IsNodeLocalServerEnabled 				= False # Based on regular sockets
		self.Ticker 								= 0
		self.Pwd									= os.getcwd()
		# State machine
		self.State 									= 'IDLE' # Current state of node
		self.States 								= None	 # States list
		# Locks and Events
		self.ExitEvent 								= threading.Event()
		self.ExitLocalServerEvent					= threading.Event()
		# Debug
		self.DebugMode								= False	
		# Callbacks
		self.WorkingCallback 						= None
		self.NodeSystemLoadedCallback 				= None
		self.OnLocalServerStartedCallback 			= None # Main local server (listener) rutin started.		
		self.OnApplicationRequestCallback			= None # Application will get this event on request arrived from local socket
		self.OnApplicationResponseCallback			= None # Application will get this event on response arrived from local socket
		self.OnAceptNewConnectionCallback			= None # Local server listener recieved new socket connection
		self.OnMasterFoundCallback					= None # When master node found or connected this event will be raised.
		self.OnMasterSearchCallback					= None # Raised on serach of master nodes start.
		self.OnMasterDisconnectedCallback			= None # When slave node loose connection with master node.
		self.OnTerminateConnectionCallback 			= None # When local server (listener) terminate socket connection.
		self.OnLocalServerListenerStartedCallback	= None # When loacl server (listener) succesfully binded port.
		self.OnExitCallback							= None # When node recieve command to terminate itself.
		# Registered items
		self.OnDeviceChangeList						= [] # Register command "register_on_node_change"
		## Unused
		self.DeviceConnectedCallback 				= None
		# Network
		self.ServerSocket 							= None # Local server listener
		self.ServerAdderss							= None # Local server listener
		self.RecievingSockets						= []
		self.SendingSockets							= []
		self.Connections 							= []
		self.OpenSocketsCounter						= 0
		self.IsLocalSocketRunning					= False
		self.IsListenerEnabled 						= False
		# Initialization methods
		self.MyLocalIP 								= MkSUtils.GetLocalIP()
		# Handlers
		self.NodeRequestHandlers					= {
			'get_node_info': 						self.GetNodeInfoRequestHandler,
			'get_node_status': 						self.GetNodeStatusRequestHandler,
			'get_file': 							self.GetFileHandler,
			'register_on_node_change':				self.RegisterOnNodeChangeHandler,
			'unregister_on_node_change':			self.UnregisterOnNodeChangeHandler
		}
		self.NodeResponseHandlers					= {
			'get_node_info': 						self.GetNodeInfoResponseHandler,
			'get_node_status': 						self.GetNodeStatusResponseHandler
		}
		# LocalFace UI
		self.UI 									= None
		self.LocalWebPort							= ""
		self.BasicProtocol 							= MkSBasicNetworkProtocol.BasicNetworkProtocol()

		parser = argparse.ArgumentParser(description='Execution module called Node')
		parser.add_argument('--path', action='store',
							dest='pwd', help='Root folder of a Node')
		args = parser.parse_args()

		if args.pwd is not None:
			os.chdir(args.pwd)

	# Overload
	def GatewayConnectedEvent(self):
		pass

	# Overload
	def GatewayDisConnectedEvent(self):
		pass

	# Overload
	def HandleExternalRequest(self, data):
		pass

	# Overload
	def NodeWorker(self):
		pass

	# Overload
	def SendGatewayPing(self):
		pass

	# Overload
	def GetNodeInfoRequestHandler(self, sock, packet):
		pass

	# Overload
	def GetNodeStatusRequestHandler(self, sock, packet):
		pass
	
	# Overload	
	def GetNodeInfoResponseHandler(self, sock, packet):
		pass
	
	# Overload
	def GetNodeStatusResponseHandler(self, sock, packet):
		pass

	# Overload
	def ExitRoutine(self):
		pass

	# Overload
	def NodeConnectHandler(self, conn, addr):
		pass

	# Overload
	def NodeDisconnectHandler(self, sock):
		pass

	# Overload
	def NodeMasterAvailable(self, sock):
		pass

	# Overload
	def PreUILoaderHandler(self):
		pass
	
	def SetState (self, state):
		self.State = state
	
	def GetState (self):
		return self.State

	def RegisterOnNodeChangeHandler(self, sock, packet):
		payload 	= self.BasicProtocol.GetPayloadFromJson(packet)
		piggy 		= self.BasicProtocol.GetPiggybagFromJson(packet)
		item_type 	= payload["item_type"]
		if item_type == 2:
			if packet["additional"]["pipe"] == "GATEWAY":
				payload["webface_indexer"] = piggy["webface_indexer"]
			elif packet["additional"]["pipe"] == "LOCAL_WS":
				payload["ws_id"] = packet["additional"]["ws_id"]
			
			payload["pipe"] = packet["additional"]["pipe"]

		self.OnDeviceChangeList.append({
							'ts':		time.time(),
							'payload':	payload
							})

		return self.BasicProtocol.BuildResponse(packet, {
			'registered': "OK"
		})
	
	def UnregisterOnNodeChangeHandler(self, sock, packet):
		payload 		= self.BasicProtocol.GetPayloadFromJson(packet)
		item_type		= payload["item_type"]

		if item_type == 1: 		# Node
			uuid = payload["uuid"]
			# TODO - Unregister node
		elif item_type == 2: 	# Webface
			webface_indexer = payload["webface_indexer"]
			for item in self.OnDeviceChangeList:
				item_payload = item["payload"]
				if "webface_indexer" in item_payload:
					if item_payload["webface_indexer"] == webface_indexer:
						self.OnDeviceChangeList.remove(item)
						print ("({classname})# Unregistered WEBFACE session ({webface_indexer}))".format(
								classname=self.ClassName,
								webface_indexer=str(webface_indexer)))
						return self.BasicProtocol.BuildResponse(packet, {
							'unregistered': "OK"
						})
		
		return self.BasicProtocol.BuildResponse(packet, {
			'unregistered': "FAILED"
		})
	
	# Overload
	def EmitOnNodeChange(self, payload):
		pass

	def GetFileHandler(self, sock, packet):
		objFile 		= MkSFile.File()
		payload 		= self.BasicProtocol.GetPayloadFromJson(packet)
		uiType 			= payload["ui_type"]
		fileType 		= payload["file_type"]
		fileName 		= payload["file_name"]
		client_type 	= packet["additional"]["client_type"]
		machine_type 	= "pc"

		folder = {
			'config': 		'config',
			'app': 			'app',
			'thumbnail': 	'thumbnail'
		}

		path 	= os.path.join(".","ui",machine_type,folder[uiType],"ui." + fileType)
		content = objFile.Load(path)
		
		if ("html" in fileType):
			content = content.replace("[NODE_UUID]", self.UUID)
			content = content.replace("[GATEWAY_IP]", self.GatewayIP)

			if client_type == "global_ws":
				css = '''
					<link rel="stylesheet" href="/static/lib/bootstrap/css/bootstrap.min.css" crossorigin="anonymous">
					<link rel="stylesheet" href="/static/lib/bootstrap/css/bootstrap-slider.css" crossorigin="anonymous">
					<link rel="stylesheet" href="/static/lib/fontawesome-5.11.2/css/all.min.css">
					<link rel="stylesheet" href="/static/lib/bootstrap4-editable/css/bootstrap-editable.css">
				'''

				script = '''
					<script src="/static/lib/nodes/js/jquery_3_3_1/jquery.min.js"></script>
					<script src="/static/lib/nodes/js/popper_1_14_7/popper.min.js" crossorigin="anonymous"></script>
					<script src="/static/lib/bootstrap/js/bootstrap.min.js" crossorigin="anonymous"></script>
					<script src="/static/lib/bootstrap/js/bootstrap-slider.js" crossorigin="anonymous"></script>
					<script src="/static/lib/nodes/js/feather_4_19/feather.min.js"></script>
					<script src="/static/lib/nodes/map/feather_4_19/feather.min.js.map"></script>
					<script src="/static/lib/bootstrap4-editable/js/bootstrap-editable.min.js"></script>
					
					<script src="mksdk-js/MkSAPI.js"></script>
					<script src="mksdk-js/MkSCommon.js"></script>
					<script src="mksdk-js/MkSGateway.js"></script>
					<script src="mksdk-js/MkSWebface.js"></script>
				'''
			elif client_type == "local_ws":
				css = '''
					<link rel="stylesheet" href="static/lib/bootstrap/css/bootstrap.min.css" crossorigin="anonymous">
					<link rel="stylesheet" href="static/lib/bootstrap/css/bootstrap-slider.css" crossorigin="anonymous">
					<link rel="stylesheet" href="static/lib/fontawesome-5.11.2/css/all.min.css">
					<link rel="stylesheet" href="static/lib/bootstrap4-editable/css/bootstrap-editable.css">
				'''

				script = '''
					<script src="static/lib/nodes/js/jquery_3_3_1/jquery.min.js"></script>
					<script src="static/lib/nodes/js/popper_1_14_7/popper.min.js" crossorigin="anonymous"></script>
					<script src="static/lib/bootstrap/js/bootstrap.min.js" crossorigin="anonymous"></script>
					<script src="static/lib/bootstrap/js/bootstrap-slider.js" crossorigin="anonymous"></script>
					<script src="static/lib/nodes/js/feather_4_19/feather.min.js"></script>
					<script src="static/lib/nodes/map/feather_4_19/feather.min.js.map"></script>
					<script src="static/lib/bootstrap4-editable/js/bootstrap-editable.min.js"></script>
					
					<script src="static/mksdk-js/MkSAPI.js"></script>
					<script src="static/mksdk-js/MkSCommon.js"></script>
					<script src="static/mksdk-js/MkSGateway.js"></script>
					<script src="static/mksdk-js/MkSWebface.js"></script>
				'''
			else:
				css 	= ""
				script 	= ""


		# TODO - Minify file content
		content = content.replace("\t","")

		content = content.replace("[CSS]",css)
		content = content.replace("[SCRIPTS]",script)

		print ("({classname})# Requested file: {path} ({fileName}.{fileType}) ({length})".format(
				classname=self.ClassName,
				path=path,
				fileName=fileName,
				fileType=fileType,
				length=str(len(content))))
		
		return self.BasicProtocol.BuildResponse(packet, {
								'file_type': fileType,
								'ui_type': uiType,
								'content': content.encode('hex')
		})

	def LoadSystemConfig(self):
		if MkSGlobals.OS_TYPE in ["linux", "linux2"]:
			MKS_PATH = os.environ['HOME'] + "/mks/"
		else:
			MKS_PATH = "C:\\mks\\"

		# Information about the node located here.
		strSystemJson 		= self.File.Load("system.json")
		strMachineJson 		= self.File.Load(MKS_PATH + "config.json")

		if (strSystemJson is None or len(strSystemJson) == 0):
			print("(MkSNode)# ERROR - Cannot find system.json file.")
			self.Exit()
			return False

		if (strMachineJson is None or len(strMachineJson) == 0):
			print("(MkSNode)# ERROR - Cannot find config.json file.")
			self.Exit()
			return False
		
		try:
			dataSystem 				= json.loads(strSystemJson)
			dataConfig 				= json.loads(strMachineJson)
			self.NodeInfo 			= dataSystem["node"]
			# Node connection to WS information
			self.Key 				= dataConfig["network"]["key"]
			self.GatewayIP			= dataConfig["network"]["gateway"]
			self.ApiPort 			= dataConfig["network"]["apiport"]
			self.WsPort 			= dataConfig["network"]["wsport"]
			self.ApiUrl 			= "http://{gateway}:{api_port}".format(gateway=self.GatewayIP, api_port=self.ApiPort)
			self.WsUrl				= "ws://{gateway}:{ws_port}".format(gateway=self.GatewayIP, ws_port=self.WsPort)
			# Device information
			self.Type 				= dataSystem["node"]["type"]
			self.OSType 			= dataSystem["node"]["ostype"]
			self.OSVersion 			= dataSystem["node"]["osversion"]
			self.BrandName 			= dataSystem["node"]["brandname"]
			self.Name 				= dataSystem["node"]["name"]
			self.Description 		= dataSystem["node"]["description"]
			# TODO - Why is that?
			if (self.Type == 1):
				self.BoardType 		= dataSystem["node"]["boardType"]
			self.UserDefined		= dataSystem["user"]
			# Device UUID MUST be read from HW device.
			if "True" == dataSystem["node"]["isHW"]:
				self.IsHardwareBased = True
			else:
				self.UUID = dataSystem["node"]["uuid"]
			
			self.SetNodeUUID(self.UUID)
			self.SetNodeType(self.Type)
			self.SetNodeName(self.Name)
			self.SetGatewayIPAddress(self.GatewayIP)
			self.BasicProtocol.SetKey(self.Key)
		except Exception as e:
			print("(MkSNode)# ERROR - Wrong configuration format\n(EXEPTION)# {error}".format(error=str(e)))
			self.Exit()
			return False
		
		print("# TODO - Do we need this DeviceInfo?")
		self.DeviceInfo = MkSDevice.Device(self.UUID, self.Type, self.OSType, self.OSVersion, self.BrandName)
		return True
	
	def InitiateLocalServer(self, port):
		self.UI 			= WebInterface("Context", port)
		self.LocalWebPort	= port
		# Data for the pages.
		jsonUIData 	= {
			'ip': str(self.MyLocalIP),
			'port': str(port),
			'uuid': str(self.UUID)
		}
		data = json.dumps(jsonUIData)
		# UI Pages
		self.UI.AddEndpoint("/", 			"index", 		None, 		data)
		self.UI.AddEndpoint("/nodes", 		"nodes", 		None, 		data)
		self.UI.AddEndpoint("/config", 		"config", 		None, 		data)
		self.UI.AddEndpoint("/app", 		"app", 			None, 		data)
		self.UI.AddEndpoint("/mobile", 		"mobile", 		None, 		data)
		self.UI.AddEndpoint("/mobile/app", 	"mobile/app", 	None, 		data)
		# UI RestAPI
		self.UI.AddEndpoint("/test/<key>", 						"test", 						self.TestWithKeyHandler)
		self.UI.AddEndpoint("/get/socket_list/<key>", 			"get_socket_list", 				self.GetConnectedSocketsListHandler)

	def AppendFaceRestTable(self, endpoint=None, endpoint_name=None, handler=None, args=None, method=['GET']):
		self.UI.AddEndpoint(endpoint, endpoint_name, handler, args, method)

	# TODO - REFACTORING
	def TestWithKeyHandler(self, key):
		if "ykiveish" in key:
			return "{\"response\":\"OK\"}"
		else:
			return ""

	# TODO - REFACTORING
	def GetConnectedSocketsListHandler(self, key):
		if "ykiveish" in key:
			response = "{\"response\":\"OK\",\"payload\":{\"list\":["
			for idx, item in enumerate(self.Connections):
				response += "{\"local_type\":\"" + str(item.LocalType) + "\",\"uuid\":\"" + str(item.UUID) + "\",\"ip\":\"" + str(item.IP) + "\",\"port\":" + str(item.Port) + ",\"type\":\"" + str(item.Type) + "\"},"
			response = response[:-1] + "]}}"
			return jsonify(response)
		else:
			return ""

	def AppendConnection(self, sock, ip, port):
		# Append to recieving data sockets.
		self.RecievingSockets.append(sock)
		# Append to list of all connections.
		node = LocalNode(ip, port, "", "", sock)
		self.Connections.append(node)
		# Increment socket counter.
		self.OpenSocketsCounter += self.OpenSocketsCounter
		return node

	def RemoveConnection(self, sock):
		conn = self.GetConnection(sock)
		if None is not conn:
			# Remove socket from list.
			self.RecievingSockets.remove(conn.Socket)
			# Close connection.
			if conn.Socket is not None:
				conn.Socket.close()
			# Remove LocalNode from the list.
			self.Connections.remove(conn)
			# Deduce socket counter.
			self.OpenSocketsCounter -= self.OpenSocketsCounter

	def GetConnection(self, sock):
		for conn in self.Connections:
			if conn.Socket == sock:
				return conn
		return None

	def GetNodeByUUID(self, uuid):
		for conn in self.Connections:
			if conn.UUID == uuid:
				return conn
		return None

	def GetNode(self, ip, port):
		for conn in self.Connections:
			if conn.IP == ip and conn.Port == port:
				return conn
		return None

	def TryStartListener(self):
		try:
			print ("(MkSAbstractNode)# Start listener...")
			self.ServerSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
			self.ServerSocket.setblocking(0)

			self.ServerSocket.bind(self.ServerAdderss)
			# [socket, ip_address, port]
			node = self.AppendConnection(self.ServerSocket, self.MyLocalIP, self.ServerAdderss[1])
			node.LocalType 	= "LISTENER"
			node.UUID 		= self.UUID
			node.Type 		= self.Type

			self.ServerSocket.listen(32)
			self.IsLocalSocketRunning = True

			# Run preloader for UI interface
			if self.UI is None:
				print ("(MkSAbstractNode)# Executing UI preloader (Only valid for local UI aka Webface)")
				self.PreUILoaderHandler()

			# Let know registered method about local server start.
			if self.OnLocalServerListenerStartedCallback is not None:
				self.OnLocalServerListenerStartedCallback(self.ServerSocket, self.MyLocalIP, self.ServerAdderss[1])

			# Run UI thread
			if self.UI is None:
				print ("(MkSAbstractNode)# Local UI(Webface) is not set ... (NULL)")
			else:
				print ("(MkSAbstractNode)# Running local UI(Webface)")
				self.UI.Run()

			return True
		except Exception as e:
			self.RemoveConnection(self.ServerSocket)
			print ("(MkSAbstractNode)# Failed to open listener, ", str(self.ServerAdderss[1]), e)
			return False
	
	def LocalWSDataArrivedHandler(self, ws, data):
		print("({classname})# (WS) {0}".format(data,classname=self.ClassName))
		try:
			packet 		= json.loads(data)
			if ("HANDSHAKE" == self.BasicProtocol.GetMessageTypeFromJson(packet)):
				return
			
			command 	= self.BasicProtocol.GetCommandFromJson(packet)
			direction 	= self.BasicProtocol.GetDirectionFromJson(packet)
			destination = self.BasicProtocol.GetDestinationFromJson(packet)
			source 		= self.BasicProtocol.GetSourceFromJson(packet)

			packet["additional"]["client_type"] = "local_ws"

			print ("({classname})# [{direction}] {source} -> {dest} [{cmd}]".format(
						classname=self.ClassName,
						direction=direction,
						source=source,
						dest=destination,
						cmd=command))

			if direction in "request":
				if command in self.NodeRequestHandlers.keys():
					message = self.NodeRequestHandlers[command](ws, packet)
					ws.send(message)
				else:
					# This command belongs to the application level
					if self.OnApplicationRequestCallback is not None:
						message = self.OnApplicationRequestCallback(ws, packet)
						ws.send(message)
			elif direction in "response":
				if command in self.NodeResponseHandlers.keys():
					self.NodeResponseHandlers[command](ws, packet)
				else:
					# This command belongs to the application level
					if self.OnApplicationResponseCallback is not None:
						self.OnApplicationResponseCallback(ws, packet)
			else:
				pass
		except Exception as e:
			print ("[AbstractNode] LocalWSDataArrivedHandler ERROR", e, data)

	def DataSocketInputHandler(self, sock, data):
		try:
			packet 		= json.loads(data)
			command 	= self.BasicProtocol.GetCommandFromJson(packet)
			direction 	= self.BasicProtocol.GetDirectionFromJson(packet)
			destination = self.BasicProtocol.GetDestinationFromJson(packet)
			source 		= self.BasicProtocol.GetSourceFromJson(packet)

			packet["additional"]["client_type"] = "global_ws"

			print ("({classname})# [{direction}] {source} -> {dest} [{cmd}]".format(
						classname=self.ClassName,
						direction=direction,
						source=source,
						dest=destination,
						cmd=command))
			
			# Is this packet for me?
			if destination in self.UUID or (destination in "MASTER" and 1 == self.Type):
				if direction in "request":
					if command in self.NodeRequestHandlers.keys():
						message = self.NodeRequestHandlers[command](sock, packet)
						packet  = self.BasicProtocol.AppendMagic(message)
						sock.send(packet)
					else:
						# This command belongs to the application level
						if self.OnApplicationRequestCallback is not None:
							message = self.OnApplicationRequestCallback(sock, packet)
							message  = self.BasicProtocol.AppendMagic(message)
							sock.send(message)
				elif direction in "response":
					if command in self.NodeResponseHandlers.keys():
						self.NodeResponseHandlers[command](sock, packet)
					else:
						# This command belongs to the application level
						if self.OnApplicationResponseCallback is not None:
							self.OnApplicationResponseCallback(sock, packet)
				else:
					pass
			else:
				# This massage is external (MOSTLY MASTER)
				if self.Network is not None:
					self.Network.SendWebSocket(data)

		except Exception as e:
			print ("[AbstractNode] DataSocketInputHandler ERROR", e, data)

	def ConnectNodeSocket(self, ip_addr_port):
		sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		sock.settimeout(5)
		try:
			sock.connect(ip_addr_port)
			return sock, True
		except:
			return None, False

	def DisconnectNodeSocket(self, sock):
		self.RemoveConnection(sock)

	def NodeLocalNetworkConectionListener(self):
		# AF_UNIX, AF_LOCAL   Local communication
       	# AF_INET             IPv4 Internet protocols
       	# AF_INET6            IPv6 Internet protocols
       	# AF_PACKET           Low level packet interface
       	#
       	# SOCK_STREAM     	Provides sequenced, reliable, two-way, connection-
        #               	based byte streams.  An out-of-band data transmission
        #               	mechanism may be supported.
        #
        # SOCK_DGRAM      	Supports datagrams (connectionless, unreliable
        #               	messages of a fixed maximum length).
        #
       	# SOCK_SEQPACKET  	Provides a sequenced, reliable, two-way connection-
        #               	based data transmission path for datagrams of fixed
        #               	maximum length; a consumer is required to read an
        #               	entire packet with each input system call.
        #
       	# SOCK_RAW        	Provides raw network protocol access.
       	#
       	# SOCK_RDM        	Provides a reliable datagram layer that does not
        #               	guarantee ordering.
		if self.IsListenerEnabled is True:
			while self.IsLocalSocketRunning is False:
				self.TryStartListener()
		else:
			self.IsLocalSocketRunning = True

		# Raise event for user
		if self.OnLocalServerStartedCallback is not None:
			self.OnLocalServerStartedCallback()

		while self.IsLocalSocketRunning is True:
			try:
				readable, writable, exceptional = select.select(self.RecievingSockets, self.SendingSockets, self.RecievingSockets, 0.5)

				# Socket management.
				for sock in readable:
					if sock is self.ServerSocket and True == self.IsListenerEnabled:
						conn, addr = sock.accept()
						conn.setblocking(0)
						self.AppendConnection(conn, addr[0], addr[1])
						self.NodeConnectHandler(conn, addr)
						
						# Raise event for user
						if self.OnAceptNewConnectionCallback is not None:
							self.OnAceptNewConnectionCallback(conn)
					else:
						try:
							if sock is not None:
								data = sock.recv(2048)
								dataLen = len(data)
								while dataLen == 2048:
									chunk = sock.recv(2048)
									data += chunk
									dataLen = len(chunk)
						except Exception as e:
							print ("[AbstractNode] Recieve ERROR", e)
							self.NodeDisconnectHandler(sock)
							self.RemoveConnection(sock)
						else:
							if data:
								# Each makesense packet should start from magic number "MKS"
								if "MKSS" in data[:4]:
									# One packet can hold multiple MKS messages.
									multiData = data.split("MKSS:")
									for packet in multiData[1:]:
										# TODO - Must handled in different thread
										if "MKSE" in packet:
											self.DataSocketInputHandler(sock, packet[:-5])
								else:
									print ("[AbstractNode] Data Invalid")
							else:
								self.NodeDisconnectHandler(sock)
								# Raise event for user
								if self.OnTerminateConnectionCallback is not None:
									self.OnTerminateConnectionCallback(sock)
								self.RemoveConnection(sock)

				for sock in exceptional:
					print ("[AbstractNode] Socket Exceptional")
			except Exception as e:
				print ("[AbstractNode] [ERROR]", e)

		# Clean all resorses before exit.
		self.CleanAllSockets()
		print ("[AbstractNode] Exit execution thread")
		self.ExitLocalServerEvent.set()

	def ConnectNode(self, ip, port):
		sock, status = self.ConnectNodeSocket((ip, port))
		if True == status:
			node = self.AppendConnection(sock, ip, port)
			node.LocalType = "NODE"
		return sock, status

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

	def FindMasters(self):
		# Let user know master search started.
		if self.OnMasterSearchCallback is not None:
			self.OnMasterSearchCallback()
		# Find all master nodes on the network.
		ips = MkSUtils.FindLocalMasterNodes()
		for ip in ips:
			if self.GetNode(ip, 16999) is None:
				# Master not in list, can make connection
				sock, status = self.ConnectNodeSocket((ip, 16999))
				if True == status:
					node = self.AppendConnection(sock, ip, 16999)
					node.LocalType = "MASTER"
					# Raise event
					if self.OnMasterFoundCallback is not None:
						self.OnMasterFoundCallback([sock, ip])
					self.NodeMasterAvailable(sock)
				else:
					print ("[Node Server] Could not connect")
			else:
				if self.OnMasterFoundCallback is not None:
					self.OnMasterFoundCallback([None, ip])
		return len(ips)

	def CleanAllSockets(self):
		for conn in self.Connections:
			self.RemoveConnection(conn.Socket)
		
		if len(self.Connections) > 0:
			print ("Still live socket exist")
			for conn in self.Connections:
				self.RemoveConnection(conn.Socket)

	def GetConnections(self):
		return self.Connections

	def SetNodeUUID(self, uuid):
		self.UUID = uuid

	def SetNodeType(self, node_type):
		self.Type = node_type
	
	def SetNodeName(self, name):
		self.Name = name
	
	def SetGatewayIPAddress(self, ip):
		self.GatewayIP = ip
	
	def SetWebServiceStatus(self, is_enabled):
		self.IsNodeWSServiceEnabled = is_enabled

	def SetLocalServerStatus(self, is_enabled):
		self.IsNodeLocalServerEnabled = is_enabled
	
	def StartLocalNode(self):
		print("TODO - (MkSNode.Run) Missing management of network HW disconnection")
		thread.start_new_thread(self.NodeLocalNetworkConectionListener, ())

	def Run (self, callback):
		# Will be called each half a second.
		self.WorkingCallback = callback
		self.LocalWSManager.OnDataArrivedEvent = self.LocalWSDataArrivedHandler
		self.ExitEvent.clear()
		self.ExitLocalServerEvent.clear()
		# Initial state is connect to Gateway.
		self.SetState("INIT")

		# Read sytem configuration
		print("(MkSAbstractNode)# Load system configuration ...")
		if (self.LoadSystemConfig() is False):
			print("(MkSAbstractNode)# Load system configuration ... FAILED")
			return

		# Start local node dervice thread
		if self.IsNodeLocalServerEnabled is True:
			self.StartLocalNode()

		# Waiting here till SIGNAL from OS will come.
		while self.IsMainNodeRunnig:
			# State machine management
			self.Method = self.States[self.State]
			self.Method()

			# User callback
			if ("WORKING" == self.GetState() and self.SystemLoaded is True):
				self.WorkingCallback()
				if self.LocalWSManager.IsServerRunnig() is False:
					self.Exit()
			self.Ticker += 1
			time.sleep(0.5)
		
		print ("(MkSAbstractNode)# Exit Node ...")
		self.ExitEvent.set()
		if self.IsNodeWSServiceEnabled is True:
			if self.Network is not None:
				self.Network.Disconnect()

		if self.IsHardwareBased is True:
			self.Connector.Disconnect()
		
		# TODO - Don't think we need this event.
		self.ExitEvent.wait()
		if self.IsLocalSocketRunning is True:
			self.ExitLocalServerEvent.wait()
	
	def Stop (self):
		print ("(MkSAbstractNode)# Stop Node ...")
		self.IsMainNodeRunnig 		= False
		self.IsLocalSocketRunning 	= False
	
	def Pause (self):
		pass
	
	def Exit (self):
		self.Stop()
