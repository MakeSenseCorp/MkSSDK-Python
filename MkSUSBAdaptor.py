#!/usr/bin/python
import os
import time
import sys
import serial
import struct
if sys.version_info[0] < 3:
	import thread
else:
	import _thread

class Adaptor ():
	UsbPath = ""
	Interfaces = ""
	SerialAdapter = None

	def __init__(self, asyncCallback):
		self.UsbPath 						  = "/dev/"
		self.DataArrived 					  = False
		self.SendRequest 					  = False
		self.RXData 						  = ""
		self.RecievePacketsWorkerRunning 	  = True
		self.DeviceConnected				  = False
		self.DeviceConnectedName 			  = ""
		self.DeviceComNumber 				  = 0
		self.ExitRecievePacketsWorker 		  = False
		# Callbacks
		self.OnSerialConnectedCallback 		  = None
		self.OnSerialDataArrivedCallback 	  = None
		self.OnSerialAsyncDataCallback 	  	  = asyncCallback
		self.OnSerialErrorCallback 			  = None
		self.OnSerialConnectionClosedCallback = None

		self.Initiate()

	def Initiate (self):
		dev = os.listdir(self.UsbPath)
		self.Interfaces = [item for item in dev if "ttyUSB" in item]
		print self.Interfaces

	def ConnectDevice(self, id, withtimeout):
		self.SerialAdapter 			= serial.Serial()
		self.SerialAdapter.port		= self.UsbPath + self.Interfaces[id-1]
		self.DeviceComNumber 		= id
		self.SerialAdapter.baudrate	= 9600
		
		try:
			# That will disable the assertion of DTR which is resetting the board.
			# self.SerialAdapter.setDTR(False)

			if (withtimeout > 0):
				self.SerialAdapter.timeout = withtimeout
				self.SerialAdapter.open()
			else:
				self.SerialAdapter.open()
			# Only for Arduino issue - The first time it is run there will be a reset, 
			# since setting that flag entails opening the port, which causes a reset. 
			# So we need to add a delay long enough to get past the bootloader make delay 3 sec.
			time.sleep(3)
		except Exception, e:
			print ("ERROR: Serial adpater. " + str(e))
			return False
			
		if self.SerialAdapter != None:
			print ("Connected to " + self.UsbPath + self.Interfaces[id-1])
			self.DeviceConnectedName 			= self.UsbPath + self.Interfaces[id-1]
			self.RecievePacketsWorkerRunning 	= True
			self.DeviceConnected 				= True
			self.ExitRecievePacketsWorker		= False
			thread.start_new_thread(self.RecievePacketsWorker, ())
			return True
		
		return False

	def DisconnectDevice (self):
		self.DeviceConnected 			 = False
		self.RecievePacketsWorkerRunning = False
		print ("[DEBUG::Adaptor] DisconnectDevice")
		while self.ExitRecievePacketsWorker == False and self.DeviceConnected == True:
			time.sleep(0.1)
		if self.SerialAdapter != None:
			self.SerialAdapter.close()
		print ("Serial connection to " + self.DeviceConnectedName + " was closed ...")

	def Send (self, data):
		self.DataArrived = False
		self.SendRequest = True

		# Send PAUSE request to HW
		self.SerialAdapter.write(str(struct.pack("BBH", 0xDE, 0xAD, 0x5)) + '\n')
		time.sleep(0.2)

		# Now the device pause all async (if supporting) tasks
		print ("[OUT] " + ":".join("{:02x}".format(ord(c)) for c in data))
		self.SerialAdapter.write(str(data) + '\n')
		while self.DataArrived == False and self.DeviceConnected == True:
			time.sleep(0.1)
		self.SendRequest = False
		return self.RXData

	def RecievePacketsWorker (self):
		while self.RecievePacketsWorkerRunning == True:
			try:
				self.RXData = self.SerialAdapter.readline()
				if self.RXData == "" and self.DataArrived == False:
					self.RXData = self.SerialAdapter.readline()
			except Exception, e:
				print ("ERROR: Serial adpater. " + str(e))
				self.RXData = ""
				# Need to reconnect, send event to Node.
				if self.OnSerialConnectionClosedCallback != None:
					self.OnSerialConnectionClosedCallback(self.DeviceComNumber)
			if True == self.SendRequest:
				if self.DataArrived == False:
					self.DataArrived = True
					print ("[IN]  " + ":".join("{:02x}".format(ord(c)) for c in self.RXData))
			else:
				print ("[IN ASYNC]  " + ":".join("{:02x}".format(ord(c)) for c in self.RXData))
				if len(self.RXData) > 2:
					self.OnSerialAsyncDataCallback(self.RXData)
		self.ExitRecievePacketsWorker = True
