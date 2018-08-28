#!/usr/bin/python
import os
import sys
import thread
import threading
import time
import json
import signal
import socket, select
import Queue

from mksdk import MkSFile
from mksdk import MkSNetMachine
from mksdk import MkSDevice
from mksdk import MkSUtils

class Node():
	"""Node respomsable for coordinate between web services
	and adaptor (in most cases serial)"""
	   
	def __init__(self, node_type):
		# Objects node depend on
		self.File 							= MkSFile.File()
		self.Device 						= None
		self.Network						= None
		# Node connection to WS information
		self.ApiUrl 						= ""
		self.WsUrl							= ""
		self.UserName 						= ""
		self.Password 						= ""
		self.NodeType 						= node_type
		# Device information
		self.Type 							= 0
		self.UUID 							= ""
		self.IsHardwareBased 				= False
		self.OSType 						= ""
		self.OSVersion 						= ""
		self.BrandName 						= ""
		self.Name 							= ""
		self.Description					= ""
		self.DeviceInfo 					= None
		# Misc
		self.State 							= 'IDLE'
		self.IsRunnig 						= True
		self.AccessTick 					= 0
		self.RegisteredNodes  				= []
		self.SystemLoaded					= False
		self.IsNodeMainEnabled  			= False
		self.IsNodeLocalServerEnabled 		= False
		self.IsMasterNode					= False
		# Inner state
		self.States = {
			'IDLE': 						self.StateIdle,
			'CONNECT_DEVICE':				self.StateConnectDevice,
			'ACCESS': 						self.StateGetAccess,
			'WORK': 						self.StateWork
		}
		# Callbacks
		self.WorkingCallback 				= None
		self.OnWSDataArrived 				= None
		self.OnWSConnected 					= None
		self.OnWSConnectionClosed 			= None
		self.OnNodeSystemLoaded 			= None
		# Locks and Events
		self.NetworkAccessTickLock 			= threading.Lock()
		self.DeviceLock			 			= threading.Lock()
		self.ExitEvent 						= threading.Event()
		self.ExitLocalServerEvent			= threading.Event()
		# Debug
		self.DebugMode						= False
		# Handlers
		self.Handlers						= {
			'get_node_info': 				self.GetNodeInfoHandler,
			'get_node_status': 				self.GetNodeStatusHandler,
			'register_subscriber':			self.RegisterSubscriberHandler,
			'unregister_subscriber':		self.UnregisterSubscriberHandler 
		}
		# Node sockets
		self.Connections 					= {}
		self.MasterNodeServer				= ('', 16999)
		self.LocalSocketServer				= ('', 10000)
		self.LocalSocketServerRun			= False
		self.RecievingSockets				= []
		self.SendingSockets					= []
		self.MasterNodesList				= []
		# Master Section
		self.MasterVersion					= "1.0.1"
		self.PackagesList					= ["Gateway","LinuxTerminal","USBManager"] # Default Master capabilities.
		self.PortsForClients				= [1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32]
		# Master Node Request Handlers
		self.Handlers						= {
			'get_port': 					self.GetPort_MasterHandler,
			'get_local_nodes': 				self.GetLocalNodes_MasterHandler,
			'get_master_info':				self.GetMasterInfo_MasterHandler
		}

	def GetPort_MasterHandler(self, sock):
		port =self.PortsForClients.pop()
		print "GetPort_MasterHandler"

	def GetLocalNodes_MasterHandler(self):
		print "GetLocalNodes_MasterHandler"

	def GetMasterInfo_MasterHandler(self):
		print "GetMasterInfo_MasterHandler"

	def SocketClientHandler(self, uuid):
		print uuid

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
		server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		server.setblocking(0)

		if True == self.IsMasterNode:
			server.bind(self.MasterNodeServer)
		else:
			server.bind(self.LocalSocketServer)
		server.listen(5)

		self.RecievingSockets.append(server)

		self.IsNodeLocalServerEnabled 	= True
		self.LocalSocketServerRun 		= True
		while True == self.LocalSocketServerRun:
			readable, writable, exceptional = select.select(self.RecievingSockets, self.SendingSockets, self.RecievingSockets, 0.5)

			for sock in readable:
				if sock is server:
					conn, clientAddr = sock.accept()
					print "[Node Server] Accept new connection", clientAddr
					conn.setblocking(0)
					self.RecievingSockets.append(conn)
					self.SendingSockets.append(conn)
					self.Connections[conn] = [clientAddr, Queue.Queue(), conn]
				else:
					print "[Node Server] Client communicate", self.Connections[sock][0]
					try:
						data = sock.recv(1024)
					except:
						print "[Node Server] Recieve ERROR"
					else:
						if data:
							print data
							# Client sending data.
							self.Connections[sock][1].put(data)
							if sock not in self.SendingSockets:
								self.SendingSockets.append(sock)

							if "MKS" in data[:3]:
								print "Makesense request"
							else:
								print "Drop"
						else:
							print "[Node Server] Closing connection"
							# Client might be disconnected.
							if sock in self.SendingSockets:
								self.SendingSockets.remove(sock)
							self.RecievingSockets.remove(sock)
							sock.close()
							del self.Connections[sock][1]

			for sock in writable:
				try:
					next_msg = self.Connections[sock][1].get_nowait()
				except Queue.Empty:
					self.SendingSockets.remove(sock)
				else:
					sock.send(next_msg)

			for sock in exceptional:
				self.RecievingSockets.remove(sock)
				if sock in self.SendingSockets:
					self.SendingSockets.remove(sock)
				sock.close()
				del self.Connections[sock]

		# data = conn.recv(128)
		# self.Connections[data] = conn
		# currThread = Thread(target=self.SocketClientHandler, args=(data,))
		# currThread.start()
		# self.ThreadList.append(currThread)

		# Clean all resorses before exit.
		self.Connections.clear()
		for sock in self.RecievingSockets:
			sock.close()
		for sock in self.SendingSockets:
			sock.close()

		print "[DEBUG::Node] Exit local socket server"
		self.ExitLocalServerEvent.set()
	
	def ScanForNodes(self):
		print "ScanForNodes"
		# Get local IP
		# Scan from 1 to 240
		# Add nodes to the list

	def GetUUIDFromIP(self, uuid):
		ip_addr = ""
		return ip_addr

	def ConnectNodeSocket(self, ip_addr, no_thread):
		sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		serverAddr = ((ip_addr, 16999))
		sock.settimeout(5)
		try:
			print "Connecting to", ip_addr
			sock.connect(serverAddr)
			self.MasterNodesList.append(sock)
			print "Connected ..."
		except:
			print "Could not connect server", ip_addr
		# Open thread to communicate only if no_thread is False.
		# If continues connection, store socket in DB.

	def CreateConnectionToNode(self, uuid):
		print "CreateConnectionToNode"
		ip_addr = self.GetUUIDFromIP(uuid)
		self.ConnectNodeSocket(ip_addr, False)

	def DeviceDisconnectedCallback(self, data):
		print "[DEBUG::Node] DeviceDisconnectedCallback"
		if True == self.IsHardwareBased:
			self.Device.Disconnect()
		self.Network.Disconnect()
		self.Stop()
		self.Run(self.WorkingCallback)

	def LoadSystemConfig(self):
		# Information about the node located here.
		jsonSystemStr = self.File.LoadStateFromFile("system.json")
		
		try:
			dataSystem 				= json.loads(jsonSystemStr)
			# Node connection to WS information
			self.ApiUrl 			= dataSystem["apiurl"]
			self.WsUrl				= dataSystem["wsurl"]
			self.UserName 			= dataSystem["username"]
			self.Password 			= dataSystem["password"]
			# Device information
			self.Type 				= dataSystem["node"]["type"]
			self.OSType 			= dataSystem["node"]["ostype"]
			self.OSVersion 			= dataSystem["node"]["osversion"]
			self.BrandName 			= dataSystem["node"]["brandname"]
			self.Name 				= dataSystem["node"]["name"]
			self.Description 		= dataSystem["node"]["description"]
			self.UserDefined		= dataSystem["user"]
			# Device UUID MUST be read from HW device.
			if "True" == dataSystem["node"]["isHW"]:
				self.IsHardwareBased = True
			else:
				self.UUID = dataSystem["node"]["uuid"]
		except:
			print "Error: [LoadSystemConfig] Wrong system.json format"
			self.Exit()
		
		self.DeviceInfo = MkSDevice.Device(self.UUID, self.Type, self.OSType, self.OSVersion, self.BrandName)
	
	def SetDevice(self, device):
		print "SetDevice"
		self.Device = device
		
	def SetNetwork(self):
		print "SetNetwork"
	
	def StateIdle (self):
		print "StateIdle"
	
	def StateConnectDevice (self):
		print "StateConnectDevice"
		if True == self.IsHardwareBased:
			if None == self.Device:
				print "Error: [Run] Device did not specified"
				self.Exit()
				return
			
			if False == self.Device.Connect(self.NodeType):
				print "Error: [Run] Could not connect device"
				self.Exit()
				return
			
			self.Device.SetDeviceDisconnectCallback(self.DeviceDisconnectedCallback)
			deviceUUID = self.Device.GetUUID()
			if len(deviceUUID) > 30:
				self.UUID = deviceUUID
				print "Device UUID: " + self.UUID
				self.Network.SetDeviceUUID(self.UUID)
			else:
				print "Error: [Run] Could not connect device"
				self.Exit()
				return

		self.State = "ACCESS"
	
	def StateGetAccess (self):
		print "[DEBUG::Node] StateGetAccess"
		# Let the state machine know that this state was entered.
		self.NetworkAccessTickLock.acquire()
		try:
			self.AccessTick = 1
		finally:
			self.NetworkAccessTickLock.release()
		payloadStr = "[]"
		if self.Network.Connect(self.UserName, self.Password, payloadStr) == True:
			print "Register Device ..."
			data, error = self.Network.RegisterDevice(self.DeviceInfo)
			if error == False:
				return
	
	def StateWork (self):
		self.WorkingCallback()
	
	def WebSocketConnectedCallback (self):
		self.State = "WORK"
		self.OnWSConnected()

	def GetNodeInfoHandler(self, message_type, source, data):
		if True == self.SystemLoaded:
			print self.UserDefined
			res_payload = "\"state\":\"response\",\"status\":\"ok\",\"ts\":" + str(time.time()) + ",\"name\":\"" + self.Name + "\",\"description\":\"" + self.Description + "\", \"user\":" + json.dumps(self.UserDefined)
			print res_payload
			self.SendMessage(message_type, source, "get_node_info", res_payload)

	def GetNodeStatusHandler(self, message_type, source, data):
		if True == self.SystemLoaded:
			res_payload = "\"state\":\"response\",\"status\":\"ok\",\"ts\":" + str(time.time()) + ",\"registered\":\"" + str(self.IsNodeRegistered(source)) + "\""
			self.SendMessage(message_type, source, "get_node_status", res_payload)
	
	def RegisterSubscriberHandler(self, message_type, source, data):
		print "RegisterSubscriberHandler"
	
	def UnregisterSubscriberHandler(self, message_type, source, data):
		print "UnregisterSubscriberHandler"
	
	def WebSocketDataArrivedCallback (self, json):
		self.State = "WORK"
		#print "[NETWORK IN] - " + str(json)
		messageType = self.Network.GetMessageTypeFromJson(json)
		source = self.Network.GetSourceFromJson(json)
		command = self.Network.GetCommandFromJson(json)
		print "[DEBUG::Node Network(In)] " + command
		if messageType == "CUSTOM":
			return;
		elif messageType == "DIRECT" or messageType == "PRIVATE" or messageType == "BROADCAST" or messageType == "WEBFACE":
			data = self.Network.GetDataFromJson(json)
			# If commands located in the list below, do not forward this message and handle it in this context.
			if command in ["get_node_info", "get_node_status"]:
				self.Handlers[command](messageType, source, data)
			else:
				self.OnWSDataArrived(messageType, source, data)
		else:
			print "Error: Not support " + request + " request type."

	def IsNodeRegistered(self, subscriber_uuid):
		return subscriber_uuid in self.RegisteredNodes
	
	def SendMessage (self, message_type, destination, command, payload):
		message = self.Network.BuildMessage(message_type, destination, command, payload)
		print "[DEBUG::Node Network(Out)] " + command
		ret = self.Network.SendMessage(message)
		if False == ret:
			self.State = "ACCESS"
		return ret

	def WebSocketConnectionClosedCallback (self):
		self.OnWSConnectionClosed()
		self.NetworkAccessTickLock.acquire()
		try:
			self.AccessTick = 0
		finally:
			self.NetworkAccessTickLock.release()
		self.State = "ACCESS"

	def WebSocketErrorCallback (self):
		print "WebSocketErrorCallback"
		# TODO - Send callback "OnWSError"
		self.NetworkAccessTickLock.acquire()
		try:
			self.AccessTick = 0
		finally:
			self.NetworkAccessTickLock.release()
		self.State = "ACCESS"

	def GetFileContent (self, file):
		return self.File.LoadStateFromFile(file)

	def SetFileContent (self, file, content):
		self.File.SaveStateToFile(file, content)

	def AppendToFile (self, file, data):
		self.File.AppendToFile(file, data + "\n")

	def SaveBasicSensorValueToFile (self, uuid, value):
		self.AppendToFile(uuid + ".json", "{\"ts\":" + str(time.time()) + ",\"v\":" + str(value) + "},")
	
	def LoadBasicSensorValuesFromFileByRowNumber (self, uuid, rows_number):
		buf_size = 8192
		data_set = "["
		data_set_index = 0
		with open(uuid + ".json") as fh:
			segment = None
			offset = 0
			fh.seek(0, os.SEEK_END)
			file_size = remaining_size = fh.tell()
			while remaining_size > 0:
				offset = min(file_size, offset + buf_size)
				fh.seek(file_size - offset)
				buffer = fh.read(min(remaining_size, buf_size))
				remaining_size -= buf_size
				lines = buffer.split('\n')
				if segment is not None:
					if buffer[-1] is not '\n':
						lines[-1] += segment
					else:
						print "1" + segment
				segment = lines[0]
				for index in range(len(lines) - 1, 0, -1):
					if len(lines[index]):
						data_set_index += 1
						data_set += lines[index]
						if data_set_index == rows_number:
							data_set = data_set[:-1] + "]"
							return data_set
			if segment is not None:
				data_set += segment
		data_set = data_set[:-1] + "]"
		return data_set

	def GetDeviceConfig (self):
		jsonConfigStr = self.File.LoadStateFromFile("config.json")
		try:
			dataConfig = json.loads(jsonConfigStr)
			return dataConfig
		except:
			print "Error: [GetDeviceConfig] Wrong config.json format"
			return ""
	
	def GetSensorHWValue (self, id):
		"""Get HW device sensor value"""
		self.DeviceLock.acquire()
		error, device_id, value = self.Device.GetSensor(id)
		if error == True:
			error, device_id, value = self.Device.GetSensor(id)
			if error == True:
				self.DeviceLock.release()
				return True, 0, 0
		self.DeviceLock.release()
		return False, device_id, value

	def SetSensorHWValue (self, id, value):
		"""Set HW device with sensor value"""
		self.DeviceLock.acquire()
		data = self.Device.SetSensor(id, value)
		self.DeviceLock.release()
		return data

	def NodeWorker (self, callback):
		# Read sytem configuration
		self.LoadSystemConfig()
		self.WorkingCallback = callback
		self.State = "CONNECT_DEVICE"
		
		self.Network = MkSNetMachine.Network(self.ApiUrl, self.WsUrl)
		self.Network.SetDeviceType(self.Type)
		self.Network.SetDeviceUUID(self.UUID)
		self.Network.OnConnectionCallback  		= self.WebSocketConnectedCallback
		self.Network.OnDataArrivedCallback 		= self.WebSocketDataArrivedCallback
		self.Network.OnConnectionClosedCallback = self.WebSocketConnectionClosedCallback
		self.Network.OnErrorCallback 			= self.WebSocketErrorCallback

		self.SystemLoaded = True # Update node that system done loading.
		self.OnNodeSystemLoaded()
		
		# We need to know if this worker is running for waiting mechanizm
		self.IsNodeMainEnabled = True
		while self.IsRunnig:
			time.sleep(0.5)
			# If state is accessing network and it ia only the first time.
			if self.State == "ACCESS" and self.AccessTick > 0:
				self.NetworkAccessTickLock.acquire()
				try:
					self.AccessTick = self.AccessTick + 1
				finally:
					self.NetworkAccessTickLock.release()
				if self.AccessTick < 10:
					print "Waiting for web service ... " + str(self.AccessTick)
					continue
			
			self.Method = self.States[self.State]
			self.Method()
		
		print "[DEBUG::Node] Exit NodeWork"
		if True == self.IsHardwareBased:
			self.Device.Disconnect()
		self.ExitEvent.set()

	def SetLocalServerStatus(self, is_enabled):
		self.IsNodeLocalServerEnabled = is_enabled

	def SetConnectivityStatus(self, is_enabled):
		self.IsNodeMainEnabled = is_enabled

	def SetMasterNodeStatus(self, is_enabled):
		self.IsMasterNode = is_enabled

	def Run (self, callback):
		self.ExitEvent.clear()
		self.ExitLocalServerEvent.clear()
		
		if False == self.IsMasterNode:
			# Find all master nodes on the network.
			# Find local master and get port port number.
			self.ConnectNodeSocket("10.0.0.7", True)
			for master in self.MasterNodesList:
				master.send("MKS: Data\nHello\n")
		#	masterList = MkSUtils.FindLocalMasterNodes()

		if True == self.IsNodeMainEnabled:
			thread.start_new_thread(self.NodeWorker, (callback, ))
		if True == self.IsNodeLocalServerEnabled:
			thread.start_new_thread(self.NodeLocalNetworkConectionListener, ())

		# Waiting here till SIGNAL from OS will come.
		while self.IsRunnig:
			time.sleep(0.5)
		
		if True == self.IsNodeMainEnabled:
			self.ExitEvent.wait()

		if True == self.IsNodeLocalServerEnabled:
			self.ExitLocalServerEvent.wait()
	
	def Stop (self):
		print "[DEBUG::Node] Stop"
		self.IsRunnig 				= False
		self.LocalSocketServerRun 	= False
	
	def Pause (self):
		print "Pause"
	
	def Exit (self):
		print "Exit with ERROR"
		self.Stop()
