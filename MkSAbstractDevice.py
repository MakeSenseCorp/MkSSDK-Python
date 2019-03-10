#!/usr/bin/python
import os
import sys
import json
if sys.version_info[0] < 3:
	import thread
else:
	import _thread
import threading

from mksdk import MkSFile

class AbstractDevice():
	def __init__(self):
		self.File 					= MkSFile.File()
		self.Type 					= None
		self.UUID 					= ""
		# Flags
		self.IsConnected 			= False
		# Events
		self.OnDataReadyCallback 	= None

		jsonSystemStr = self.File.LoadStateFromFile("system.json")
		try:
			dataSystem 				= json.loads(jsonSystemStr)
			self.UUID = dataSystem["node"]["uuid"]
			self.DeviceInfoJson = dataSystem["device"]
		except:
			print ("Error: [LoadSystemConfig] Wrong system.json format")
			self.Exit()

	def RegisterOnDataReadyCallback(self, on_data_ready_callback):
		self.OnDataReadyCallback = on_data_ready_callback

	def Connect(self):
		self.IsConnected = True
		return self.IsConnected

	def Disconnect(self):
		self.IsConnected = False
		return self.IsConnected

	def Send(self, data):
		return "Abstract"