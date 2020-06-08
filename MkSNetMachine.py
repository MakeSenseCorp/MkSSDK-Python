#!/usr/bin/python
import os
import urllib2
import urllib
import websocket
import sys
import time
import json

if sys.version_info[0] < 3:
	import thread
else:
	import _thread

from mksdk import MkSBasicNetworkProtocol
from mksdk import MkSTransceiver
from mksdk import MkSLocalSocketUtils

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
		self.Transceiver	= MkSTransceiver.Manager(self.WebSocketTXCallback, self.WebSocketRXCallback)

		self.OnConnectionCallback 		= None
		self.OnDataArrivedCallback 		= None
		self.OnErrorCallback 			= None
		self.OnConnectionClosedCallback = None

		# RX
		self.RXHandlerMethod            = {
			"websock_new_connection":	self.WebSockNewConnection_RXHandlerMethod,
			"websock_data_arrived":		self.WebSockDataArrived_RXHandlerMethod,
			"websock_disconnected":	    self.WebSockDisconnected_RXHandlerMethod,
			"websock_error":		    self.WebSockError_RXHandlerMethod,
		}

	''' 
		Description: 	
		Return: 		
	'''   
	def WebSockNewConnection_RXHandlerMethod(self, data):
		self.Logger.Log("({classname})# [WebSockNewConnection_RXHandlerMethod]".format(classname=self.ClassName))
		if self.OnConnectionCallback is not None:
			self.OnConnectionCallback()

	''' 
		Description: 	
		Return: 		
	'''  		
	def WebSockDataArrived_RXHandlerMethod(self, data):
		self.Logger.Log("({classname})# [WebSockDataArrived_RXHandlerMethod]".format(classname=self.ClassName))
		packet	= data["data"]
		# Raise event for user
		try:
			if self.OnDataArrivedCallback is not None:
				self.OnDataArrivedCallback(data)
		except Exception as e:
			self.Logger.Log("({classname})# [WebSockDataArrived_RXHandlerMethod] ERROR {0}".format(e,classname=self.ClassName))

	''' 
		Description: 	
		Return: 		
	'''  	
	def WebSockDisconnected_RXHandlerMethod(self, sock):
		self.Logger.Log("({classname})# [WebSockDisconnected_RXHandlerMethod]".format(classname=self.ClassName))
		if self.OnConnectionClosedCallback is not None:
			self.OnConnectionClosedCallback()

	''' 
		Description: 	
		Return: 		
	'''  	
	def WebSockError_RXHandlerMethod(self, error):
		self.Logger.Log("({classname})# [WebSockError_RXHandlerMethod] {0}".format(error,classname=self.ClassName))
		if self.OnErrorCallback is not None:
			self.OnErrorCallback()

	''' 
		Description: 	
		Return: 		
	'''    
	def WebSocketTXCallback(self, item):
		try:
			self.Logger.Log("({classname})# [WebSocketTXCallback]".format(classname=self.ClassName))
			packet = item["packet"]
			if packet is not "" and packet is not None:
				pckt 	= json.loads(packet)
				src  	= self.BasicProtocol.GetSourceFromJson(pckt)
				dst  	= self.BasicProtocol.GetDestinationFromJson(pckt)
				drt 	= self.BasicProtocol.GetDirectionFromJson(pckt)
				cmd 	= self.BasicProtocol.GetCommandFromJson(pckt)
				self.Logger.Log("({classname})# Node -> Gateway [{2}] {0} -> {1} ({3})".format(src,dst,drt,cmd,classname=self.ClassName))
				self.WSConnection.send(packet)
			else:
				self.Logger.Log("({classname})# Sending packet to Gateway FAILED".format(classname=self.ClassName))
		except Exception as e:
			self.Logger.Log("({classname})# ERROR - [WebSocketTXCallback]\n\n********** EXCEPTION **********\n----\nITEM\n----\n{0}\n-----\nERROR\n-----\n({error})\n********************************\n".format(
				item["packet"],
				classname=self.ClassName,
				error=str(e)))

	''' 
		Description: 	
		Return: 		
	'''  	
	def WebSocketRXCallback(self, item):
		try:
			self.Logger.Log("({classname})# [WebSocketRXCallback]".format(classname=self.ClassName))
			self.RXHandlerMethod[item["type"]](item["data"])
		except Exception as e:
			self.Logger.Log("({classname})# ERROR - [WebSocketTXCallback]\n\n********** EXCEPTION **********\n----\nITEM\n----\n{0}\n-----\nERROR\n-----\n({error})\n********************************\n".format(
				item,
				classname=self.ClassName,
				error=str(e)))

	''' 
		Description: 	
		Return: 		
	''' 
	def SetLogger(self, logger):
		self.Logger = logger

	''' 
		Description: 	
		Return: 		
	''' 
	def GetNetworkState(self):
		return self.State

	''' 
		Description: 	
		Return: 		
	''' 
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

	''' 
		Description: 	
		Return: 		
	''' 		
	def PostRequset (self, url, payload):
		try:
			data = urllib2.urlopen(url, payload).read()
		except:
			return "failed"
		
		return data

	''' 
		Description: 	
		Return: 		
	''' 	
	def RegisterDevice (self, device):
		jdata = json.dumps([{"key":"" + str(self.UserDevKey) + "", "payload":{"uuid":"" + str(device.UUID) + "","type":"" + str(device.Type) + "","ostype":"" + str(device.OSType) + "","osversion":"" + str(device.OSVersion) + "","brandname":"" + str(device.BrandName) + ""}}])
		data = self.PostRequset(self.ServerUri + "device/register/", jdata)

		if ('info' in data):
			return data, True
		
		return "", False

	''' 
		Description: 	
		Return: 		
	''' 
	def RegisterDeviceToPublisher (self, publisher, subscriber):
		jdata = json.dumps([{"key":"" + str(self.UserDevKey) + "", "payload":{"publisher_uuid":"" + str(publisher) + "","listener_uuid":"" + str(subscriber) + ""}}])
		data = self.PostRequset(self.ServerUri + "register/device/node/listener", jdata)

		if ('info' in data):
			return data, True
		
		return "", False

	''' 
		Description: 	
		Return: 		
	''' 
	def WSConnection_OnMessage_Handler (self, ws, message):
		data = json.loads(message)
		self.Transceiver.Receive({
			"type": "websock_data_arrived",
			"data": data
		})

	''' 
		Description: 	
		Return: 		
	''' 
	def WSConnection_OnError_Handler (self, ws, error):
		self.Transceiver.Receive({
			"type": "websock_error",
			"data": error
		})

	''' 
		Description: 	
		Return: 		
	''' 
	def WSConnection_OnClose_Handler (self, ws):
		self.State = "DISCONN"
		self.Transceiver.Receive({
			"type": "websock_disconnected",
			"data": {}
		})

	''' 
		Description: 	
		Return: 		
	''' 		
	def WSConnection_OnOpen_Handler (self, ws):
		self.State = "CONN"
		self.Transceiver.Receive({
			"type": "websock_new_connection",
			"data": {}
		})

	''' 
		Description: 	
		Return: 		
	''' 
	def NodeWebfaceSocket_Thread (self):
		self.Logger.Log("({classname})# Connect Gateway ({url})...".format(url=self.WSServerUri,classname=self.ClassName))
		self.WSConnection.keep_running = True
		self.WSConnection.run_forever()
		self.Logger.Log("({classname})# Gateway Disconnected ({url})...".format(url=self.WSServerUri,classname=self.ClassName))

	''' 
		Description: 	
		Return: 		
	''' 
	def Disconnect(self):
		self.Logger.Log("({classname})# Close WebSocket Connection ...".format(classname=self.ClassName))
		self.WSConnection.keep_running = False
		time.sleep(1)

	''' 
		Description: 	
		Return: 		
	''' 
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

	''' 
		Description: 	
		Return: 		
	''' 
	def SetDeviceUUID (self, uuid):
		self.DeviceUUID = uuid

	''' 
		Description: 	
		Return: 		
	''' 
	def SetDeviceType (self, type):
		self.Type = type

	''' 
		Description: 	
		Return: 		
	''' 		
	def SetApiUrl (self, url):
		self.ServerUri = url

	''' 
		Description: 	
		Return: 		
	''' 		
	def SetWsUrl (self, url):
		self.WSServerUri = url

	''' 
		Description: 	
		Return: 		
	''' 
	def SendWebSocket(self, packet):
		return self.Transceiver.Send({"packet":packet})
