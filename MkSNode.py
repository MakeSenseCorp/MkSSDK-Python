#!/usr/bin/python
import os
import sys
import thread
import threading
import time
import json
import signal

from mksdk import MkSFile
from mksdk import MkSNetMachine
from mksdk import MkSDevice
from mksdk import MkSSensor

class Node():
	"""Node respomsable for coordinate between web services
	and adaptor (in most cases serial)"""
	   
	def __init__(self, node_type):
		# Objects node depend on
		self.File 				= MkSFile.File()
		self.Device 			= None
		self.Network			= None
		# Node connection to WS information
		self.ApiUrl 			= ""
		self.WsUrl				= ""
		self.UserName 			= ""
		self.Password 			= ""
		self.NodeType 			= node_type
		# Device information
		self.Type 				= 0
		self.UUID 				= ""
		self.IsHardwareBased 	= False
		self.OSType 			= ""
		self.OSVersion 			= ""
		self.BrandName 			= ""
		self.DeviceInfo 		= None
		# Misc
		self.Sensors 			= []
		self.SensorsLoaded 		= False
		self.State 				= 'IDLE'
		self.IsRunnig 			= True
		self.AccessTick 		= 0
		# Inner state
		self.States = {
			'IDLE': 			self.StateIdle,
			'CONNECT_DEVICE':	self.StateConnectDevice,
			'ACCESS': 			self.StateGetAccess,
			'WORK': 			self.StateWork
		}
		# Callbacks
		self.WorkingCallback 		= None
		self.OnWSDataArrived 		= None
		self.OnWSConnected 			= None
		self.OnWSConnectionClosed 	= None
		self.OnNodeSystemLoaded 	= None
		# Locks and Events
		self.NetworkAccessTickLock 	= threading.Lock()
		self.DeviceLock			 	= threading.Lock()
		self.ExitEvent 				= threading.Event()
	
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
			self.Type 				= dataSystem["device"]["type"]
			self.OSType 			= dataSystem["device"]["ostype"]
			self.OSVersion 			= dataSystem["device"]["osversion"]
			self.BrandName 			= dataSystem["device"]["brandname"]
			# Device UUID MUST be read from HW device.
			if "True" == dataSystem["device"]["isHW"]:
				self.IsHardwareBased = True
				if "" != dataSystem["sensors"]:
					for sensor in dataSystem["sensors"]:
						self.Sensors.append(MkSSensor.Sensor(self.UUID, sensor["type"], sensor["id"]))
						self.SensorsLoaded = True
			else:
				self.UUID = dataSystem["device"]["uuid"]
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
		print "StateGetAccess"
		# Let the state machine know that this state was entered.
		self.NetworkAccessTickLock.acquire()
		try:
			self.AccessTick = 1
		finally:
			self.NetworkAccessTickLock.release()		
		if self.Network.Connect(self.UserName, self.Password) == True:
			print "Register Device ..."
			data, error = self.Network.RegisterDevice(self.DeviceInfo)
			if error == False:
				return
	
	def StateWork (self):
		self.WorkingCallback()
	
	def WebSocketConnectedCallback (self):
		self.State = "WORK"
		self.OnWSConnected()

	def WebSocketDataArrivedCallback (self, json):
		self.State = "WORK"
		request = self.Network.GetRequestFromJson(json)
		if request == "direct":
			payload = self.Network.GetPayloadFromJson(json)
			command = self.Network.GetCommandFromJson(json)
			self.OnWSDataArrived(command, payload);
		else:
			print "Error: Not support " + request + " request type."

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

	def Response (self, command, payload):
		response = self.Network.BuildDirectResponse(command, payload)
		print "[RESPONSE] " + response
		ret = self.Network.Response(response)
		if False == ret:
			self.State = "ACCESS"
		return ret

	def GetSensorList (self):
		return self.Sensors
	
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

		self.OnNodeSystemLoaded()
		
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
		
		self.Device.Disconnect()
		self.ExitEvent.set()

	def Run (self, callback):
		self.ExitEvent.clear()
		thread.start_new_thread(self.NodeWorker, (callback, ))
		# Waiting here till SIGNAL from OS will come.
		while self.IsRunnig:
			time.sleep(0.5)
		
		self.ExitEvent.wait()
	
	def Stop (self):
		print "Stop"
		self.IsRunnig = False
	
	def Pause (self):
		print "Pause"
	
	def Exit (self):
		print "Exit with ERROR"
		self.Stop()
