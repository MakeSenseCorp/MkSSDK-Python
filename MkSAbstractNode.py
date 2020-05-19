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
		self.OnWSDisconnected 		= None
	
	def AppendSocket(self, ws_id, ws):
		print ("({classname})# Append new connection ({0})".format(ws_id, classname=self.ClassName))
		self.ApplicationSockets[ws_id] = ws
	
	def RemoveSocket(self, ws_id):
		print ("({classname})# Remove connection ({0})".format(ws_id, classname=self.ClassName))
		del self.ApplicationSockets[ws_id]
		if self.OnWSDisconnected is not None:
			self.OnWSDisconnected(ws_id)
	
	def WSDataArrived(self, ws, data):
		# TODO - Append webface type
		packet	= json.loads(data)
		if ("HANDSHAKE" == packet['header']['message_type']):
			return
		
		packet["additional"]["ws_id"] 	= id(ws)
		packet["additional"]["pipe"]  	= "LOCAL_WS"
		packet["stamping"] 				= ['local_ws']
		data = json.dumps(packet)

		if self.OnDataArrivedEvent is not None:
			self.OnDataArrivedEvent(ws, data)
	
	def Send(self, ws_id, data):
		if ws_id in self.ApplicationSockets:
			self.ApplicationSockets[ws_id].send(data)
		else:
			print ("({classname})# ERROR - This socket ({0}) does not exist. (Might be closed)".format(ws_id, classname=self.ClassName))
	
	def IsServerRunnig(self):
		return self.ServerRunning

	def Worker(self):
		try:
			server = WebSocketServer(('', 1982), Resource(OrderedDict([('/', NodeWSApplication)])))

			self.ServerRunning = True
			print ("({classname})# Staring local WS server ...".format(classname=self.ClassName))
			server.serve_forever()
		except Exception as e:
			print ("({classname})# [ERROR] Stoping local WS server ... {0}".format(str(e), classname=self.ClassName))
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
		#print ("({classname})# MESSAGE RECIEVED {0} {1}".format(id(self.ws),message,classname=self.ClassName))
		if message is not None:
			WSManager.WSDataArrived(self.ws, message)
		else:
			print ("({classname})# ERROR - Message is not valid".format(classname=self.ClassName))

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
		self.Info 		= None
	
	def SetNodeName(self, name):
		self.Name = name

