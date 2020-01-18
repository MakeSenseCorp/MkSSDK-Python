#!/usr/bin/python
import os
import sys
import json
if sys.version_info[0] < 3:
	import thread
else:
	import _thread
import threading
import time

from geventwebsocket import WebSocketServer, WebSocketApplication, Resource
from collections import OrderedDict

class MkSLocalWebsocketServer():
	def __init__(self):
		self.ClassName 				= "LocalWebsocketServer"
		self.ApplicationSockets 	= {}
	
	def AppendSocket(self, ws_id, ws):
		print ("({classname})# Append new connection".format(classname=self.ClassName))
		self.ApplicationSockets[ws_id] = ws
	
	def RemoveSocket(self, ws_id):
		print ("({classname})# Remove connection".format(classname=self.ClassName))
		del self.ApplicationSockets[ws_id]

	def Worker(self):
		server = WebSocketServer(('', 1982), Resource(OrderedDict([('/', NodeWSApplication)])))
		server.serve_forever()
	
	def RunServer(self):
		thread.start_new_thread(self.Worker, ())

WSManager = MkSLocalWebsocketServer()
WSManager.RunServer()

class NodeWSApplication(WebSocketApplication):
	def __init__(self, *args, **kwargs):
		self.ClassName = "NodeWSApplication"
		super(NodeWSApplication, self).__init__(*args, **kwargs)
	
	def on_open(self):
		print ("({classname})# CONNECTION OPENED".format(classname=self.ClassName))
		WSManager.AppendSocket(id(self.ws), self.ws)

	def on_message(self, message):
		print ("({classname})# MESSAGE RECIEVED {0} {1}".format(id(self.ws),message,classname=self.ClassName))
		#if (message is None):
		#	WSManager.RemoveSocket(id(self.ws))
		# self.ws.send(message)

	def on_close(self, reason):
		print ("({classname})# CONNECTION CLOSED".format(classname=self.ClassName))
		WSManager.RemoveSocket(id(self.ws))

while (True):
	time.sleep(1)
