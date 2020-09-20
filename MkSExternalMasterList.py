#!/usr/bin/python

'''
			Author
				Name:	Yevgeniy Kiveisha
				E-Mail:	yevgeniy.kiveisha@gmail.com

'''

import os
import sys
import json
import time
import threading

class ExternalMasterList:
	def __init__(self, node):
		self.ClassName  = "ExternalMasterList"
		self.Context    = node
		self.Masters    = {}
		self.Nodes      = {}
		self.Working    = False
		self.Context.NodeResponseHandlers['get_master_nodes'] = self.OnGetMasterNodesResponseHandler

	def OnGetMasterNodesResponseHandler(self, sock, packet):
		payload = self.Context.Node.BasicProtocol.GetPayloadFromJson(packet)
		nodes 	= payload["nodes"]

	def ConnectMasterWithRetries(self, ip):
		while retry < 3:
			time.sleep(2)
			conn, status = self.Context.Node.ConnectNode(ip, 16999)
			if status is True:
				return conn, status
			retry += 1
		
		return None, status

	def GetNodesList(self, master):
		if (time.time() - master["ts"] > 60):
			if master["conn"] is not None:
				message = self.Conext.Node.BasicProtocol.BuildRequest("DIRECT", "MASTER", self.Node.UUID, "get_master_nodes", {}, {})
				packet  = self.Conext.Node.BasicProtocol.AppendMagic(message)
				self.Conext.Node.SocketServer.Send(master["conn"].Socket, packet)
			master["ts"] = time.time()

	def Worker(self):
		while(self.Working is True):
			for master in self.Masters:
				if master["status"] is False:
					# Connect to the master
					# Check if this socket already exist !!!!!!!
					conn, status = self.ConnectMasterWithRetries(master["ip"])
					if status is True:
						master["conn"] = conn
						master["ts"] = time.time()
						# Get nodes list
						self.GetNodesList(conn)
						# Register master node
				else:
					# Get nodes list
					self.GetNodesList(master["conn"])
				time.sleep(1)

	def Append(self, master):
		if master["ip"] in self.Masters:
			return
		
		master["status"] = False
		self.Masters[master["ip"]] = master

	def Remove(self):
		# Remove nodes from the list
		# Delete master intance
		pass

	def GetNodesList(self):
		pass

	def Start(self):
		self.Working = True

	def Stop(slef):
		self.Working = False
