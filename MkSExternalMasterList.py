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
import thread
import threading

class ExternalMasterList:
	def __init__(self, node):
		self.ClassName  = "ExternalMasterList"
		self.Context    = node
		self.Masters    = {}
		self.Working    = False
		self.Context.NodeRequestHandlers['get_master_nodes']  = self.OnGetMasterNodesRequestHandler
		self.Context.NodeResponseHandlers['get_master_nodes'] = self.OnGetMasterNodesResponseHandler

	def OnGetMasterNodesRequestHandler(self, sock, packet):
		connections = self.Context.GetConnectedNodes()

		nodes_list = []
		for key in connections:
			node = connections[key]
			nodes_list.append(node.Obj)

		return self.Context.BasicProtocol.BuildResponse(packet, { 
			'ip': self.Context.MyLocalIP,
			'nodes': nodes_list
		})

	def OnGetMasterNodesResponseHandler(self, sock, packet):
		payload = self.Context.BasicProtocol.GetPayloadFromJson(packet)
		self.Masters[payload["ip"]]["nodes"] = payload["nodes"]
		self.Masters[payload["ip"]]["ts"] 	 = time.time()

	def ConnectMasterWithRetries(self, ip):
		retry = 0
		while retry < 3:
			conn, status = self.Context.ConnectNode(ip, 16999)
			if status is True:
				return conn, status
			retry += 1
			time.sleep(2)
		
		return None, status

	def SendGetNodesList(self, master):
		if (time.time() - master["ts"] > 60):
			if master["conn"] is not None:
				message = self.Conext.BasicProtocol.BuildRequest("DIRECT", "MASTER", self.UUID, "get_master_nodes", {}, {})
				packet  = self.Conext.BasicProtocol.AppendMagic(message)
				self.Conext.SocketServer.Send(master["conn"].Socket, packet)
			master["ts"] = time.time()

	def Worker(self):
		self.Context.LogMSG("({classname})# Start worker".format(classname=self.ClassName),5)
		self.Working = True
		while (self.Working is True):
			try:
				for key in self.Masters:
					master = self.Masters[key]
					# self.Context.LogMSG("({classname})# Worker {0}".format(master,classname=self.ClassName),5)
					if master["status"] is False:
						# Connect to the master
						# Check if this socket already exist !!!!!!!
						self.Context.LogMSG("({classname})# ConnectMasterWithRetries [{0}]".format(master["ip"],classname=self.ClassName),5)
						conn, status = self.ConnectMasterWithRetries(master["ip"])
						if status is True:
							master["conn"] 	 = conn
							master["ts"] 	 = time.time() - 70
							master["status"] = True
							# Get nodes list
							self.SendGetNodesList(master)
							# Register master node
					else:
						# Get nodes list
						self.SendGetNodesList(master)
					time.sleep(1)
			except Exception as e:
				self.Context.LogException("[Worker] {0}".format(command),e,3)

	def Append(self, master):
		if master["ip"] in self.Masters or master["ip"] in self.Context.MyLocalIP:
			return
		
		master["status"] = False
		master["nodes"]  = []
		self.Masters[master["ip"]] = master
		self.Context.LogMSG("({classname})# Append {0}".format(master,classname=self.ClassName),5)

	def Remove(self, conn):
		del_key = None
		for key in self.Masters:
			master = self.Masters[key]
			if master["status"] is False:
				if master["conn"]["obj"]["uuid"] == conn["obj"]["uuid"]:
					del_key = key
		del self.Masters[del_key]

	def GetMasterConnection(self, uuid):
		for key in self.Masters:
			master = self.Masters[key]
			if master["status"] is True:
				for node in master["nodes"]:
					if node["uuid"] == uuid:
						return master["conn"]
		return None

	def Start(self):
		self.Context.LogMSG("({classname})# Start".format(classname=self.ClassName),5)
		thread.start_new_thread(self.Worker, ())

	def Stop(slef):
		self.Context.LogMSG("({classname})# Stop".format(classname=self.ClassName),5)
		self.Working = False
		# Disconnect and remove all connections
