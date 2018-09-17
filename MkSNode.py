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
from mksdk import MkSAbstractNode

class Node():
	"""Node respomsable for coordinate between web services
	and adaptor (in most cases serial)"""
	   
	def __init__(self, node_type, local_service_node):
		# Objects node depend on
		self.File 							= MkSFile.File()
		self.Device 						= None
		self.Network						= None
		self.LocalServiceNode 				= local_service_node
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
		self.IsListenerEnabled 				= False
		self.isPureSlave					= False
		self.MasterNodeLocatorRunning		= False
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
		self.LocalSocketServerRun			= False
		# Callbacks
		self.OnMasterFoundCallback			= None
		self.OnMasterDisconnectedCallback	= None
		self.OnMasterAppendNodeCallback 	= None
		self.OnMasterRemoveNodeCallback		= None
		self.OnTerminateConnectionCallback	= None

	def SocketClientHandler(self, uuid):
		print uuid

	def GetLocalConnection(self, ip, port):
		for item in self.Connections:
			if item.IP == ip and item.Port == port:
				return item
		return None

	def GetSlaveNode(self, uuid):
		for item in self.LocalSlaveList:
			if item.UUID == uuid:
				return item
		return None

	# Handler triggered by request and response
	def HandlerRouter (self, data, sock):
		#try:
			jsonData 	= json.loads(data)
			command 	= jsonData['command']
			direction 	= jsonData['direction']
			conn 		= self.GetConnection(sock)
			ip 			= conn.IP

			if "get_port" == command:
				if "request" == direction:
					uuid = jsonData['uuid']
					nodeType = jsonData['type']
					if self.PortsForClients:
						existingSlave = None
						for slave in self.LocalSlaveList:
							if slave.UUID == uuid:
								# NOTE - Should we delete the old slave?
								# 		 Also should we send to clients about new slave?
								existingSlave = slave
								continue

						if None == existingSlave:
							port = 10000 + self.PortsForClients.pop()
							# Send message to all nodes.
							for client in self.Connections:
								if client.Socket == self.ServerSocket:
									pass
								else:
									client.Socket.send("MKS: Data\n{\"command\":\"master_append_node\",\"direction\":\"request\",\"node\":{\"ip\":\"" + str(ip) + "\",\"port\":" + str(port) + ",\"uuid\":\"" + uuid + "\",\"type\":" + str(nodeType) + "}}\n")
							self.LocalSlaveList.append(LocalClient(ip, port, uuid, nodeType, sock))
							payload = "MKS: Data\n{\"command\":\"get_port\",\"direction\":\"response\",\"port\":" + str(port) + "}\n"
							sock.send(payload)
						else:
							existingSlave.Socket = sock
							payload = "MKS: Data\n{\"command\":\"get_port\",\"direction\":\"response\",\"port\":" + str(existingSlave.Port) + "}\n"
							sock.send(payload)
					else:
						sock.send("MKS: Data\n{\"command\":\"get_port\",\"direction\":\"response\",\"port\":0,\"error:\":\"NO_PORT\"}\n")
				elif "response" == direction:
					print "Execute RESPONSE handler for \"get_port\""
					self.SlaveListenerPort 		= int(jsonData['port'])
					self.LocalSocketServer 		= ('', self.SlaveListenerPort)
					self.SlaveState 			= "START_LISTENER"
			elif "get_local_nodes" == command:
				if "request" == direction:
					nodes = ""
					if self.LocalSlaveList:
						for node in self.LocalSlaveList:
							nodes = nodes + "{\"ip\":\"" + str(node.IP) + "\",\"port\":" + str(node.Port) + ",\"uuid\":\"" + node.UUID + "\",\"type\":" + str(node.Type) + "},"
						nodes = nodes[:-1]
					payload = "MKS: Data\n{\"command\":\"get_local_nodes\",\"direction\":\"response\",\"nodes\":[" + nodes + "]}\n"
					sock.send(payload)
				elif "response" == direction:
					print "Execute RESPONSE handler for \"get_local_nodes\""
			elif "get_master_info" == command:
				if "request" == direction:
					print "get_master_info"
				elif "response" == direction:
					nodes = ""
					if self.LocalSlaveList:
						for node in self.LocalSlaveList:
							nodes = nodes + "{\"ip\":\"" + str(node.IP) + "\",\"port\":" + str(node.Port) + ",\"uuid\":\"" + node.UUID + "\",\"type\":" + str(node.Type) + "},"
						nodes = nodes[:-1]
					payload = "MKS: Data\n{\"command\":\"get_master_info\",\"direction\":\"response\",\"info\":{\"hostname\":\"" + self.MasterHostName + "\",\"nodes\":[" + nodes + "]}}\n"
					sock.send(payload)
			elif "master_append_node" == command:
				info 		= jsonData['node']
				uuid 		= info['uuid']
				port 		= info['port']
				nodeType 	= info['type']
				ip 			= info['ip']

				print "[master_append_node]", ip, port
				if self.OnMasterAppendNodeCallback is not None:
					nodeStr = "{\"ip\":\"" + str(ip) + "\",\"port\":" + str(port) + ",\"uuid\":\"" + uuid + "\",\"type\":" + str(nodeType) + "}"
					self.OnMasterAppendNodeCallback(nodeStr)
			elif "master_remove_node" == command:
				info 		= jsonData['node']
				uuid 		= info['uuid']
				port 		= info['port']
				nodeType 	= info['type']
				
				if self.OnMasterRemoveNodeCallback is not None:
					nodeStr = "{\"ip\":\"" + str(ip) + "\",\"port\":" + str(port) + ",\"uuid\":\"" + uuid + "\",\"type\":" + str(nodeType) + "}"
					self.OnMasterRemoveNodeCallback(nodeStr)
			else:
				print "[Node Server] Does NOT support this command", command
		#except:
		#	print "[Node Server] HandlerRouter ERROR", sys.exc_info()[0]

	def ConnectNodeSocket(self, ip_addr_port):
		sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		sock.settimeout(5)
		try:
			print "[Node] Connecting to", ip_addr_port
			sock.connect(ip_addr_port)
			self.AppendConnection(sock, ip_addr_port[0], ip_addr_port[1])
			return sock, True
		except:
			print "Could not connect server", ip_addr_port
			return None, False

	def DisconnectNodeSocket(self, sock):
		self.RemoveConnection(sock)

	def GetMasterInfo(self, ip):
		for master in self.MasterNodesList:
			if master[1] == ip:
				payload = "MKS: Data\n{\"command\":\"get_master_info\",\"direction\":\"response\"}\n"
				master[0].send(payload)

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
		pass
	
	def WebSocketConnectedCallback (self):
		self.State = "WORK"
		self.OnWSConnected()

	def GetNodeInfoHandler(self, message_type, source, data):
		if True == self.SystemLoaded:
			# print self.UserDefined
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
		messageType = self.Network.GetMessageTypeFromJson(json)
		source = self.Network.GetSourceFromJson(json)
		command = self.Network.GetCommandFromJson(json)
		print "[DEBUG::Node Network(In)] " + str(json)
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
		print "[DEBUG::Node Network(Out)] " + message
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

	def StartMasterNodeLocator(self):
		self.MasterNodeLocatorRunning = True

	def StopMasterNodeLocator(self):
		self.MasterNodeLocatorRunning = False

	def MasterNodeLocator(self):
		self.StartMasterNodeLocator()
		while True == self.MasterNodeLocatorRunning:
			print "[Node] MasterNodeLocator WORKING"
			# Search network.
			self.FindMasters()
			# Rest for several seconds.
			time.sleep(10)

	def SetLocalServerStatus(self, is_enabled):
		self.IsNodeLocalServerEnabled = is_enabled

	def SetConnectivityStatus(self, is_enabled):
		self.IsNodeMainEnabled = is_enabled

	def SetMasterNodeStatus(self, is_enabled):
		self.IsMasterNode 		= is_enabled
		self.IsListenerEnabled 	= is_enabled

	def SetPureSlaveStatus(self, is_enabled):
		self.isPureSlave = is_enabled

	def Run (self, callback):
		self.WorkingCallback = callback
		self.ExitEvent.clear()
		self.ExitLocalServerEvent.clear()

		# Read sytem configuration
		self.LoadSystemConfig()

		if True == self.IsNodeMainEnabled:
			thread.start_new_thread(self.NodeWorker, (callback, ))
		if True == self.IsNodeLocalServerEnabled:
			thread.start_new_thread(self.NodeLocalNetworkConectionListener, ())

		thread.start_new_thread(self.MasterNodeLocator, ())

		# Waiting here till SIGNAL from OS will come.
		while self.IsRunnig:
			self.WorkingCallback()
			time.sleep(0.5)
		
		if True == self.IsNodeMainEnabled:
			self.ExitEvent.wait()

		if True == self.LocalSocketServerRun:
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
