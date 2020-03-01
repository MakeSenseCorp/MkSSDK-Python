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

		self.RawData						  = ""
		self.PacketEnds 					  = [False, False]

		self.Initiate()

	def Initiate (self):
		dev = os.listdir(self.UsbPath)
		self.Interfaces = [item for item in dev if "ttyUSB" in item]
		print (self.Interfaces)

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
		#self.SerialAdapter.write(str(struct.pack("BBBH", 0xDE, 0xAD, 0x5)) + '\n')
		#time.sleep(0.2)

		# Now the device pause all async (if supporting) tasks
		print ("[TX] " + ":".join("{:02x}".format(ord(c)) for c in data))
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
							print ("[RX] " + ":".join("{:02x}".format(ord(c)) for c in self.RawData))
							self.RXData = self.RawData
							self.RawData = ""
							self.PacketEnds[0] = False
							self.PacketEnds[1] = False
					elif direction == 0x3:
						print ("[ASYNC] " + ":".join("{:02x}".format(ord(c)) for c in self.RawData))
						if len(self.RawData) > 2:
							self.RXData = self.RawData
							self.OnSerialAsyncDataCallback(self.RXData)
						self.RawData = ""
						self.PacketEnds[0] = False
						self.PacketEnds[1] = False
			except Exception as e:
				print ("ERROR: Serial adpater. " + str(e))
				self.RawData = ""
				if self.OnSerialConnectionClosedCallback != None:
					self.OnSerialConnectionClosedCallback(self.DeviceComNumber)
		
		self.ExitRecievePacketsWorker = True
		print("Exit USB Adaptor")
