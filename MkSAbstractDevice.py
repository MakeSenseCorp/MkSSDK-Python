#!/usr/bin/python
import os
import sys
import json
import thread
import threading

class AbstractDevice():
	def __init__(self, on_data_ready_callback):
		self.Type 					= None
		self.UUID 					= ""
		# Flags
		self.IsConnected 			= False
		# Events
		self.OnDataReadyCallback 	= on_data_ready_callback

	def Connect(self):
		self.IsConnected = True
		return True

	def DisConnect(self):
		self.IsConnected = False
		return True

	def Send(self, data):
		return "Abstract"