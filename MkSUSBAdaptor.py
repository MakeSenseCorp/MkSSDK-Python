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
import threading

class Adaptor ():
	def __init__(self, path, baudrate):
		self.ClassName 						  = "Adaptor"
		self.SerialAdapter 					  = None
		self.DevicePath						  = path
		self.DeviceBaudrate					  = baudrate

		self.DataArrived 					  = False
		self.SendRequest 					  = False
		self.RXData 						  = ""
		self.RecievePacketsWorkerRunning 	  = True
		self.DeviceConnected				  = False
		self.ExitRecievePacketsWorker 		  = False
		# Callbacks
		self.OnSerialConnectedCallback 		  = None
		self.OnSerialDataArrivedCallback 	  = None
		self.OnSerialAsyncDataCallback 	  	  = None
		self.OnSerialErrorCallback 			  = None
		self.OnSerialConnectionClosedCallback = None

		self.RawData						  = ""
		self.PacketEnds 					  = [False, False]

	def Connect(self, withtimeout):
		self.SerialAdapter 			= serial.Serial()
		self.SerialAdapter.port		= self.DevicePath
		self.SerialAdapter.baudrate	= self.DeviceBaudrate
		
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
		except Exception as e:
			print ("({classname})# [ERROR] (Connect) {0}".format(str(e),classname=self.ClassName))
			return False
			
		if self.SerialAdapter != None:
			print ("({classname})# CONNECTED {0}".format(self.DevicePath,classname=self.ClassName))
			self.RecievePacketsWorkerRunning 	= True
			self.DeviceConnected 				= True
			self.ExitRecievePacketsWorker		= False
			thread.start_new_thread(self.RecievePacketsWorker, ())
			return True
		
		return False

	def Disconnect(self):
		self.DeviceConnected 			 = False
		self.RecievePacketsWorkerRunning = False
		while self.ExitRecievePacketsWorker == False and self.DeviceConnected == True:
			time.sleep(0.1)
		if self.SerialAdapter != None:
			self.SerialAdapter.close()
		print ("({classname})# DISCONNECTED {0}".format(self.DevicePath,classname=self.ClassName))
		if self.OnSerialConnectionClosedCallback is not None:
			self.OnSerialConnectionClosedCallback(self.DevicePath)

	def Send(self, data):
		self.DataArrived = False
		self.SendRequest = True

		# Send PAUSE request to HW
		#self.SerialAdapter.write(str(struct.pack("BBBH", 0xDE, 0xAD, 0x5)) + '\n')
		#time.sleep(0.2)

		# Now the device pause all async (if supporting) tasks
		print ("({classname})# TX {0}".format(":".join("{:02x}".format(ord(c)) for c in data),classname=self.ClassName))
		time.sleep(1)
		self.SerialAdapter.write(str(data) + '\n')
		while self.DataArrived == False and self.DeviceConnected == True:
			time.sleep(0.1)
		self.SendRequest = False
		return self.RXData

	def RecievePacketsWorker (self):
		while self.RecievePacketsWorkerRunning == True:
			try:
				self.RawData += self.SerialAdapter.read(1)
				#print (":".join("{:02x}".format(ord(c)) for c in self.RawData))
				if len(self.RawData) > 1:
					if self.PacketEnds[0] == False:
						byte_one, byte_two = struct.unpack("BB", self.RawData)
						if byte_one == 0xde and byte_two == 0xad: # Confirmed start packet
							self.PacketEnds[0] = True
						elif byte_one == 0xad and byte_two == 0xde: # Error
							self.PacketEnds[0] = False
							self.PacketEnds[1] = False
							self.RawData = ""
					elif self.PacketEnds[1] == False:
						byte_one, byte_two = struct.unpack("BB", self.RawData[-2:])
						if byte_one == 0xad and byte_two == 0xde: # Confirmed start packet
							self.PacketEnds[1] = True
						elif byte_one == 0xde and byte_two == 0xad: # Error
							self.PacketEnds[0] = True
							self.PacketEnds[1] = False
							self.RawData = ""

				if self.PacketEnds[0] is True and self.PacketEnds[1] is True:
					direction = ord(self.RawData[2])
					if True == self.SendRequest and direction == 0x2:
						if self.DataArrived == False:
							self.DataArrived = True
							self.SendRequest = False
							print ("({classname})# RX {0}".format(":".join("{:02x}".format(ord(c)) for c in self.RawData),classname=self.ClassName))
							self.RXData = self.RawData
							self.RawData = ""
							self.PacketEnds[0] = False
							self.PacketEnds[1] = False
					elif direction == 0x3:
						print ("({classname})# ASYNC {0}".format(":".join("{:02x}".format(ord(c)) for c in self.RawData),classname=self.ClassName))
						if len(self.RawData) > 2:
							self.RXData = self.RawData
							self.OnSerialAsyncDataCallback(self.DevicePath, self.RXData)
						self.RawData = ""
						self.PacketEnds[0] = False
						self.PacketEnds[1] = False
			except Exception as e:
				print ("({classname})# [ERROR] (RecievePacketsWorker) {0}".format(str(e),classname=self.ClassName))
				self.RawData = ""
				self.RXData  = ""
				self.PacketEnds[0] 	= False
				self.PacketEnds[1] 	= False
				self.DataArrived 	= True
				
		self.ExitRecievePacketsWorker = True
		print ("({classname})# Exit USB Adaptor".format(classname=self.ClassName))
