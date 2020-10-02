#!/usr/bin/python
import os
import sys
import json
import thread

class MkSStream():
	def __init__(self, context):
		self.ClassName 				= "MkSLocalWebsocketServer"
		self.Context 				= context
		self.OnConnectedEvent 		= None
		self.OnDataArrivedEvent 	= None
		self.State 					= "IDLE"
	
	def Worker(self):
		pass

	def Connect(self, uuid):
		pass

	def Disconnect(self):
		pass

	def Send(self, data):
		pass

	def SetState(self, state):
		pass
