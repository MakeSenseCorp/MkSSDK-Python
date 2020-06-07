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
        self.Logger						= None
        # Events
        self.NewSocketEvent             = None	# Disabled
        self.CloseSocketEvent           = None	# Disabled
        self.DataArrivedEvent           = None	# Enabled
        self.NewConnectionEvent			= None	# Enabled
        self.ConnectionRemovedEvent		= None	# Enabled
        self.ServerStartetedEvent		= None 	# Enabled
        self.ServerStopedEvent			= None	# Enabled
        self.ExitSynchronizer			= None
		# Members
        self.ServerStarted				= False
        self.MasterNodesList 			= []
		# Network
        self.ServerSocket 				= None # Local server listener
        self.ServerAdderss				= None # Local server listener
        self.ListenerPort				= 0
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
		self.LogMSG("({classname})# [SockNewConnection_RXHandlerMethod]".format(classname=self.ClassName))
		conn = data["conn"]
		addr = data["addr"]
		self.AppendConnection(conn, addr[0], addr[1])

    ''' 
		Description: 	
		Return: 		
	'''  		
    def SockDataArrived_RXHandlerMethod(self, data):
		self.LogMSG("({classname})# [SockDataArrived_RXHandlerMethod]".format(classname=self.ClassName))
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
			self.LogMSG("({classname})# [DataArrivedEvent] ERROR {0}".format(e,classname=self.ClassName))

    ''' 
		Description: 	
		Return: 		
	'''  	
    def SockDisconnected_RXHandlerMethod(self, sock):
		self.LogMSG("({classname})# [SockDisconnected_RXHandlerMethod]".format(classname=self.ClassName))
		self.RemoveConnectionBySock(sock)

    ''' 
		Description: 	
		Return: 		
	'''    
    def SocketTXCallback(self, item):
		try:
			self.LogMSG("({classname})# [SocketTXCallback]".format(classname=self.ClassName))
			item["sock"].send(item["packet"])
		except Exception as e:
			self.LogMSG("({classname})# ERROR - [SocketTXCallback]\n\n********** EXCEPTION **********\n----\nITEM\n----\n{0}\n-----\nERROR\n-----\n({error})\n********************************\n".format(
				item["packet"],
				classname=self.ClassName,
				error=str(e)))

    ''' 
		Description: 	
		Return: 		
	'''  	
    def SocketRXCallback(self, item):
		try:
			self.LogMSG("({classname})# [SocketRXCallback]".format(classname=self.ClassName))
			self.RXHandlerMethod[item["type"]](item["data"])
		except Exception as e:
			self.LogMSG("({classname})# ERROR - [SocketRXCallback]\nPACKET#\n{0}\n(EXEPTION)# {error}".format(
				item,
				classname=self.ClassName,
				error=str(e)))

    ''' 
		Description: 	
		Return: 		
	'''     
    def StartListener(self):
		try:
			self.LogMSG("({classname})# Start listener...".format(classname=self.ClassName))
			self.ServerSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
			self.ServerSocket.setblocking(0)

			self.ServerSocket.bind(self.ServerAdderss)
			# [socket, ip_address, port]
			conn = self.AppendConnection(self.ServerSocket, self.LocalIP, self.ServerAdderss[1])

			self.ServerSocket.listen(32)
			self.LocalSocketWorkerRunning = True
		except Exception as e:
			self.RemoveConnectionBySock(self.ServerSocket)
			self.LogMSG("({classname})# Failed to open listener, {0}\n[EXCEPTION] {1}".format(str(self.ServerAdderss[1]),e,classname=self.ClassName))
			return False
		
		try:
			# Let know registered method about local server start.
			if self.ServerStartetedEvent is not None:
				self.ServerStartetedEvent(conn)
		except Exception as e:
			self.LogMSG("({classname})# [ServerStartetedEvent] ERROR {0}".format(e,classname=self.ClassName))
		
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

		while self.LocalSocketWorkerRunning is True:
			try:
				readable, writable, exceptional = select.select(self.RecievingSockets, self.SendingSockets, self.RecievingSockets, 0.5)
				# self.LogMSG("({classname})# [LocalSocketWorker] Heartbeat".format(classname=self.ClassName))
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
									self.LogMSG("({classname})# [LocalSocketWorker] Socket closed ...".format(classname=self.ClassName))
									# Remove socket from list.
									self.RecievingSockets.remove(sock)
									self.Transceiver.Receive({
										"type": "sock_disconnected",
										"data": sock
									})
						except Exception as e:
							self.LogMSG("({classname})# ERROR - Local socket recieve\n(EXEPTION)# {error}\n{data}".format(error=str(e),data=data,classname=self.ClassName))
							# Remove socket from list.
							self.RecievingSockets.remove(sock)
							self.Transceiver.Receive("sock_disconnected", sock)
						
				for sock in exceptional:
					self.LogMSG("({classname})# [LocalSocketWorker] Socket Exceptional ...".format(classname=self.ClassName))
			except Exception as e:
				self.LogMSG("({classname})# ERROR - Local socket listener\n(EXEPTION)# {error}".format(error=str(e),classname=self.ClassName))

		# Stop TX/RX Queue Workers
		self.LogMSG("({classname})# [LocalSocketWorker] Stop TX/RX Queue Workers".format(classname=self.ClassName))
		self.LocalServerTXWorkerRunning = False
		self.LocalServerRXWorkerRunning = False
		time.sleep(1)
		self.LogMSG("({classname})# [LocalSocketWorker] Clean all connection to this server".format(classname=self.ClassName))
		# Clean all resorses before exit.
		self.RemoveConnectionBySock(self.ServerSocket)
		self.CleanAllSockets()
		# Let user know about exit
		if self.ServerStopedEvent is not None:
			self.ServerStopedEvent()
		self.IsListenerEnabled = False
		self.LogMSG("({classname})# [LocalSocketWorker] Exit Local Server Thread ... ({0}/{1})".format(len(self.RecievingSockets),len(self.SendingSockets),classname=self.ClassName))
		time.sleep(0.5)
		self.ExitSynchronizer.set()

    ''' 
		Description: 	Create SocketConnection object and add to connections list.
						Each connection has its HASH (MD5).
		Return: 		Status and socket.
	'''
    def AppendConnection(self, sock, ip, port):
		self.LogMSG("({classname})# [AppendConnection]".format(classname=self.ClassName))
		# Append to recieving data sockets.
		self.RecievingSockets.append(sock)
		# Append to list of all connections.
		conn = MkSLocalSocketUtils.SocketConnection(ip, port, sock)
		hash_key = conn.GetHash()
		self.LogMSG("({classname})# [AppendConnection] {0} {1} {2}".format(ip,str(port),hash_key,classname=self.ClassName))
		self.OpenConnections[hash_key] 	= conn
		self.SockToHASHMap[sock] 		= hash_key
		
		try:
			# Raise event for user
			if self.NewConnectionEvent is not None:
				self.NewConnectionEvent(conn)
		except Exception as e:
			self.LogMSG("({classname})# [NewConnectionEvent] ERROR {0}".format(e,classname=self.ClassName))

		# Increment socket counter.
		self.OpenSocketsCounter += self.OpenSocketsCounter
		return conn
	
    ''' 
		Description: 	Remove socket connection and close socket.
		Return: 		Status.
	'''
    def RemoveConnectionByHASH(self, hash_key):
		self.LogMSG("({classname})# [RemoveConnectionByHASH]".format(classname=self.ClassName))
		if hash_key in self.OpenConnections:
			conn = self.OpenConnections[hash_key]
			if conn is None:
				return False
			try:
				# Raise event for user
				if self.ConnectionRemovedEvent is not None:
					self.ConnectionRemovedEvent(conn)
			except Exception as e:
				self.LogMSG("({classname})# [ConnectionRemovedEvent] ERROR {0}".format(e,classname=self.ClassName))
			
			self.LogMSG("({classname})# [RemoveConnectionByHASH] {0}, {1}".format(conn.IP,conn.Port,classname=self.ClassName))
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
		self.LogMSG("({classname})# [RemoveConnectionBySock]".format(classname=self.ClassName))
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
		self.LogMSG("({classname})# [ConnectSocket]".format(classname=self.ClassName))
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
		self.LogMSG("({classname})# [Connect]".format(classname=self.ClassName))
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
		self.LogMSG("({classname})# [SendData] {0} {1}".format(ip,port,classname=self.ClassName))
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
		self.LogMSG("({classname})# [Disconnect]".format(classname=self.ClassName))
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
			self.LogMSG("({classname})# [Disconnect] Failed to disconnect".format(classname=self.ClassName))
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
		self.LogMSG("({classname})# [CleanAllSockets]".format(classname=self.ClassName))
		try:
			while len(self.OpenConnections) > 0:
				conn = self.OpenConnections.values()[0]
				self.LogMSG("({classname})# [CleanAllSockets] {0}, {1}, {2}, {3}".format(len(self.OpenConnections),conn.HASH,conn.IP,conn.Port,classname=self.ClassName))
				status = self.Disconnect(conn.IP, conn.Port)
				if status is False:
					del self.OpenConnections.values()[0]
		except Exception as e:
			self.LogMSG("({classname})# [CleanAllSockets] ERROR {0}".format(e,classname=self.ClassName))

		self.LogMSG("({classname})# [CleanAllSockets] All sockets where released ({0})".format(len(self.OpenConnections),classname=self.ClassName))

    ''' 
		Description: 	<N/A>
		Return: 		<N/A>
	''' 
    def LogMSG(self, message):
		if self.Logger is not None:
			self.Logger.Log(message)
		else:
			print("({classname})# [NONE LOGGER] - {0}".format(message,classname=self.ClassName))

    ''' 
		Description: 	<N/A>
		Return: 		<N/A>
	''' 
    def GetListenerStatus(self):
		return self.LocalSocketWorkerRunning

    ''' 
		Description: 	<N/A>
		Return: 		<N/A>
	''' 
    def GetListenerPort(self):
		return self.ListenerPort
	
    ''' 
		Description: 	<N/A>
		Return: 		<N/A>
	''' 
    def GetListenerSocket(self):
		return self.ServerSocket

    ''' 
		Description: 	<N/A>
		Return: 		<N/A>
	''' 
    def SetExitSync(self, sync):
		self.ExitSynchronizer = sync
	
    def EnableListener(self, port):
		self.ListenerPort 		= port
		self.IsListenerEnabled 	= True
		self.ServerAdderss = ('', port)

    ''' 
		Description: 	Start worker thread of server.
		Return: 		None.
	'''	
    def Start(self):
		if self.ServerStarted is False:
			self.ServerStarted = True
			thread.start_new_thread(self.LocalSocketWorker, ())

    ''' 
		Description: 	Stop worker threa of server.
		Return: 		None.
	''' 
    def Stop(self):
        self.LocalSocketWorkerRunning 	= False
        self.ServerStarted 				= False