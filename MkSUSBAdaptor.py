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
	SerialAdapter = ""

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
		if (withtimeout > 0):
			self.SerialAdapter = serial.Serial(port=self.UsbPath+self.Interfaces[id-1], baudrate=9600, parity=serial.PARITY_ODD, stopbits=serial.STOPBITS_TWO, bytesize=serial.SEVENBITS, timeout=withtimeout)
		else:
			self.SerialAdapter = serial.Serial(port=self.UsbPath+self.Interfaces[id-1], baudrate=9600, parity=serial.PARITY_ODD, stopbits=serial.STOPBITS_TWO, bytesize=serial.SEVENBITS)

		if self.SerialAdapter != "":
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
		while self.ExitRecievePacketsWorker == False:
			time.sleep(0.1)
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
			self.RXData = self.SerialAdapter.readline()
			self.DataArrived = True
			print ":".join("{:02x}".format(ord(c)) for c in self.RXData)
		self.ExitRecievePacketsWorker = True

