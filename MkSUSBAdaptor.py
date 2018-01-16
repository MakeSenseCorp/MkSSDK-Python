#!/usr/bin/python
import os
import time
import sys
import serial
import struct
import thread

class Adaptor ():
	UsbPath = ""
	Interfaces = ""
	SerialAdapter = None

	def __init__(self):
		self.UsbPath 						  = "/dev/"
		self.DataArrived 					  = False;
		self.RXData 						  = ""
		self.OnSerialConnectedCallback 		  = None
		self.OnSerialDataArrivedCallback 	  = None
		self.OnSerialErrorCallback 			  = None
		self.OnSerialConnectionClosedCallback = None
		self.RecievePacketsWorkerRunning 	  = True
		self.DeviceConnected				  = False
		self.DeviceConnectedName 			  = ""
		self.ExitRecievePacketsWorker 		  = False

		self.Initiate()

	def Initiate (self):
		dev = os.listdir(self.UsbPath)
		self.Interfaces = [item for item in dev if "ttyUSB" in item]
		print self.Interfaces

	def ConnectDevice(self, id, withtimeout):
		self.SerialAdapter 			= serial.Serial()
		self.SerialAdapter.port		= self.UsbPath + self.Interfaces[id-1]
		self.SerialAdapter.baudrate	= 9600
		# That will disable the assertion of DTR which is resetting the board.
		self.SerialAdapter.setDTR(False)
		
		try:
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
			print "ERROR: Serial adpater. " + str(e)
			
		if self.SerialAdapter != None:
			print "Connected to " + self.UsbPath + self.Interfaces[id-1]
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
		while self.ExitRecievePacketsWorker == False and self.DeviceConnected == True:
			time.sleep(0.1)
		if self.SerialAdapter != None:
			self.SerialAdapter.close()
		print "Serial connection to " + self.DeviceConnectedName + " was closed ..."

	def Send (self, data):
		self.DataArrived = False
		self.SerialAdapter.write(str(data) + '\n')
		while self.DataArrived == False and self.DeviceConnected == True:
			time.sleep(0.1)
		return self.RXData

	def RecievePacketsWorker (self):
		while self.RecievePacketsWorkerRunning == True:
			try:
				self.RXData = self.SerialAdapter.readline()
			except Exception, e:
				print "ERROR: Serial adpater. " + str(e)
				self.RXData = ""
			self.DataArrived = True
			print ":".join("{:02x}".format(ord(c)) for c in self.RXData)
		self.ExitRecievePacketsWorker = True
