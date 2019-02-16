#!/usr/bin/python
import os
import sys
import json
import thread
import threading
import socket, select

from mksdk import MkSUtils

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

class AbstractNode():
	def __init__(self):
		self.Ticker 							= 0
		self.UUID 								= ""
		self.Type 								= 0
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
		self.OnNewNodeCallback						= None
		self.OnSlaveNodeDisconnectedCallback		= None
		self.OnSlaveResponseCallback				= None
		# Network
		self.ServerSocket 						= None
		self.ServerAdderss						= None
		self.RecievingSockets					= []
		self.SendingSockets						= []
		self.Connections 						= []
		self.OpenSocketsCounter					= 0
		# Flags
		self.LocalSocketServerRun				= False
		self.IsListenerEnabled 					= False
		# State machine
		self.States 							= None
		self.CurrentState						= ''
		# Locks and Events
		self.ExitLocalServerEvent				= threading.Event()
		# Initialization methods
		self.MyLocalIP 							= MkSUtils.GetLocalIP()
		# Handlers
		self.ServerNodeRequestHandlers			= {
			'get_node_info': 					self.GetNodeInfoRequestHandler,
			'get_node_status': 					self.GetNodeStatusRequestHandler
		}
		self.ServerNodeResponseHandlers			= {
			'get_node_info': 					self.GetNodeInfoResponseHandler,
			'get_node_status': 					self.GetNodeStatusResponseHandler
		}

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

	def SetSates (self, states):
		self.States = states

	def ChangeState(self, state):
		self.CurrentState = state

	# Overload
	def Start(self):
		pass

	# Overload
	def Stop(self):
		pass

	def TickState(self):
		self.Ticker += 1;
		# State machine
		method = self.States[self.CurrentState]
		method()

	def AppendConnection(self, sock, ip, port):
		# print "[Node] Append connection, port", port
		# Append to recieving data sockets.
		self.RecievingSockets.append(sock)
		# Append to list of all connections.
		node = LocalNode(ip, port, "", "", sock)
		self.Connections.append(node)
		self.OpenSocketsCounter += self.OpenSocketsCounter
		return node

	def RemoveConnection(self, sock):
		conn = self.GetConnection(sock)
		if None is not conn:
			# print "[Node] Remove connection, port", conn.Port
			self.RecievingSockets.remove(conn.Socket)
			conn.Socket.close()
			self.Connections.remove(conn)
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
			print "[Node Server] Start listener..."
			self.ServerSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
			self.ServerSocket.setblocking(0)

			self.ServerSocket.bind(self.ServerAdderss)
			# [socket, ip_address, port]
			node = self.AppendConnection(self.ServerSocket, self.ServerAdderss[0], self.ServerAdderss[1])
			node.LocalType 	= "LISTENER"
			node.UUID 		= self.UUID
			node.Type 		= self.Type

			self.ServerSocket.listen(32)
			self.LocalSocketServerRun = True

			if self.OnLocalServerListenerStartedCallback is not None:
				self.OnLocalServerListenerStartedCallback(self.ServerSocket, self.MyLocalIP, self.ServerAdderss[1])

			return True
		except:
			self.RemoveConnection(self.ServerSocket)
			print "[Server Node] Bind socket ERROR on TryStartListener", str(self.ServerAdderss[1])
			return False

	def DataSocketInputHandler_Response(self, sock, json_data):
		print "[AbstractNode] DataSocketInputHandler_Response"
		command = json_data['command']
		if command in self.ServerNodeResponseHandlers:
			self.ServerNodeResponseHandlers[command](sock, json_data)

	def DataSocketInputHandler_Resquest(self, sock, json_data):
		print "[AbstractNode] DataSocketInputHandler_Resquest"
		command = json_data['command']
		if command in self.ServerNodeRequestHandlers:
			self.ServerNodeRequestHandlers[command](sock, json_data)

	def DataSocketInputHandler(self, sock, data):
		try:
			jsonData 	= json.loads(data)
			command 	= jsonData['command']
			direction 	= jsonData['direction']

			if command in ["get_node_info", "get_node_status"]:
				print "[AbstractNode] ['get_node_info', 'get_node_status']"
				if direction in ["response", "proxy_response"]:
					self.DataSocketInputHandler_Response(sock, jsonData)
				elif direction in ["request", "proxy_request"]:
					self.DataSocketInputHandler_Resquest(sock, jsonData)
			else:
				print "[AbstractNode] HandlerRouter"
				# Call for handler.
				self.HandlerRouter(sock, data)
		except:
			print "[AbstractNode] DataSocketInputHandler ERROR", sys.exc_info()[0]

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

	def ConnectNodeSocket(self, ip_addr_port):
		sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		sock.settimeout(5)
		try:
			# print "[Node] Connecting to", ip_addr_port
			sock.connect(ip_addr_port)
			return sock, True
		except:
			print "Could not connect server", ip_addr_port
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

		# print "[Node Server] Local network is started..."
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
							data = sock.recv(2048)
							dataLen = len(data)
							while dataLen == 2048:
								chunk = sock.recv(2048)
								data += chunk
								dataLen = len(chunk)
						except:
							print "[Node Server] Recieve ERROR"
						else:
							if data:
								# Each makesense packet should start from magic number "MKS"
								if "MKS" in data[:3]:
									# One packet can hold multiple MKS messages.
									multiData = data.split("MKS: ")
									for data in multiData[1:]:
										req = (data.split('\n'))[1]
										self.DataSocketInputHandler(sock, req)
								else:
									print "[Node Server] Data Invalid"
							else:
								self.NodeDisconnectHandler(sock)
								# Raise event for user
								if self.OnTerminateConnectionCallback is not None:
									self.OnTerminateConnectionCallback(sock)
								self.RemoveConnection(sock)

				for sock in exceptional:
					print "[DEBUG] Socket Exceptional"
			except:
				print "[Node Server] Connection Close [ERROR]", sys.exc_info()[0]

		# Clean all resorses before exit.
		self.CleanAllSockets()

		#print "[Node] Open sockets count...", self.OpenSocketsCounter
		#print "[Node] Connections dictonary items count...", len(self.Connections)
		#print "[DEBUG::Node] Exit local socket server"
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
				# print "[Node] Found new master", ip
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
					print "[Node Server] Could not connect"
			else:
				if self.OnMasterFoundCallback is not None:
					self.OnMasterFoundCallback([None, ip])
		return len(ips)

	def CleanAllSockets(self):
		for conn in self.Connections:
			self.RemoveConnection(conn.Socket)
		
		if len(self.Connections) > 0:
			print "Still live socket exist"
			for conn in self.Connections:
				self.RemoveConnection(conn.Socket)

	def GetConnections(self):
		return self.Connections;

	def SetNodeUUID(self, uuid):
		self.UUID = uuid

	def SetNodeType(self, node_type):
		self.Type = node_type

	# Overload
	def ExitRoutine(self):
		pass