class AbstractNode():
	def __init__(self):
		self.ClassName								= ""
		self.File 									= MkSFile.File()
		self.Connector 								= None
		self.Network								= None
		self.LocalWSManager							= WSManager
		self.MKSPath								= ""
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
		self.IsMaster 								= False
		# State machine
		self.State 									= 'IDLE' # Current state of node
		self.States 								= None	 # States list
		# Locks and Events
		self.ExitEvent 								= threading.Event()
		self.ExitLocalServerEvent					= threading.Event()
		# Debug
		self.DebugMode								= False	
		self.Logger 								= None
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
		self.OnGetNodesListCallback 				= None # Get all online nodes from GLOBAL gateway (Not implemented yet)
		# Registered items
		self.OnDeviceChangeList						= [] # Register command "register_on_node_change"
		# Synchronization
		self.DeviceChangeListLock 					= threading.Lock()
		# Services
		self.IPScannerServiceUUID					= ""
		self.EMailServiceUUID						= ""
		self.SMSServiceUUID							= ""
		self.Services 								= {}
		self.NetworkOnlineDevicesList 				= []
		# Timers
		self.ServiceSearchTS						= time.time()
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
		self.MyLocalIP 								= ""
		self.NetworkCards 							= MkSUtils.GetIPList()
		# Handlers
		self.NodeRequestHandlers					= {
			'get_node_info': 						self.GetNodeInfoRequestHandler,
			'get_node_status': 						self.GetNodeStatusRequestHandler,
			'get_file': 							self.GetFileHandler,
			'register_on_node_change':				self.RegisterOnNodeChangeHandler,
			'unregister_on_node_change':			self.UnregisterOnNodeChangeHandler,
			'find_node':							self.FindNodeRequestHandler,
			'master_append_node':					self.MasterAppendNodeRequestHandler,
			'master_remove_node':					self.MasterRemoveNodeRequestHandler
		}
		self.NodeResponseHandlers					= {
			'get_node_info': 						self.GetNodeInfoResponseHandler,
			'get_node_status': 						self.GetNodeStatusResponseHandler,
			'find_node': 							self.FindNodeResponseHandler,
			'master_append_node':					self.MasterAppendNodeResponseHandler,
			'master_remove_node':					self.MasterRemoveNodeResponseHandler,
			'get_online_devices':					self.GetOnlineDevicesHandler
		}
		# LocalFace UI
		self.UI 									= None
		self.LocalWebPort							= ""
		self.BasicProtocol 							= MkSBasicNetworkProtocol.BasicNetworkProtocol()
		#print(self.NetworkCards)

		self.Services[101] = {
			'uuid': "",
			'name': "eMail",
			'enabled': 0
		}

		self.Services[102] = {
			'uuid': "",
			'name': "SMS",
			'enabled': 0
		}

		self.Services[103] = {
			'uuid': "",
			'name': "IP Scanner",
			'enabled': 0
		}

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

	# Overload
	def SendRequest(self, uuid, msg_type, command, payload, additional):
		pass

	# Overload
	def EmitOnNodeChange(self, payload):
		pass

	def GetOnlineDevicesHandler(self, sock, packet):
		self.LogMSG("({classname})# Online network device list ...".format(classname=self.ClassName))
		payload = self.BasicProtocol.GetPayloadFromJson(packet)
		self.NetworkOnlineDevicesList = payload["online_devices"]

	def MasterAppendNodeRequestHandler(self, sock, packet):
		pass

	def MasterRemoveNodeRequestHandler(self, sock, packet):
		pass

	def MasterAppendNodeResponseHandler(self, sock, packet):
		payload 	= self.BasicProtocol.GetPayloadFromJson(packet)
		additional = self.BasicProtocol.GetAdditionalFromJson(packet)

		additional["online"] = True
		packet = self.BasicProtocol.SetAdditional(packet, additional)

		if payload["tagging"]["cat_1"] == "service":
			self.Services[payload["type"]]["uuid"] 		= payload["uuid"]
			self.Services[payload["type"]]["enabled"] 	= 1
		self.GetNodeInfoResponseHandler(sock, packet)

	def MasterRemoveNodeResponseHandler(self, sock, packet):
		payload 	= self.BasicProtocol.GetPayloadFromJson(packet)
		additional = self.BasicProtocol.GetAdditionalFromJson(packet)
		
		additional["online"] = False
		packet = self.BasicProtocol.SetAdditional(packet, additional)

		if payload["tagging"]["cat_1"] == "service":
			self.Services[payload["type"]]["uuid"] 		= ""
			self.Services[payload["type"]]["enabled"] 	= 0
		self.GetNodeInfoResponseHandler(sock, packet)

	def FindNodeResponseHandler(self, sock, packet):
		payload 	= self.BasicProtocol.GetPayloadFromJson(packet)
		additional 	= self.BasicProtocol.GetAdditionalFromJson(packet)

		additional["online"] = True
		packet = self.BasicProtocol.SetAdditional(packet, additional)

		if payload["tagging"]["cat_1"] == "service":
			self.Services[payload["type"]]["uuid"] 		= payload["uuid"]
			self.Services[payload["type"]]["enabled"] 	= 1
		self.GetNodeInfoResponseHandler(sock, packet)

	def FindNodeRequestHandler(self, sock, packet):
		self.LogMSG("({classname})# Search node request ...".format(classname=self.ClassName))
		payload = self.BasicProtocol.GetPayloadFromJson(packet)
		cat_1 = payload["cat_1"]
		cat_2 = payload["cat_2"]
		cat_3 = payload["cat_3"]
		node_type = payload["type"]

		if str(node_type) == str(self.Type):
			return self.BasicProtocol.BuildResponse(packet, self.NodeInfo)

		if cat_1 in "service" and cat_2 in "network" and cat_3 in "ip_scanner" and node_type == 0:
			return self.BasicProtocol.BuildResponse(packet, self.NodeInfo)
		else:
			return ""
	
	def SetState (self, state):
		self.State = state
	
	def GetState (self):
		return self.State
	
	def GetServices(self):
		enabled_services = []
		for key in self.Services:
			if self.Services[key]["enabled"] == 1:
				enabled_services.append({ 
					'name': self.Services[key]["name"],
					'type': key
				})
		return enabled_services

	def FindSMSService(self):
		self.FindNode("service", "network", "sms", 0)
	
	def FindEmailService(self):
		self.FindNode("service", "network", "email", 0)

	def FindIPScannerService(self):
		self.FindNode("service", "network", "ip_scanner", 0)
	
	def ScanNetwork(self):
		self.SendRequestToNode(self.Services[103]["uuid"], "get_online_devices", {})

	def GetNetworkOnlineDevicesList(self):
		return self.NetworkOnlineDevicesList

	def FindNode(self, category1, category2, category3, node_type):
		payload = {
			'cat_1': category1,
			'cat_2': category2,
			'cat_3': category3,
			'type': node_type
		}
		self.SendRequest("BROADCAST", "BROADCAST", "find_node", payload, {})

	def SendRequestToNode(self, uuid, command, payload):
		self.SendRequest(uuid, "DIRECT", command, payload, {})

	def AppendDeviceChangeListNode(self, payload):
		self.DeviceChangeListLock.acquire()
		for item in self.OnDeviceChangeList:
			if item["uuid"] == payload["uuid"]:
				self.DeviceChangeListLock.release()
				return

		self.OnDeviceChangeList.append({
			'ts':		time.time(),
			'payload':	payload
		})		
		self.DeviceChangeListLock.release()

	def AppendDeviceChangeListLocal(self, payload):
		self.DeviceChangeListLock.acquire()
		for item in self.OnDeviceChangeList:
			if item["payload"]["ws_id"] == payload["ws_id"]:
				self.DeviceChangeListLock.release()
				return

		self.OnDeviceChangeList.append({
			'ts':		time.time(),
			'payload':	payload
		})		
		self.DeviceChangeListLock.release()
	
	def AppendDeviceChangeListGlobal(self, payload):
		self.DeviceChangeListLock.acquire()
		for item in self.OnDeviceChangeList:
			if item["payload"]["webface_indexer"] == payload["webface_indexer"]:
				self.DeviceChangeListLock.release()
				return

		self.OnDeviceChangeList.append({
			'ts':		time.time(),
			'payload':	payload
		})		
		self.DeviceChangeListLock.release()
	
	def RemoveDeviceChangeListNode(self, uuid):
		# Context of geventwebsocket (PAY ATTENTION)
		self.DeviceChangeListLock.acquire()
		is_removed = False

		for i in xrange(len(self.OnDeviceChangeList) - 1, -1, -1):
			item = self.OnDeviceChangeList[i]
			item_payload = item["payload"]
			if item_payload["uuid"] == uuid:
				del self.OnDeviceChangeList[i]
				self.LogMSG("({classname})# Unregistered WEBFACE local session ({uuid}) ({length}))".format(classname=self.ClassName,
						uuid=str(uuid),
						length=len(self.OnDeviceChangeList)))
				is_removed = True
		self.DeviceChangeListLock.release()
		return is_removed

	def RemoveDeviceChangeListLocal(self, id):
		# Context of geventwebsocket (PAY ATTENTION)
		self.DeviceChangeListLock.acquire()
		is_removed = False

		for i in xrange(len(self.OnDeviceChangeList) - 1, -1, -1):
			item = self.OnDeviceChangeList[i]
			item_payload = item["payload"]
			if "ws_id" in item_payload:
				if item_payload["ws_id"] == id:
					del self.OnDeviceChangeList[i]
					self.LogMSG("({classname})# Unregistered WEBFACE local session ({ws_id}) ({length}))".format(classname=self.ClassName,
							ws_id=str(id),
							length=len(self.OnDeviceChangeList)))
					is_removed = True
		self.DeviceChangeListLock.release()
		return is_removed
	
	def RemoveDeviceChangeListGlobal(self, id):
		self.DeviceChangeListLock.acquire()
		for item in self.OnDeviceChangeList:
			item_payload = item["payload"]
			if "webface_indexer" in item_payload:
				if item_payload["webface_indexer"] == id:
					self.OnDeviceChangeList.remove(item)
					self.LogMSG("({classname})# Unregistered WEBFACE global session ({webface_indexer}))".format(classname=self.ClassName,
							webface_indexer=str(id)))
					self.DeviceChangeListLock.release()
					return True
		self.DeviceChangeListLock.release()
		return False

	def UnRegisterOnNodeChangeEvent(self, uuid):
		self.SendRequestToNode(uuid, "unregister_on_node_change", {
				'item_type': 1,
				'uuid':	self.UUID
			})

	def RegisterOnNodeChangeEvent(self, uuid):
		self.SendRequestToNode(uuid, "register_on_node_change", {
				'item_type': 1,
				'uuid':	self.UUID
			})
	
	def RegisterOnNodeChangeHandler(self, sock, packet):
		self.LogMSG("({classname})# On Node change request recieved ....".format(classname=self.ClassName))
		payload 	= self.BasicProtocol.GetPayloadFromJson(packet)
		item_type 	= payload["item_type"]
		# Node
		if item_type == 1:
			self.AppendDeviceChangeListNode(payload)
		# Webface
		elif item_type == 2:
			piggy = self.BasicProtocol.GetPiggybagFromJson(packet)
			payload["pipe"] = packet["additional"]["pipe"]
			if packet["additional"]["pipe"] == "GATEWAY":
				payload["webface_indexer"] = piggy["webface_indexer"]
				self.AppendDeviceChangeListGlobal(payload)
			elif packet["additional"]["pipe"] == "LOCAL_WS":
				payload["ws_id"] = packet["additional"]["ws_id"]
				self.AppendDeviceChangeListLocal(payload)
			
			return self.BasicProtocol.BuildResponse(packet, {
				'registered': "OK"
			})
		
		return self.BasicProtocol.BuildResponse(packet, {
			'registered': "NO REGISTERED"
		})
	
	def UnregisterOnNodeChangeHandler(self, sock, packet):
		payload 		= self.BasicProtocol.GetPayloadFromJson(packet)
		item_type		= payload["item_type"]

		# Node
		if item_type == 1:
			uuid = payload["uuid"]
			self.RemoveDeviceChangeListNode(uuid)
		# Webface
		elif item_type == 2:
			if packet["additional"]["pipe"] == "GATEWAY":
				webface_indexer = payload["webface_indexer"]
				if self.UnregisterGlobalWS(webface_indexer) is True:
					return self.BasicProtocol.BuildResponse(packet, {
						'unregistered': "OK"
					})
			elif packet["additional"]["pipe"] == "LOCAL_WS":
				ws_id = packet["additional"]["ws_id"]
				if self.UnregisterLocalWS(ws_id) is True:
					return self.BasicProtocol.BuildResponse(packet, {
						'unregistered': "OK"
					})
		
		return self.BasicProtocol.BuildResponse(packet, {
			'unregistered': "FAILED"
		})
	
	def UnregisterLocalWS(self, id):
		return self.RemoveDeviceChangeListLocal(id)

	def UnregisterGlobalWS(self, id):
		return self.RemoveDeviceChangeListGlobal(id)

	def GetFileHandler(self, sock, packet):
		objFile 		= MkSFile.File()
		payload 		= self.BasicProtocol.GetPayloadFromJson(packet)
		uiType 			= payload["ui_type"]
		fileType 		= payload["file_type"]
		fileName 		= payload["file_name"]
		client_type 	= packet["additional"]["client_type"]
		stamping 		= packet["stamping"]
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
			if stamping is None:
				self.LogMSG("({classname})# [ERROR] Missing STAMPING in packet ...".format(classname=self.ClassName))
				content = content.replace("[GATEWAY_IP]", self.GatewayIP)
			else:
				if "cloud_t" in stamping:
					content = content.replace("[GATEWAY_IP]", "ec2-54-188-199-33.us-west-2.compute.amazonaws.com")
				else:
					content = content.replace("[GATEWAY_IP]", self.GatewayIP)

			if client_type == "global_ws":
				css = '''
					<link rel="stylesheet" href="/static/lib/bootstrap/css/bootstrap.min.css" crossorigin="anonymous">
					<link rel="stylesheet" href="/static/lib/bootstrap/css/bootstrap-slider.css" crossorigin="anonymous">
					<link rel="stylesheet" href="/static/lib/fontawesome-5.11.2/css/all.min.css">
					<link rel="stylesheet" href="/static/lib/bootstrap4-editable/css/bootstrap-editable.css">
					<link rel="stylesheet" href="/static/lib/chartjs/2.9.3/Chart.min.css">
					<link rel="stylesheet" href="/static/lib/datetimepicker/bootstrap-datetimepicker.min.css">
				'''

				script = '''
					<script src="/static/lib/nodes/js/jquery_3_3_1/jquery.min.js"></script>
					<script src="/static/lib/nodes/js/popper_1_14_7/popper.min.js" crossorigin="anonymous"></script>
					<script src="/static/lib/bootstrap/js/bootstrap.min.js" crossorigin="anonymous"></script>
					<script src="/static/lib/bootstrap/js/bootstrap-slider.js" crossorigin="anonymous"></script>
					<script src="/static/lib/nodes/js/feather_4_19/feather.min.js"></script>
					<script src="/static/lib/nodes/map/feather_4_19/feather.min.js.map"></script>
					<script src="/static/lib/bootstrap4-editable/js/bootstrap-editable.min.js"></script>
					<script src="/static/lib/chartjs/2.9.3/Chart.min.js"></script>
					<script src="/static/lib/datetimepicker/bootstrap-datetimepicker.min.js"></script>
					
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
					<link rel="stylesheet" href="static/lib/chartjs/2.9.3/Chart.min.css">
					<link rel="stylesheet" href="static/lib/datetimepicker/bootstrap-datetimepicker.min.css">
				'''

				script = '''
					<script src="static/lib/nodes/js/jquery_3_3_1/jquery.min.js"></script>
					<script src="static/lib/nodes/js/popper_1_14_7/popper.min.js" crossorigin="anonymous"></script>
					<script src="static/lib/bootstrap/js/bootstrap.min.js" crossorigin="anonymous"></script>
					<script src="static/lib/bootstrap/js/bootstrap-slider.js" crossorigin="anonymous"></script>
					<script src="static/lib/nodes/js/feather_4_19/feather.min.js"></script>
					<script src="static/lib/nodes/map/feather_4_19/feather.min.js.map"></script>
					<script src="static/lib/bootstrap4-editable/js/bootstrap-editable.min.js"></script>
					<script src="static/lib/chartjs/2.9.3/Chart.min.js"></script>
					<script src="static/lib/datetimepicker/bootstrap-datetimepicker.min.js"></script>
					
					<script src="static/mksdk-js/MkSCommon.js"></script>
					<script src="static/mksdk-js/MkSAPI.js"></script>
					<script src="static/mksdk-js/MkSGateway.js"></script>
					<script src="static/mksdk-js/MkSWebface.js"></script>
				'''
			else:
				css 	= ""
				script 	= ""
		
			content = content.replace("[CSS]",css)
			content = content.replace("[SCRIPTS]",script)


		# TODO - Minify file content
		content = content.replace("\t","")
		self.LogMSG("({classname})# Requested file: {path} ({fileName}.{fileType}) ({length})".format(classname=self.ClassName,
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
		self.MKSPath = os.path.join(os.environ['HOME'],"mks")
		self.LogMSG("({classname})# MakeSense HOME folder '{0}'".format(self.MKSPath, classname=self.ClassName))
		# Information about the node located here.
		strSystemJson 		= self.File.Load("system.json") # Located in node context
		strMachineJson 		= self.File.Load(os.path.join(self.MKSPath,"config.json"))

		if (strSystemJson is None or len(strSystemJson) == 0):
			self.LogMSG("({classname})# ERROR - Cannot find system.json file.".format(classname=self.ClassName))
			self.Exit()
			return False

		if (strMachineJson is None or len(strMachineJson) == 0):
			self.LogMSG("({classname})# ERROR - Cannot find config.json file.".format(classname=self.ClassName))
			self.Exit()
			return False
		
		try:
			dataSystem 				= json.loads(strSystemJson)
			dataConfig 				= json.loads(strMachineJson)

			for network in self.NetworkCards:
				if network["iface"] in dataConfig["network"]["iface"]:
					self.MyLocalIP = network["ip"]

			self.NodeInfo 			= dataSystem["node"]["info"]
			self.ServiceDepened 	= dataSystem["node"]["service"]["depend"]
			# Node connection to WS information
			self.Key 				= dataConfig["network"]["key"]
			self.GatewayIP			= dataConfig["network"]["gateway"]
			self.ApiPort 			= dataConfig["network"]["apiport"]
			self.WsPort 			= dataConfig["network"]["wsport"]
			self.ApiUrl 			= "http://{gateway}:{api_port}".format(gateway=self.GatewayIP, api_port=self.ApiPort)
			self.WsUrl				= "ws://{gateway}:{ws_port}".format(gateway=self.GatewayIP, ws_port=self.WsPort)
			# Device information
			self.Type 				= self.NodeInfo["type"]
			self.OSType 			= self.NodeInfo["ostype"]
			self.OSVersion 			= self.NodeInfo["osversion"]
			self.BrandName 			= self.NodeInfo["brandname"]
			self.Name 				= self.NodeInfo["name"]
			self.Description 		= self.NodeInfo["description"]
			# TODO - Why is that?
			if (self.Type == 1):
				self.BoardType 		= self.NodeInfo["boardType"]
			self.UserDefined		= dataSystem["user"]
			# Device UUID MUST be read from HW device.
			if "True" == self.NodeInfo["isHW"]:
				self.IsHardwareBased = True
			else:
				self.UUID = self.NodeInfo["uuid"]
			
			self.SetNodeUUID(self.UUID)
			self.SetNodeType(self.Type)
			self.SetNodeName(self.Name)
			self.SetGatewayIPAddress(self.GatewayIP)
			self.BasicProtocol.SetKey(self.Key)
		except Exception as e:
			self.LogMSG("({classname})# ERROR - Wrong configuration format\n(EXEPTION)# {error}".format(error=str(e),classname=self.ClassName))
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
			self.LogMSG("({classname})# Start listener...".format(classname=self.ClassName))
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
				self.LogMSG("({classname})# Executing UI preloader (Only valid for local UI aka Webface)".format(classname=self.ClassName))
				self.PreUILoaderHandler()

			# Let know registered method about local server start.
			if self.OnLocalServerListenerStartedCallback is not None:
				self.OnLocalServerListenerStartedCallback(self.ServerSocket, self.MyLocalIP, self.ServerAdderss[1])

			# Run UI thread
			if self.UI is None:
				self.LogMSG("({classname})# Local UI(Webface) is not set ... (NULL)".format(classname=self.ClassName))
			else:
				self.LogMSG("({classname})# Running local UI(Webface)".format(classname=self.ClassName))
				self.UI.Run()

			return True
		except Exception as e:
			self.RemoveConnection(self.ServerSocket)
			self.LogMSG("({classname})# Failed to open listener, {0}\n[EXCEPTION] {1}".format(str(self.ServerAdderss[1]),e,classname=self.ClassName))
			return False
	
	def LocalWSDisconnectedHandler(self, ws_id):
		self.UnregisterLocalWS(ws_id)

	def LocalWSDataArrivedHandler(self, ws, data):
		# print("({classname})# (WS) {0}".format(data,classname=self.ClassName))
		try:
			packet 		= json.loads(data)
			if ("HANDSHAKE" == self.BasicProtocol.GetMessageTypeFromJson(packet)):
				return
			
			command 	= self.BasicProtocol.GetCommandFromJson(packet)
			direction 	= self.BasicProtocol.GetDirectionFromJson(packet)
			destination = self.BasicProtocol.GetDestinationFromJson(packet)
			source 		= self.BasicProtocol.GetSourceFromJson(packet)

			packet["additional"]["client_type"] = "local_ws"

			self.LogMSG("({classname})# WS LOCAL [{direction}] {source} -> {dest} [{cmd}]".format(classname=self.ClassName,
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
			self.LogMSG("({classname})# ERROR - Wrong configuration format\n(EXEPTION)# {error}\n{data}".format(error=str(e),data=data,classname=self.ClassName))

	def DataSocketInputHandler(self, sock, data):
		try:
			packet 		= json.loads(data)
			messageType = self.BasicProtocol.GetMessageTypeFromJson(packet)
			command 	= self.BasicProtocol.GetCommandFromJson(packet)
			direction 	= self.BasicProtocol.GetDirectionFromJson(packet)
			destination = self.BasicProtocol.GetDestinationFromJson(packet)
			source 		= self.BasicProtocol.GetSourceFromJson(packet)

			packet["additional"]["client_type"] = "global_ws"
			self.LogMSG("({classname})# SOCK [{direction}] {source} -> {dest} [{cmd}]".format(classname=self.ClassName,
						direction=direction,
						source=source,
						dest=destination,
						cmd=command))
			
			if messageType == "BROADCAST":
				pass

			if destination in self.UUID and source in self.UUID:
				return
			
			# Is this packet for me?
			if destination in self.UUID or (destination in "MASTER" and 1 == self.Type):
				if direction in "request":
					if command in self.NodeRequestHandlers.keys():
						message = self.NodeRequestHandlers[command](sock, packet)
						if message == "":
							return
						packet  = self.BasicProtocol.AppendMagic(message)
						sock.send(packet)
					else:
						# This command belongs to the application level
						if self.OnApplicationRequestCallback is not None:
							message = self.OnApplicationRequestCallback(sock, packet)
							if message == "":
								return
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
			self.LogMSG("({classname})# ERROR - Wrong configuration format\n(EXEPTION)# {error}\n{data}".format(error=str(e),data=data,classname=self.ClassName))

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
							self.LogMSG("({classname})# ERROR - Local socket recieve\n(EXEPTION)# {error}\n{data}".format(error=str(e),data=data,classname=self.ClassName))
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
									self.LogMSG("({classname})# [NodeLocalNetworkConectionListener] Data Invalid ...".format(classname=self.ClassName))
							else:
								self.NodeDisconnectHandler(sock)
								# Raise event for user
								if self.OnTerminateConnectionCallback is not None:
									self.OnTerminateConnectionCallback(sock)
								self.RemoveConnection(sock)

				for sock in exceptional:
					self.LogMSG("({classname})# [NodeLocalNetworkConectionListener] Socket Exceptional ...".format(classname=self.ClassName))
			except Exception as e:
				self.LogMSG("({classname})# ERROR - Local socket listener\n(EXEPTION)# {error}".format(error=str(e),classname=self.ClassName))

		# Clean all resorses before exit.
		self.CleanAllSockets()
		self.LogMSG("({classname})# [NodeLocalNetworkConectionListener] Exit execution thread ...".format(classname=self.ClassName))
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
					self.LogMSG("({classname})# [FindMasters] Could not connect".format(classname=self.ClassName))
			else:
				if self.OnMasterFoundCallback is not None:
					self.OnMasterFoundCallback([None, ip])
		return len(ips)

	def CleanAllSockets(self):
		for conn in self.Connections:
			self.RemoveConnection(conn.Socket)
		
		if len(self.Connections) > 0:
			self.LogMSG("({classname})# [FindMasters] Still live socket exist".format(classname=self.ClassName))
			for conn in self.Connections:
				self.RemoveConnection(conn.Socket)
	
	def LogMSG(self, msg):
		if self.Logger is None:
			print(msg)
		elif self.Logger is not None and self.DebugMode is True:
			print(msg)
			self.Logger.info(msg)
		elif self.Logger is not None and self.DebugMode is False:
			self.Logger.info(msg)

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
	
	def ServicesManager(self):
		if self.IsMaster is True:
			return
		
		if len(self.ServiceDepened) == 0:
			return
		
		if time.time() - self.ServiceSearchTS > 10:
			for depend_srv_type in self.ServiceDepened:
				for key in self.Services:
					service = self.Services[key]
					if key == depend_srv_type:
						if service["enabled"] == 0:
							self.FindNode("", "", "", depend_srv_type)
						else:
							self.ScanNetwork()
			self.ServiceSearchTS = time.time()

	def Run (self, callback):
		# Will be called each half a second.
		self.WorkingCallback = callback
		self.LocalWSManager.OnDataArrivedEvent  = self.LocalWSDataArrivedHandler
		self.LocalWSManager.OnWSDisconnected 	= self.LocalWSDisconnectedHandler
		self.ExitEvent.clear()
		self.ExitLocalServerEvent.clear()
		# Initial state is connect to Gateway.
		self.SetState("INIT")

		# Read sytem configuration
		self.LogMSG("({classname})# Load system configuration ...".format(classname=self.ClassName))
		if (self.LoadSystemConfig() is False):
			self.LogMSG("({classname})# Load system configuration ... FAILED".format(classname=self.ClassName))
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
				#TODO - Services section must be in differebt thread
				self.ServicesManager()
				self.WorkingCallback()
				# This check is for client nodes
				if (self.Type not in [1, 2]):
					if self.LocalWSManager.IsServerRunnig() is False and self.MasterSocket is None:
						self.LogMSG("({classname})# Exiting main thread ... ({0}, {1}) ...".format(self.LocalWSManager.IsServerRunnig(), self.MasterSocket, classname=self.ClassName))
						self.Exit()

			self.Ticker += 1
			time.sleep(0.5)
		
		self.LogMSG("({classname})# Exit Node ...".format(classname=self.ClassName))
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
		self.LogMSG("({classname})# Stop Node ...".format(classname=self.ClassName))
		self.IsMainNodeRunnig 		= False
		self.IsLocalSocketRunning 	= False
	
	def Pause (self):
		pass
	
	def Exit (self):
		self.Stop()
