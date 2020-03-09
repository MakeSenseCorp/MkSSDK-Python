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

		self.SendRequest					  = False
		self.DataArrived 					  = False
		self.RXData 						  = []
		self.RecievePacketsWorkerRunning 	  = True
		self.DeviceConnected				  = False
		self.ExitRecievePacketsWorker 		  = False
		# Callbacks
		self.OnSerialConnectedCallback 		  = None
		self.OnSerialDataArrivedCallback 	  = None
		self.OnSerialAsyncDataCallback 	  	  = None
		self.OnSerialErrorCallback 			  = None
		self.OnSerialConnectionClosedCallback = None

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
		# Send PAUSE request to HW
		#self.SerialAdapter.write(str(struct.pack("BBBH", 0xDE, 0xAD, 0x5)) + '\n')
		#time.sleep(0.2)

		self.DataArrived = False
		self.SendRequest = True
		# Now the device pause all async (if supporting) tasks
		time.sleep(0.1)
		self.SerialAdapter.write(str(data) + '\n')
		print ("({classname})# TX {0}".format(":".join("{:02x}".format(ord(c)) for c in data),classname=self.ClassName))
		tick_timer = 0
		while self.DataArrived == False and self.DeviceConnected == True and tick_timer < 30:
			time.sleep(0.1)
			tick_timer += 1
		print ("({classname})# RX {0}".format(self.RXData,classname=self.ClassName))
		self.SendRequest = False
		return self.RXData

	def RecievePacketsWorker (self):
		shift_buffer 		= [0, 0]
		packet_data_start 	= False
		packet_data_end 	= False
		packet_data			= []
		while self.RecievePacketsWorkerRunning == True:
			try:
				s_byte = self.SerialAdapter.read(1)
				if s_byte != "":
					shift_buffer[0] = shift_buffer[1]
					shift_buffer[1] = struct.unpack("B", s_byte)[0]
					# ''.join([str(elem) if elem not in ['\r','\n',''] else "-" for elem in shift_buffer])

					if shift_buffer[0] == 0xde and shift_buffer[1] == 0xad: 	# Confirmed start packet
						packet_data = []
						packet_data_start	= True
					elif shift_buffer[0] == 0xad and shift_buffer[1] == 0xde: # Confirmed end packet
						packet_data_end 	= True

					if packet_data_start is True and packet_data_end is True: # Whole packet arrived
						self.RXData = packet_data[1:-1]
						direction = self.RXData[0]
						if True == self.SendRequest and direction == 2:
							if self.DataArrived == False:
								self.DataArrived = True
						elif direction == 3:
							# ":".join("{:02x}".format(ord(c)) for c in self.RXData)
							print ("({classname})# ASYNC {0}".format(self.RXData,classname=self.ClassName))
							if len(self.RXData) > 2:
								if self.OnSerialAsyncDataCallback is not None:
									self.OnSerialAsyncDataCallback(self.DevicePath, self.RXData)
						packet_data_start	= False
						packet_data_end		= False
					elif packet_data_start is True and packet_data_end is False: # In middle of packet transfare
						packet_data.append(shift_buffer[1])
					elif packet_data_start is False and packet_data_end is True:  # Error
						packet_data_end 	= False
						packet_data 		= []
						self.RXData 		= []
						self.DataArrived 	= True # Relese sync uart read
					elif packet_data_start is False and packet_data_end is False:  # Error
						pass
			except Exception as e:
				print ("({classname})# [ERROR] (RecievePacketsWorker) {0} {1}".format(str(e), self.RXData, classname=self.ClassName))
				if "device disconnected?" in str(e):
					# Device disconnected
					self.DeviceConnected 				= True
					self.RecievePacketsWorkerRunning 	= False
					self.Disconnect()
				self.RXData  		= ""
				self.DataArrived 	= True
				
		self.ExitRecievePacketsWorker = True
		print ("({classname})# Exit USB Adaptor".format(classname=self.ClassName))
