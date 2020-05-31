import os
import sys
import json
import time
import hashlib

class SocketConnection():
	def __init__(self, ip, port, sock):
		self.IP 			= ip
		self.Port 			= port
		self.Socket 		= sock
		self.Timestamp  	= 0
		self.HASH 			= ""		# MD5 hash of ip and port
		self.Obj 			= {}
		# Set timestamp
		self.UpdateTimestamp()

		#self.PID 			= 0
		#self.ListenerPort	= 0			# This port will be assigned by Master
		#self.UUID 			= uuid
		#self.Type 			= node_type
		#self.Name 			= ""
		#self.LocalType 	= "UNKNOWN"
		#self.Status 		= "Stopped"
		#self.Info 			= None
	
	#def SetNodeName(self, name):
	#	self.Name = name
	
	def UpdateTimestamp(self):
		self.Timestamp = time.time()
	
	def GetHash(self):
		if self.HASH == "":
			self.HASH = hashlib.md5("{0}_{1}".format(self.IP,str(self.Port))).hexdigest()
		return self.HASH