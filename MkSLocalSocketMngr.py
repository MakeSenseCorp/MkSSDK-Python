import os
import sys
import json
import threading
import time
import socket, select

if sys.version_info[0] < 3:
	import thread
else:
	import _thread

import MkSGlobals
from mksdk import MkSFile
from mksdk import MkSUtils
from mksdk import MkSBasicNetworkProtocol
from mksdk import MkSSecurity
from mksdk import MkSTransceiver
from mksdk import MkSLocalSocketUtils

class Manager():
    def __init__(self):
        self.ClassName                  = "MkSLocalSocket"
        self.Security                   = MkSSecurity.Security()
        self.Transceiver                = MkSTransceiver.Manager(self.SocketTXCallback, self.SocketRXCallback)
        self.BasicProtocol              = MkSBasicNetworkProtocol.BasicNetworkProtocol()
        # Events
        self.NewSocketEvent             = None	# Disabled
        self.CloseSocketEvent           = None	# Disabled
        self.DataArrivedEvent           = None	# Enabled
        self.NewConnectionEvent			= None	# Enabled
        self.ConnectionRemovedEvent		= None	# Enabled
        self.ServerStatrtedEvent		= None 	# Enabled
        self.ServerStopedEvent			= None	# Disabled
		# Members
        self.ServerStarted				= False
        self.MasterNodesList 			= []
		# Network
        self.ServerSocket 				= None # Local server listener
        self.ServerAdderss				= None # Local server listener
        self.RecievingSockets			= []
        self.SendingSockets				= []
        self.OpenSocketsCounter			= 0
        self.LocalSocketWorkerRunning	= False
        self.IsListenerEnabled 			= False
        self.OpenConnections 			= {} # Locla sockets open connections
        self.SockToHASHMap				= {}
        self.LocalIP 					= ""
        self.NetworkCards 				= MkSUtils.GetIPList()
		# RX
        self.RXHandlerMethod            = {
			"sock_new_connection": 	    self.SockNewConnection_RXHandlerMethod,
			"sock_data_arrived":	    self.SockDataArrived_RXHandlerMethod,
			"sock_disconnected":	    self.SockDisconnected_RXHandlerMethod,
		}

    ''' 
		Description: 	
		Return: 		
	'''   
    def SockNewConnection_RXHandlerMethod(self, data):
		self.Logger.Log("({classname})# [SockNewConnection_RXHandlerMethod]".format(classname=self.ClassName))
		conn = data["conn"]
		addr = data["addr"]
		self.AppendConnection(conn, addr[0], addr[1])

    ''' 
		Description: 	
		Return: 		
	'''  		
    def SockDataArrived_RXHandlerMethod(self, data):
		self.Logger.Log("({classname})# [SockDataArrived_RXHandlerMethod]".format(classname=self.ClassName))
		sock 	= data["sock"]
		packet 	= data["data"]
		conn 	= self.GetConnectionBySock(sock)
		# Update TS for monitoring
		conn.UpdateTimestamp()
		# Raise event for user
		try:
			if self.DataArrivedEvent is not None:
				self.DataArrivedEvent(conn, packet)
		except Exception as e:
			self.Logger.Log("({classname})# [DataArrivedEvent] ERROR {0}".format(e,classname=self.ClassName))

    ''' 
		Description: 	
		Return: 		
	'''  	
    def SockDisconnected_RXHandlerMethod(self, sock):
		self.Logger.Log("({classname})# [SockDisconnected_RXHandlerMethod]".format(classname=self.ClassName))
		self.RemoveConnectionBySock(sock)

    ''' 
		Description: 	
		Return: 		
	'''    
    def SocketTXCallback(self, item):
		try:
			self.Logger.Log("({classname})# [SocketTXCallback]".format(classname=self.ClassName))
			item["sock"].send(item["packet"])
		except Exception as e:
			self.Logger.Log("({classname})# ERROR - [SocketTXCallback]\nPACKET#\n{0}\n(EXEPTION)# {error}".format(
				item["packet"],
				classname=self.ClassName,
				error=str(e)))

    ''' 
		Description: 	
		Return: 		
	'''  	
    def SocketRXCallback(self, item):
		try:
			self.Logger.Log("({classname})# [SocketRXCallback]".format(classname=self.ClassName))
			self.RXHandlerMethod[item["type"]](item["data"])
		except Exception as e:
			self.Logger.Log("({classname})# ERROR - [SocketRXCallback]\nPACKET#\n{0}\n(EXEPTION)# {error}".format(
				item,
				classname=self.ClassName,
				error=str(e)))

    ''' 
		Description: 	
		Return: 		
	'''     
    def StartListener(self):
		try:
			self.Logger.Log("({classname})# Start listener...".format(classname=self.ClassName))
			self.ServerSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
			self.ServerSocket.setblocking(0)

			self.ServerSocket.bind(self.ServerAdderss)
			# [socket, ip_address, port]
			conn = self.AppendConnection(self.ServerSocket, self.LocalIP, self.ServerAdderss[1])

			self.ServerSocket.listen(32)
			self.IsListenerEnabled 			= True
			self.LocalSocketWorkerRunning 	= True
		except Exception as e:
			self.RemoveConnectionBySock(self.ServerSocket)
			self.Logger.Log("({classname})# Failed to open listener, {0}\n[EXCEPTION] {1}".format(str(self.ServerAdderss[1]),e,classname=self.ClassName))
			return False
		
		try:
			# Let know registered method about local server start.
			if self.ServerStatrtedEvent is not None:
				self.ServerStatrtedEvent(conn)
		except Exception as e:
			self.Logger.Log("({classname})# [ServerStatrtedEvent] ERROR {0}".format(e,classname=self.ClassName))
		
		return True

    ''' 
		Description: 	
		Return: 		
	'''  
    def LocalSocketWorker(self):
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
			while self.LocalSocketWorkerRunning is False:
				self.StartListener()
		else:
			self.LocalSocketWorkerRunning = True

		# Raise event for user
		if self.OnLocalServerStartedCallback is not None:
			self.OnLocalServerStartedCallback()

		while self.LocalSocketWorkerRunning is True:
			try:
				readable, writable, exceptional = select.select(self.RecievingSockets, self.SendingSockets, self.RecievingSockets, 0.5)
				# self.Logger.Log("({classname})# [LocalSocketWorker] Heartbeat".format(classname=self.ClassName))
				# Socket management.
				for sock in readable:
					if sock is self.ServerSocket and self.IsListenerEnabled is True:
						conn, addr = sock.accept()
						#conn.setblocking(0)
						self.Transceiver.Receive({
							"type": "sock_new_connection",
							"data": {
								"conn": conn,
								"addr": addr
							}
						})
					else:
						try:
							if sock is not None:
								data = sock.recv(2048)
								dataLen = len(data)
								while dataLen == 2048:
									chunk = sock.recv(2048)
									data += chunk
									dataLen = len(chunk)
								if data:
									self.Transceiver.Receive({
										"type": "sock_data_arrived", 
										"data": {
											"sock": sock,
											"data": data
										}
									})
								else:
									self.Logger.Log("({classname})# [LocalSocketWorker] Socket closed ...".format(classname=self.ClassName))
									# Remove socket from list.
									self.RecievingSockets.remove(sock)
									self.Transceiver.Receive({
										"type": "sock_disconnected",
										"data": sock
									})
						except Exception as e:
							self.Logger.Log("({classname})# ERROR - Local socket recieve\n(EXEPTION)# {error}\n{data}".format(error=str(e),data=data,classname=self.ClassName))
							# Remove socket from list.
							self.RecievingSockets.remove(sock)
							self.Transceiver.Receive("sock_disconnected", sock)
						
				for sock in exceptional:
					self.Logger.Log("({classname})# [LocalSocketWorker] Socket Exceptional ...".format(classname=self.ClassName))
			except Exception as e:
				self.Logger.Log("({classname})# ERROR - Local socket listener\n(EXEPTION)# {error}".format(error=str(e),classname=self.ClassName))

		# Stop TX/RX Queue Workers
		self.Logger.Log("({classname})# [LocalSocketWorker] Stop TX/RX Queue Workers".format(classname=self.ClassName))
		self.LocalServerTXWorkerRunning = False
		self.LocalServerRXWorkerRunning = False
		time.sleep(1)
		self.Logger.Log("({classname})# [LocalSocketWorker] Clean all connection to this server".format(classname=self.ClassName))
		# Clean all resorses before exit.
		self.RemoveConnectionBySock(self.ServerSocket)
		self.CleanAllSockets()
		self.LocalServerTerminated()
		self.IsListenerEnabled = False
		self.Logger.Log("({classname})# [LocalSocketWorker] Exit Local Server Thread ... ({0}/{1})".format(len(self.RecievingSockets),len(self.SendingSockets),classname=self.ClassName))
		self.ExitLocalServerEvent.set()

    ''' 
		Description: 	Create SocketConnection object and add to connections list.
						Each connection has its HASH (MD5).
		Return: 		Status and socket.
	'''
    def AppendConnection(self, sock, ip, port):
		self.Logger.Log("({classname})# [AppendConnection]".format(classname=self.ClassName))
		# Append to recieving data sockets.
		self.RecievingSockets.append(sock)
		# Append to list of all connections.
		conn = MkSLocalSocketUtils.SocketConnection(ip, port, sock)
		hash_key = conn.GetHash()
		self.Logger.Log("({classname})# [AppendConnection] {0} {1} {2}".format(ip,str(port),hash_key,classname=self.ClassName))
		self.OpenConnections[hash_key] 	= conn
		self.SockToHASHMap[sock] 		= hash_key
		
		try:
			# Raise event for user
			if self.NewConnectionEvent is not None:
				self.NewConnectionEvent(conn)
		except Exception as e:
			self.Logger.Log("({classname})# [NewConnectionEvent] ERROR {0}".format(e,classname=self.ClassName))

		# Increment socket counter.
		self.OpenSocketsCounter += self.OpenSocketsCounter
		return conn
	
    ''' 
		Description: 	Remove socket connection and close socket.
		Return: 		Status.
	'''
    def RemoveConnectionByHASH(self, hash_key):
		self.Logger.Log("({classname})# [RemoveConnectionByHASH]".format(classname=self.ClassName))
		if hash_key in self.OpenConnections:
			conn = self.OpenConnections[hash_key]
			if conn is None:
				return False
			try:
				# Raise event for user
				if self.ConnectionRemovedEvent is not None:
					self.ConnectionRemovedEvent(conn)
			except Exception as e:
				self.Logger.Log("({classname})# [ConnectionRemovedEvent] ERROR {0}".format(e,classname=self.ClassName))
			
			self.Logger.Log("({classname})# [RemoveConnectionByHASH] {0}, {1}".format(conn.IP,conn.Port,classname=self.ClassName))
			# Remove socket from list.
			if conn.Socket in self.RecievingSockets:
				self.RecievingSockets.remove(conn.Socket)
			# Close connection.
			if conn.Socket is not None:
				del self.SockToHASHMap[conn.Socket]
				# Send close request before closing. (TODO)
				conn.Socket.close()
			# Remove SocketConnection from the list.
			del self.OpenConnections[hash_key]
			# Deduce socket counter.
			self.OpenSocketsCounter -= self.OpenSocketsCounter
			return True
		return False
	
    ''' 
		Description: 	Remove socket connection and close socket.
		Return: 		Status.
	'''
    def RemoveConnectionBySock(self, sock):
		self.Logger.Log("({classname})# [RemoveConnectionBySock]".format(classname=self.ClassName))
		if sock in self.SockToHASHMap:
			conn = self.GetConnectionBySock(sock)
			self.RemoveConnectionByHASH(conn.HASH)
	
    ''' 
		Description: 	Get local connection by sock. 
		Return: 		SocketConnection.
		GetNodeBySock
	'''
    def GetConnectionBySock(self, sock):
		if sock in self.SockToHASHMap:
			hash_key = self.SockToHASHMap[sock]
			if hash_key in self.OpenConnections:
				return self.OpenConnections[hash_key]
		return None

    ''' 
		Description: 	Get local connection by ip and port.
		Return: 		SocketConnection.
		GetNode
	'''
    def GetConnection(self, ip, port):
		hash_key = self.Security.GetMD5Hash("{0}_{1}".format(ip,str(port)))
		if hash_key in self.OpenConnections:
			return self.OpenConnections[hash_key]
		return None

    ''' 
		Description: 	Connect raw network socket.
		Return: 		Status and socket.
		ConnectNodeSocket
	'''
    def ConnectSocket(self, ip_addr_port):
		self.Logger.Log("({classname})# [ConnectSocket]".format(classname=self.ClassName))
		sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		sock.settimeout(5)
		try:
			sock.connect(ip_addr_port)
			return sock, True
		except:
			return None, False
	
    ''' 
		Description: 	Connect socket and add to connections list.
		Return: 		Status and socket.
		ConnectNode
	'''
    def Connect(self, ip, port):
		self.Logger.Log("({classname})# [Connect]".format(classname=self.ClassName))
		sock, status = self.ConnectSocket((ip, port))
		conn = None
		if True == status:
			conn = self.AppendConnection(sock, ip, port)
		return conn, status
	
    ''' 
		Description: 	Send message over socket via message queue.
		Return: 		Status.
		SendNodePacket
	'''
    def SendData(self, ip, port, packet):
		self.Logger.Log("({classname})# [SendData]".format(classname=self.ClassName))
		key = self.Security.GetMD5Hash("{0}_{1}".format(ip,str(port)))
		if key in self.OpenConnections:
			node = self.OpenConnections[key]
			if node is not None:
				self.Transceiver.Send({"sock":node.Socket, "packet":packet})
				return True
		return False

    ''' 
		Description: 	Send message over socket via message queue.
		Return: 		Status.
	'''
    def Send(self, sock, packet):
		self.Transceiver.Send({"sock":sock, "packet":packet})

    ''' 
		Description: 	Disconnect connection over socket, add clean all databases.
		Return: 		Status.
		DisconnectNode
	'''
    def Disconnect(self, ip, port):
		self.Logger.Log("({classname})# [Disconnect]".format(classname=self.ClassName))
		try:
			hash_key = self.Security.GetMD5Hash("{0}_{1}".format(ip,str(port)))
			if hash_key in self.OpenConnections:
				conn = self.OpenConnections[hash_key]
				if conn is not None:
					self.RemoveConnectionByHASH(hash_key)
					return True
					# Raise event for user
					#if self.OnTerminateConnectionCallback is not None:
					#	self.OnTerminateConnectionCallback(node.Socket)
		except:
			self.Logger.Log("({classname})# [Disconnect] Failed to disconnect".format(classname=self.ClassName))
		return False
	
    ''' 
		Description: 	Get all connected connections.
		Return: 		Connections list.
	'''
    def GetConnections(self):
		return self.OpenConnections

    ''' 
		Description: 	Delete and close all local sockets.
		Return: 		None.
	'''
    def CleanAllSockets(self):
		self.Logger.Log("({classname})# [CleanAllSockets]".format(classname=self.ClassName))
		while len(self.OpenConnections) > 0:
			conn = self.OpenConnections.values()[0]
			self.Logger.Log("({classname})# [CleanAllSockets] {0}, {1}, {2}, {3}, {4}".format(len(self.OpenConnections),conn.HASH,conn.IP,conn.Port,classname=self.ClassName))
			status = self.Disconnect(conn.IP, conn.Port)
			if status is False:
				del self.OpenConnections.values()[0]

		self.Logger.Log("({classname})# [CleanAllSockets] All sockets where released ({0})".format(len(self.OpenConnections),classname=self.ClassName))

    ''' 
		Description: 	<N/A>
		Return: 		<N/A>
	''' 
    def GetListenerStatus(self):
		return self.LocalSocketWorkerRunning

    ''' 
		Description: 	Start worker thread of server.
		Return: 		None.
	'''	
    def Start(self, port):
		if self.ServerStarted is False:
			self.ServerStarted = True
			self.ServerAdderss = ('', port)
			thread.start_new_thread(self.LocalSocketWorker, ())

    ''' 
		Description: 	Stop worker threa of server.
		Return: 		None.
	''' 
    def Stop(self):
        self.LocalSocketWorkerRunning 	= False
        self.ServerStarted 				= False