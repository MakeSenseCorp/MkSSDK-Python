#!/usr/bin/python
import os
import sys
import thread
import threading
import socket, select

class LocalNode():
	def __init__(self, ip, port, uuid, node_type, sock):
		self.IP 	= ip
		self.Port 	= port
		self.UUID 	= uuid
		self.Socket = sock
		self.Type 	= node_type
		self.Obj 	= None

class AbstractNode():
	def __init__(self):
		self.Ticker 							= 0
		self.OnLocalServerStartedCallback 		= None
		self.LocalServerDataArrivedCallback		= None
		self.OnAceptNewConnectionCallback		= None
		# Network
		self.ServerSocket 						= None
		self.ServerAdderss						= None
		self.RecievingSockets					= []
		self.SendingSockets						= []
		self.Connections 						= []
		self.OpenSocketsCounter					= 0
		# Flags
		self.LocalSocketServerRun				= False
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

	def ChangeState(self, state)
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
		print "[Node] Append connection, port", port
		# Append to recieving data sockets.
		self.RecievingSockets.append(sock)
		# Append to list of all connections.
		self.Connections.append(LocalNode(ip, port, "", "", sock))
		self.OpenSocketsCounter = self.OpenSocketsCounter + 1

	def RemoveConnection(self, sock):
		conn = self.GetConnection(sock)
		if None is not conn:
			print "[Node] Remove connection, port", conn.Port
			self.RecievingSockets.remove(conn.Socket)
			conn.Socket.close()
			self.Connections.remove(conn)
			self.OpenSocketsCounter = self.OpenSocketsCounter - 1

	def GetConnection(self, sock):
		for conn in self.Connections:
			if conn.Socket == sock:
				return conn
		return None

	def GetNode(self, ip):
		for conn in self.Connections:
			if conn.IP == ip:
				return conn
		return None

	def TryStartListener(self):
		try:
			print "[Node Server] Start listener..."
			self.ServerSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
			self.ServerSocket.setblocking(0)

			self.ServerSocket.bind(self.ServerAdderss)
			# [socket, ip_address, port]
			self.AppendConnection(self.ServerSocket, self.ServerAdderss[0], self.ServerAdderss[1])

			self.ServerSocket.listen(32)
			self.LocalSocketServerRun = True
			return True
		except:
			self.ServerSocket.close()
			print "[Server Node] Bind socket ERROR"
			return False

	def HandlerRouter(self, sock, data):
		pass

	def DataSocketInputHandler(self, sock, data):
		#try:
		jsonData 	= json.loads(data)
		command 	= jsonData['command']
		direction 	= jsonData['direction']

		if command in ["get_node_info", "get_node_status"]:
			self.ServerNodeHandlers[command](data)
		else:
			# Call for handler.
			self.HandlerRouter(sock, data)
		#except:
		#	print "[Node Server] HandleMKSNodeRequest ERROR", sys.exc_info()[0]

		

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

		print "[Node Server] Server is running..."
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
					print "[Node Server] Accept", addr
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
							print "[Node Socket] DATA"
							if "MKS" in data[:3]:
								multiData = data.split("MKS: ")
								for data in multiData[1:]:
									req = (data.split('\n'))[1]
									self.DataSocketInputHandler(sock, req)
							else:
								print "[Node Server] Data Invalid"
						else:
							#try:
							# If disconnected socket is master, slave need to find 
							# a master again and send request for port.
							self.NodeDisconnectHandler(sock)
							self.RemoveConnection(sock)
							# Raise event for user
							if self.OnTerminateConnectionCallback is not None:
								self.OnTerminateConnectionCallback(sock)
							#except:
							#	print "[Node Server] Connection Close [ERROR]", sys.exc_info()[0]

			for sock in exceptional:
				print "[DEBUG] Socket Exceptional"

		# Clean all resorses before exit.
		self.CleanAllSockets()

		print "[Node] Open sockets count...", self.OpenSocketsCounter
		print "[Node] Connections dictonary items count...", len(self.Connections)
		print "[DEBUG::Node] Exit local socket server"
		self.ExitLocalServerEvent.set()

	def FindMasters(self):
		# Find all master nodes on the network.
		ips = MkSUtils.FindLocalMasterNodes()
		for ip in ips:
			if self.GetNode(ip) is None:
				print "[Node] Found new master", ip
				# Master not in list, can make connection
				sock, status = self.ConnectNodeSocket((ip, 16999))
				if True == status:
					self.AppendConnection(sock, ip, 16999)
					# Raise event
					if self.OnMasterFoundCallback is not None:
						self.OnMasterFoundCallback([sock, ip])
					self.NodeMasterAvailable(sock)
				else:
					print "[Node Server] Could not connect"
		return len(ips)

	def CleanAllSockets(self):
		for conn in self.Connections:
			self.RemoveConnection(conn.Socket)
		
		if len(self.Connections) > 0:
			print "Still live socket exist"
			for conn in self.Connections:
				self.RemoveConnection(conn.Socket)

	

