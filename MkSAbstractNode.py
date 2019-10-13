#!/usr/bin/python
import os
import sys
import json
if sys.version_info[0] < 3:
	import thread
else:
	import _thread
import threading
import socket, select

from flask import Flask, render_template, jsonify, Response, request
#from flask_cors import CORS
import logging

from mksdk import MkSUtils

class EndpointAction(object):
	def __init__(self, page, args):
		self.Page = page + ".html"
		self.DataToJS = args

	def __call__(self, *args):
		return render_template(self.Page, data=self.DataToJS)

class WebInterface():
	def __init__(self, name, port):
		self.App = Flask(name)
		self.Port = port
		#CORS(self.App)

		#self.Log = logging.getLogger('werkzeug')
		#self.Log.disabled = True
		#self.App.logger.disabled = True

	def WebInterfaceWorker_Thread(self):
		print ("[AbstractNode]# WebInterfaceWorker_Thread", self.Port)
		self.App.run(host='0.0.0.0', port=self.Port)

	def Run(self):
		thread.start_new_thread(self.WebInterfaceWorker_Thread, ())

	def AddEndpoint(self, endpoint=None, endpoint_name=None, handler=None, args=None, method=['GET']):
		if handler is None:
			self.App.add_url_rule(endpoint, endpoint_name, EndpointAction(endpoint_name, args))
		else:
			self.App.add_url_rule(endpoint, endpoint_name, handler, methods=method)

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
		self.Ticker 							= 0
		self.UUID 								= ""
		self.Type 								= 0
		# TODO - BUG FIX - Remove sel.Name and Mastr Node will print incorrect value in the table.
		self.Name 								= "N/A"
		self.GatewayIP 							= ""
		# Callbacks
		# ---------
		# Let know that local server thread is started. Does not say that network is working (server or client).
		self.OnLocalServerStartedCallback 			= None
		# TODO - What is this callback for?
		self.LocalServerDataArrivedCallback			= None 
		# Let know about nwe connection arrived.
		self.OnAceptNewConnectionCallback			= None
		self.OnMasterFoundCallback					= None
		self.OnMasterSearchCallback					= None
		self.OnMasterDisconnectedCallback			= None
		self.OnTerminateConnectionCallback 			= None
		self.OnLocalServerListenerStartedCallback	= None
		self.OnExitCallback							= None
		self.ServiceNewNodeCallback					= None
		self.OnSlaveNodeDisconnectedCallback		= None
		self.OnSlaveResponseCallback				= None
		# Network
		self.ServerSocket 							= None
		self.ServerAdderss							= None
		self.RecievingSockets						= []
		self.SendingSockets							= []
		self.Connections 							= []
		self.OpenSocketsCounter						= 0
		# Flags
		self.LocalSocketServerRun					= False
		self.IsListenerEnabled 						= False
		# State machine
		self.States 								= None
		self.CurrentState							= ''
		self.Pwd									= os.getcwd()
		# Locks and Events
		self.ExitLocalServerEvent					= threading.Event()
		# Initialization methods
		self.MyLocalIP 								= MkSUtils.GetLocalIP()
		# Handlers
		self.ServerNodeRequestHandlers				= {
			'get_node_info': 						self.GetNodeInfoRequestHandler,
			'get_node_status': 						self.GetNodeStatusRequestHandler
		}
		self.ServerNodeResponseHandlers				= {
			'get_node_info': 						self.GetNodeInfoResponseHandler,
			'get_node_status': 						self.GetNodeStatusResponseHandler
		}
		# LocalFace UI
		self.UI 									= None
		self.LocalWebPort							= ""

	# Overload
	def GatewayConnectedEvent(self):
		pass

	# Overload
	def GatewayDisConnectedEvent(self):
		pass

	# Overload - This method must be implemented by Master node 
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

	def SetState (self, states):
		self.States = states

	def ChangeState(self, state):
		self.CurrentState = state

	# Overload
	def HandlerRouter(self, sock, data):
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
	def Start(self):
		pass

	# Overload
	def Stop(self):
		pass

	def InitiateLocalServer(self, port):
		self.UI 			= WebInterface("Context", port)
		self.LocalWebPort	= port
		# Data for the pages.
		jsonUIData 	= {
			'ip': str(self.MyLocalIP),
			'port': str(port)
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
		print ("[AbstractNode]# AppendFaceRestTable")
		self.UI.AddEndpoint(endpoint, endpoint_name, handler, args, method)

	def TestWithKeyHandler(self, key):
		if "ykiveish" in key:
			return "{\"response\":\"OK\"}"
		else:
			return ""

	def GetConnectedSocketsListHandler(self, key):
		if "ykiveish" in key:
			response = "{\"response\":\"OK\",\"payload\":{\"list\":["
			for idx, item in enumerate(self.Connections):
				response += "{\"local_type\":\"" + str(item.LocalType) + "\",\"uuid\":\"" + str(item.UUID) + "\",\"ip\":\"" + str(item.IP) + "\",\"port\":" + str(item.Port) + ",\"type\":\"" + str(item.Type) + "\"},"
			response = response[:-1] + "]}}"
			return jsonify(response)
		else:
			return ""

	def TickState(self):
		self.Ticker += 1
		# State machine
		method = self.States[self.CurrentState]
		method()

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
			print ("[AbstractNode] Start listener...")
			self.ServerSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
			self.ServerSocket.setblocking(0)

			self.ServerSocket.bind(self.ServerAdderss)
			# [socket, ip_address, port]
			node = self.AppendConnection(self.ServerSocket, self.MyLocalIP, self.ServerAdderss[1])
			node.LocalType 	= "LISTENER"
			node.UUID 		= self.UUID
			node.Type 		= self.Type

			self.ServerSocket.listen(32)
			self.LocalSocketServerRun = True

			# Run preloader for UI interface
			if self.UI is None:
				print ("[AbstractNode]# Executin Webface Preloader")
				self.PreUILoaderHandler()

			# Let know registered method about local server start.
			if self.OnLocalServerListenerStartedCallback is not None:
				self.OnLocalServerListenerStartedCallback(self.ServerSocket, self.MyLocalIP, self.ServerAdderss[1])

			# Run UI thread
			if self.UI is None:
				print ("[AbstractNode]# Local server is NULL (WARNNING)")
			else:
				print ("[AbstractNode]# Running Local Webface")
				self.UI.Run()

			return True
		except Exception as e:
			self.RemoveConnection(self.ServerSocket)
			print ("[Server Node] Failed to open listener, ", str(self.ServerAdderss[1]), e)
			return False

	def DataSocketInputHandler_Response(self, sock, json_data):
		print ("[AbstractNode] DataSocketInputHandler_Response")
		command = json_data['command']
		if command in self.ServerNodeResponseHandlers:
			self.ServerNodeResponseHandlers[command](sock, json_data)

	def DataSocketInputHandler_Resquest(self, sock, json_data):
		print ("[AbstractNode] DataSocketInputHandler_Resquest")
		command = json_data['command']
		if command in self.ServerNodeRequestHandlers:
			self.ServerNodeRequestHandlers[command](sock, json_data)

	def DataSocketInputHandler(self, sock, data):
		try:
			jsonData 	= json.loads(data)
			command 	= jsonData['command']
			direction 	= jsonData['direction']

			if command in ["get_node_info", "get_node_status"]:
				print ("[AbstractNode] ['get_node_info', 'get_node_status']")
				if direction in ["response", "proxy_response"]:
					if (direction in "proxy_response"):
						self.HandlerRouter(sock, data)
					else:
						self.DataSocketInputHandler_Response(sock, jsonData)
				elif direction in ["request", "proxy_request"]:
					self.DataSocketInputHandler_Resquest(sock, jsonData)
			else:
				print ("[AbstractNode] HandlerRouter")
				# Call for handler.
				self.HandlerRouter(sock, data)
		except Exception as e:
			print ("[AbstractNode] DataSocketInputHandler ERROR", e, data)

	def ConnectNodeSocket(self, ip_addr_port):
		sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		sock.settimeout(5)
		try:
			sock.connect(ip_addr_port)
			return sock, True
		except:
			print ("[AbstractNode] Could not connect server", ip_addr_port)
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
			while self.LocalSocketServerRun is False:
				self.TryStartListener()
		else:
			self.LocalSocketServerRun = True

		# Raise event for user
		if self.OnLocalServerStartedCallback is not None:
			self.OnLocalServerStartedCallback()

		while self.LocalSocketServerRun is True:
			self.TickState()

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
								if "MKS" in data[:3]:
									# One packet can hold multiple MKS messages.
									multiData = data.split("MKS: ")
									for data in multiData[1:]:
										req = (data.split('\n'))[1]
										# TODO - Must handled in different thread
										self.DataSocketInputHandler(sock, req)
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
				print ("[AbstractNode] Connection Close [ERROR]", e)

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

	def ConnectMaster(self, ip):
		sock, status = self.ConnectNodeSocket((ip, 16999))
		if status is True:
			node = self.AppendConnection(sock, ip, 16999)
			node.LocalType = "MASTER"
		return sock, status

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
