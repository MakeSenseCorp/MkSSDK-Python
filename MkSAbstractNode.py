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
		self.Obj 		= None

class AbstractNode():
	def __init__(self):
		self.Ticker 							= 0
		self.UUID 								= ""
		self.Type 								= 0
		# Callbacks
		self.OnLocalServerStartedCallback 			= None
		self.LocalServerDataArrivedCallback			= None
		self.OnAceptNewConnectionCallback			= None
		self.OnMasterFoundCallback					= None
		self.OnMasterSearchCallback					= None
		self.OnMasterDisconnectedCallback			= None
		self.OnTerminateConnectionCallback 			= None
		self.OnLocalServerListenerStartedCallback	= None
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
		self.ServerNodeHandlers					= {
			'get_node_info': 					self.GetNodeInfoHandler,
			'get_node_status': 					self.GetNodeStatusHandler
		}	
		
	def GetNodeInfoHandler(self, data):
		pass
	
	def GetNodeStatusHandler(self, data):
		pass

	def SetSates (self, states):
		self.States = states

	def ChangeState(self, state):
		self.CurrentState = state

	def Start(self):
		pass

	def Stop(self):
		pass

	def TickState(self):
		self.Ticker += 1;
		# State machine
		self.SlaveMethod = self.States[self.CurrentState]
		self.SlaveMethod()

	def AppendConnection(self, sock, ip, port):
		# print "[Node] Append connection, port", port
		# Append to recieving data sockets.
		self.RecievingSockets.append(sock)
		# Append to list of all connections.
		node = LocalNode(ip, port, "", "", sock)
		self.Connections.append(node)
		self.OpenSocketsCounter = self.OpenSocketsCounter + 1
		return node

	def RemoveConnection(self, sock):
		conn = self.GetConnection(sock)
		if None is not conn:
			# print "[Node] Remove connection, port", conn.Port
			self.RecievingSockets.remove(conn.Socket)
			conn.Socket.close()
			self.Connections.remove(conn)
			self.OpenSocketsCounter = self.OpenSocketsCounter - 1

	def GetConnection(self, sock):
		for conn in self.Connections:
			if conn.Socket == sock:
				return conn
		return None

	def GetNode(self, ip, port):
		for conn in self.Connections:
			if conn.IP == ip and conn.Port == port:
				return conn
		return None

	def TryStartListener(self):
		try:
			# print "[Node Server] Start listener..."
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

	def DataSocketInputHandler(self, sock, data):
		#try:
		jsonData 	= json.loads(data)
		command 	= jsonData['command']

		if command in ["get_node_info", "get_node_status"]:
			self.ServerNodeHandlers[command](data)
		else:
			# Call for handler.
			self.HandlerRouter(sock, data)
		#except:
		#	print "[Node Server] HandleMKSNodeRequest ERROR", sys.exc_info()[0]

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
		if True == self.IsListenerEnabled:
			while False == self.LocalSocketServerRun:
				self.TryStartListener()
		else:
			self.LocalSocketServerRun = True

		# print "[Node Server] Local network is started..."
		# Raise event for user
		if self.OnLocalServerStartedCallback is not None:
			self.OnLocalServerStartedCallback()

		while True == self.LocalSocketServerRun:
			readable, writable, exceptional = select.select(self.RecievingSockets, self.SendingSockets, self.RecievingSockets, 0.5)
			
			self.TickState()

			# Socket management.
			for sock in readable:
				if sock is self.ServerSocket and True == self.IsListenerEnabled:
					conn, addr = sock.accept()
					#print "[Node Server] Accept", addr
					conn.setblocking(0)
					self.AppendConnection(conn, addr[0], addr[1])
					self.NodeConnectHandler(conn, addr)
					# Raise event for user
					if self.OnAceptNewConnectionCallback is not None:
						self.OnAceptNewConnectionCallback(conn)
				else:
					try:
						data = sock.recv(1024)
					except:
						print "[Node Server] Recieve ERROR"
					else:
						if data:
							# print "[Node Socket] DATA"
							if "MKS" in data[:3]:
								multiData = data.split("MKS: ")
								for data in multiData[1:]:
									req = (data.split('\n'))[1]
									self.DataSocketInputHandler(sock, req)
							else:
								print "[Node Server] Data Invalid"
						else:
							#try:
							self.NodeDisconnectHandler(sock)
							# Raise event for user
							if self.OnTerminateConnectionCallback is not None:
								self.OnTerminateConnectionCallback(sock)
							self.RemoveConnection(sock)
							#except:
							#	print "[Node Server] Connection Close [ERROR]", sys.exc_info()[0]

			for sock in exceptional:
				print "[DEBUG] Socket Exceptional"

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
