#!/usr/bin/python
import os
import sys
import json
import thread
import socket, select
import time

class MkSStream():
	def __init__(self, name, is_server):
		self.ClassName 				= "MkSStream"
		self.Name 					= name
		self.Identity 				= 0
		self.Port 					= 0
		self.ClientPort 			= 0
		self.DataSize 				= 1024
		self.ServerSocket 			= None
		self.ClientSocket 			= None
		self.WorkerRunning 			= False
		self.IsServer 				= is_server
		self.ServerIP				= ""
		self.ClientIP 				= ""
		self.State					= "IDLE"
		# Events
		self.OnConnectedEvent 		= None
		self.OnDataArrivedEvent 	= None
		self.OnDisconnectedEvent 	= None
	
	def SetState(self, state):
		self.State = state
	
	def GetState(self):
		return self.State

	def SetPort(self, port):
		self.Port = port
	
	def GetPort(self):
		return self.Port
	
	def SetServerIP(self, ip):
		self.ServerIP = ip
	
	def ConfigureListener(self):
		try:
			self.ServerSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
			#self.ServerSocket.setblocking(0)
			self.ServerSocket.bind((self.ServerIP, self.Port))

		except Exception as e:
			return False
		return True
	
	def Worker(self):
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
		if self.IsServer is True:
			self.ConfigureListener()

		self.WorkerRunning = True
		while self.WorkerRunning is True:
			try:
				# Socket management.
				if self.IsServer is True: 
					data, addr = self.ServerSocket.recvfrom(self.DataSize)
					self.ClientPort	= addr[1]
				else:
					data, addr = self.ClientSocket.recvfrom(self.DataSize)
					
				# Emit event
				if self.OnDataArrivedEvent is not None:
					self.OnDataArrivedEvent(self.Name, self.Identity, data)
				
				time.sleep(0.5)
			except Exception as e:
				print("[Worker]", e)
	
	def Listen(self):
		if self.IsServer is True:
			thread.start_new_thread(self.Worker, ())
			self.SetState("LISTEN")

	def Connect(self):
		if self.IsServer is False:
			self.ClientSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
			thread.start_new_thread(self.Worker, ())
			self.SetState("CONNECT")

	def Disconnect(self):
		self.WorkerRunning = False
		if self.IsServer is False:
			self.ServerSocket.close()
		else:
			self.ClientSocket.close()
		self.SetState("IDLE")

	def Send(self, data):
		buffer = str.encode(data)
		if self.IsServer is False:
			self.ClientSocket.sendto(buffer, (self.ServerIP, self.Port))
		else:
			self.ServerSocket.sendto(buffer, (self.ClientIP, self.ClientPort))

class MkSStreamManager():
	def __init__(self, context):
		self.ClassName 				= "MkSStreamManager"
		self.Context 				= context
		self.Streams 				= {}
		self.PortCounter 			= 20000
	
	def CreateStream(self, identity, name, is_server):
		if identity in self.Streams:
			return
		
		stream = MkSStream(name, is_server)
		stream.Identity = identity
		if is_server is True:
			stream.Port = self.GeneratePort()
		self.Streams[identity] = stream	
		
	def UpdateStream(self, identity, stream):
		if identity in self.Streams:
			return
		self.Streams[identity] = stream	
	
	def RegisterCallbacks(self, identity, connected, data, disconnected):
		stream = self.Streams[identity]
		stream.OnConnectedEvent 	= connected
		stream.OnDataArrivedEvent 	= data
		stream.OnDisconnectedEvent 	= disconnected
		self.Streams[identity] = stream
	
	def GetStream(self, identity):
		if identity in self.Streams:
			return self.Streams[identity]
		else:
			return None
	
	def GeneratePort(self):
		self.PortCounter += 1
		return self.PortCounter