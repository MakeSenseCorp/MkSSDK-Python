#!/usr/bin/python
import os
import urllib2
import urllib
import websocket
import thread
import time
import json
import sys

class Network ():
	def __init__(self, uri, wsuri):
		self.Name 		  = "Communication to Node.JS"
		self.ServerUri 	  = uri
		self.WSServerUri  = wsuri
		self.UserName 	  = ""
		self.Password 	  = ""
		self.UserDevKey   = ""
		self.WSConnection = None
		self.DeviceUUID   = ""
		self.Type 		  = 0

		self.OnConnectionCallback 		= None
		self.OnDataArrivedCallback 		= None
		self.OnErrorCallback 			= None
		self.OnConnectionClosedCallback = None

	def GetRequest (self, url):
		try:
			data = urllib2.urlopen(url).read()
		except:
			return "failed"

		return data
		
	def PostRequset (self, url, payload):
		try:
			data = urllib2.urlopen(url, payload).read()
		except:
			return "failed"
		
		return data

	def Authenticate (self, username, password):
		data = self.GetRequest(self.ServerUri + "fastlogin/" + self.UserName + "/" + self.Password)

		if ('failed' in data):
			return False

		jsonData = json.loads(data)
		if ('error' in jsonData):
			return False
		else:
			self.UserDevKey = jsonData['key']
			return True

	def InsertDevice (self, device):
		data = self.GetRequest(self.ServerUri + "insert/device/" + self.UserDevKey + "/" + str(device.Type) + "/" + device.UUID + "/" + device.OSType + "/" + device.OSVersion + "/" + device.BrandName)

		if ('failed' in data):
			return "", False

		if ('info' in data):
			return data, True;

		return False
	
	def RegisterDevice (self, device):
		jdata = json.dumps([{"key":"" + str(self.UserDevKey) + "", "payload":{"uuid":"" + str(device.UUID) + "","type":"" + str(device.Type) + "","ostype":"" + str(device.OSType) + "","osversion":"" + str(device.OSVersion) + "","brandname":"" + str(device.BrandName) + ""}}])
		data = self.PostRequset(self.ServerUri + "device/register/", jdata)

		if ('info' in data):
			return data, True;
		
		return "", False

	def RegisterDeviceToPublisher (self, publisher, subscriber):
		jdata = json.dumps([{"key":"" + str(self.UserDevKey) + "", "payload":{"publisher_uuid":"" + str(publisher) + "","listener_uuid":"" + str(subscriber) + ""}}])
		data = self.PostRequset(self.ServerUri + "register/device/node/listener", jdata)

		if ('info' in data):
			return data, True;
		
		return "", False

	def WSConnection_OnMessage_Handler (self, ws, message):
		data = json.loads(message)
		self.OnDataArrivedCallback(data)

	def WSConnection_OnError_Handler (self, ws, error):
	    self.OnErrorCallback()
	    print error

	def WSConnection_OnClose_Handler (self, ws):
	    self.OnConnectionClosedCallback()
		
	def WSConnection_OnOpen_Handler (self, ws):
		self.OnConnectionCallback()

	def WSWorker (self):
		self.WSConnection.run_forever()

	def Connect (self, username, password, payload):
		self.UserName = username
		self.Password = password

		# TODO 	- Add retry counter.
		#		- Handle socket error [No handlers could be found for logger "websocket"]
		ret = self.Authenticate(username, password)
		if ret == True:
			websocket.enableTrace(False)
			self.WSConnection 				= websocket.WebSocketApp(self.WSServerUri)
			self.WSConnection.on_message 	= self.WSConnection_OnMessage_Handler
			self.WSConnection.on_error 		= self.WSConnection_OnError_Handler
			self.WSConnection.on_close 		= self.WSConnection_OnClose_Handler
			self.WSConnection.on_open 		= self.WSConnection_OnOpen_Handler
			self.WSConnection.header		= {'uuid':self.DeviceUUID, 'payload':str(payload), 'key':self.UserDevKey}
			print self.WSConnection.header
			thread.start_new_thread(self.WSWorker, ())
			return True

		return False

	def SetDeviceUUID (self, uuid):
		self.DeviceUUID = uuid;

	def SetDeviceType (self, type):
		self.Type = type;
		
	def SetApiUrl (self, url):
		self.ServerUri = url;
		
	def SetWsUrl (self, url):
		self.WSServerUri = url;

	def SendWebSocket(self, payload):
		self.WSConnection.send(payload)

	def SendKeepAlive(self):
		self.WSConnection.send("{\"packet_type\":\"keepalive\"}")

	def BuildJSONFromBasicSensorListToHost (self, sensors):
		payload = "{\"response\":\"sensors_publish\",\"data\":{\"key\":\"" + str(self.UserDevKey) + "\",\"device\":{\"uuid\":\"" + str(self.DeviceUUID) + "\",\"type\":" + str(self.Type) + ",\"cmd\":\"get_device_sensors\"},\"sensors\":["
		for item in sensors:
			payload += "{\"uuid\":\"" + str(item.UUID) + "\",\"type\":" + str(item.Type) + ",\"value\":" + str(item.Value) + "},"
		payload = payload[:-1]
		payload += "]}}"
		return payload

	def BuildDirectResponse (self, command, payload):
		response = "{\"response\":\"direct\",\"data\":{\"key\":\"" + str(self.UserDevKey) + "\",\"device\":{\"uuid\":\"" + str(self.DeviceUUID) + "\",\"type\":" + str(self.Type) + ",\"cmd\":\"" + command + "\"},\"payload\":{" + payload + "}}}"
		return response
	
	def BuildJSONFromBasicSensorList (self, sensors):
		payload = "{\"key\":\"" + str(self.UserDevKey) + "\",\"device\":{\"uuid\":\"" + str(self.DeviceUUID) + "\",\"type\":" + str(self.Type) + "},\"sensors\":["
		for item in sensors:
			payload += "{\"uuid\":\"" + str(item.UUID) + "\",\"type\":" + str(item.Type) + ",\"value\":" + str(item.Value) + "},"
		payload = payload[:-1]
		payload += "]}"
		return payload

	def GetUUIDFromJson(self, json):
		return json['uuid']

	def GetValueFromJson(self, json):
		return json['value']
	
	def GetRequestFromJson(self, json):
		return json['request']

	def GetCommandFromJson(self, json):
		return json['data']['device']['cmd']

	def GetPayloadFromJson(self, json):
		return json['data']['payload']

	def GetDataFromJson(self, json):
		return json['data']
	
	def Response(self, payload):
		try:
			self.SendWebSocket(payload)
		except:
			return False
		
		return True

	def UpdateSensorsWS(self, sensors):
		if (len(sensors) > 0):
			payload = self.BuildJSONFromBasicSensorListToHost(sensors)
			try:
				self.SendWebSocket(payload)
			except:
				return False
		
		return True
