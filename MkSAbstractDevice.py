#!/usr/bin/python
import os
import sys
import json
import thread
import threading

class AbstractDevice():
	def __init__(self):
		self.Type 					= None
		self.UUID 					= ""
		# Flags
		self.IsConnected 			= False
		# Events
		self.OnDataReadyCallback 	= None

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