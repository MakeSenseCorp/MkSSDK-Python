#!/usr/bin/python
import os
import urllib2
import urllib
import websocket
import sys
if sys.version_info[0] < 3:
	import thread
else:
	import _thread
import time
import json

from mksdk import MkSBasicNetworkProtocol

class Network ():
	def __init__(self, uri, wsuri):
		self.Name 		  	= "Communication to Node.JS"
		self.ClassName 		= "MkSNetwork"
		self.BasicProtocol 	= None
		self.ServerUri 	  	= uri
		self.WSServerUri  	= wsuri
		self.UserName 	  	= ""
		self.Password 	  	= ""
		self.UserDevKey   	= ""
		self.WSConnection 	= None
		self.DeviceUUID   	= ""
		self.Type 		  	= 0
		self.State 			= "DISCONN"
		self.Logger 		= None

		self.OnConnectionCallback 		= None
		self.OnDataArrivedCallback 		= None
		self.OnErrorCallback 			= None
		self.OnConnectionClosedCallback = None

	def SetLogger(self, logger):
		self.Logger = logger

	def GetNetworkState(self):
		return self.State

	def GetRequest (self, url):
		try:
			req = urllib2.urlopen(url, timeout=1)
			if req != None:
				data = req.read()
			else:
				return "failed"
		except:
			return "failed"

		return data
		
	def PostRequset (self, url, payload):
		try:
			data = urllib2.urlopen(url, payload).read()
		except:
			return "failed"
		
		return data
	
	def RegisterDevice (self, device):
		jdata = json.dumps([{"key":"" + str(self.UserDevKey) + "", "payload":{"uuid":"" + str(device.UUID) + "","type":"" + str(device.Type) + "","ostype":"" + str(device.OSType) + "","osversion":"" + str(device.OSVersion) + "","brandname":"" + str(device.BrandName) + ""}}])
		data = self.PostRequset(self.ServerUri + "device/register/", jdata)

		if ('info' in data):
			return data, True
		
		return "", False

	def RegisterDeviceToPublisher (self, publisher, subscriber):
		jdata = json.dumps([{"key":"" + str(self.UserDevKey) + "", "payload":{"publisher_uuid":"" + str(publisher) + "","listener_uuid":"" + str(subscriber) + ""}}])
		data = self.PostRequset(self.ServerUri + "register/device/node/listener", jdata)

		if ('info' in data):
			return data, True
		
		return "", False

	def WSConnection_OnMessage_Handler (self, ws, message):
		data = json.loads(message)
		if self.OnDataArrivedCallback is not None:
			self.OnDataArrivedCallback(data)

	def WSConnection_OnError_Handler (self, ws, error):
		if self.OnErrorCallback is not None:
			self.OnErrorCallback()
		self.Logger.info("({classname})# {0}".format(error,classname=self.ClassName))
		print ("({classname})# {0}".format(error,classname=self.ClassName))

	def WSConnection_OnClose_Handler (self, ws):
		self.State = "DISCONN"
		if self.OnConnectionClosedCallback is not None:
			self.OnConnectionClosedCallback()
		
	def WSConnection_OnOpen_Handler (self, ws):
		self.State = "CONN"
		if self.OnConnectionCallback is not None:
			self.OnConnectionCallback()

	def NodeWebfaceSocket_Thread (self):
		self.Logger.info("({classname})# Connect Gateway ({url})...".format(url=self.WSServerUri,classname=self.ClassName))
		print("({classname})# Connect Gateway ({url})...".format(url=self.WSServerUri,classname=self.ClassName))
		self.WSConnection.keep_running = True
		self.WSConnection.run_forever()

	def Disconnect(self):
		self.WSConnection.keep_running = False
		time.sleep(1)

	def AccessGateway (self, key, payload):
		# Set user key, commub=nication with applications will be based on key.
		# Key will be obtain by master on provisioning flow.
		self.UserDevKey 				= key
		self.BasicProtocol 				= MkSBasicNetworkProtocol.BasicNetworkProtocol()
		self.BasicProtocol.SetKey(key)
		websocket.enableTrace(False)
		self.WSConnection 				= websocket.WebSocketApp(self.WSServerUri)
		self.WSConnection.on_message 	= self.WSConnection_OnMessage_Handler
		self.WSConnection.on_error 		= self.WSConnection_OnError_Handler
		self.WSConnection.on_close 		= self.WSConnection_OnClose_Handler
		self.WSConnection.on_open 		= self.WSConnection_OnOpen_Handler
		self.WSConnection.header		= 	{
											'uuid':self.DeviceUUID, 
											'node_type':str(self.Type), 
											'payload':str(payload), 
											'key':key
											}
		self.Disconnect()
		print("# TODO - This thread will be created each time when connection lost or on retry!!!")
		thread.start_new_thread(self.NodeWebfaceSocket_Thread, ())

		return True

	def SetDeviceUUID (self, uuid):
		self.DeviceUUID = uuid

	def SetDeviceType (self, type):
		self.Type = type
		
	def SetApiUrl (self, url):
		self.ServerUri = url
		
	def SetWsUrl (self, url):
		self.WSServerUri = url

	def SendWebSocket(self, packet):
		try:
			if packet is not "" and packet is not None:
				self.Logger.info("({classname})# Node -> Gateway".format(classname=self.ClassName))
				self.WSConnection.send(packet)
			else:
				self.Logger.info("({classname})# Sending packet to Gateway FAILED".format(classname=self.ClassName))
				print ("({classname})# Sending packet to Gateway FAILED".format(classname=self.ClassName))
		except:
			return False
		
		return True
