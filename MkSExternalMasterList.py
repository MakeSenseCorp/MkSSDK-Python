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
		self.Context.LogMSG("({classname})# [OnGetMasterNodesRequestHandler]".format(classname=self.ClassName),5)
		connections = self.Context.GetConnectedNodes()

		nodes_list = []
		for key in connections:
			node = connections[key]
			nodes_list.append(node.Obj["uuid"])

		return self.Context.BasicProtocol.BuildResponse(packet, { 
			'ip': self.Context.MyLocalIP,
			'uuid': self.Context.UUID,
			'nodes': nodes_list
		})

	def OnGetMasterNodesResponseHandler(self, sock, packet):
		self.Context.LogMSG("({classname})# [OnGetMasterNodesResponseHandler]".format(classname=self.ClassName),5)
		payload = self.Context.BasicProtocol.GetPayloadFromJson(packet)
		master = self.Masters[payload["ip"]]
		master["nodes"] = payload["nodes"]
		master["ts"] 	= time.time()
		master["uuid"] 	= payload["uuid"]
		self.Masters[payload["ip"]] = master

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
			master["ts"] = time.time()
			if master["conn"] is not None:
				message = self.Context.BasicProtocol.BuildRequest("DIRECT", "MASTER", self.Context.UUID, "get_master_nodes", {}, {})
				packet  = self.Context.BasicProtocol.AppendMagic(message)
				self.Context.SocketServer.Send(master["conn"].Socket, packet)
			self.Context.LogMSG("({classname})# SendGetNodesList [{0}, {1}] <get_master_nodes>".format(master["ip"],master["ts"],classname=self.ClassName),5)

	def Worker(self):
		self.Context.LogMSG("({classname})# Start worker".format(classname=self.ClassName),5)
		self.Working = True
		try:
			while (self.Working is True):
				if len(self.Masters) > 0:
					for key in self.Masters:
						master = self.Masters[key]
						if master["status"] is False:
							# Connect to the master
							# Check if this socket already exist !!!!!!!
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
				else:
					time.sleep(1)
		except Exception as e:
			self.Context.LogException("[Worker]",e,3)

	def Append(self, master):
		if master["ip"] in self.Masters or master["ip"] in self.Context.MyLocalIP:
			return
		
		master["status"] = False
		master["nodes"]  = []
		self.Masters[master["ip"]] = master
		self.Context.LogMSG("({classname})# Append {0}".format(master,classname=self.ClassName),5)

	def Remove(self, conn):
		self.Context.LogMSG("({classname})# Remove {0}".format(conn.Obj["uuid"], classname=self.ClassName),5)
		del_key = None
		for key in self.Masters:
			master = self.Masters[key]
			if master["status"] is True:
				if master["uuid"] == conn.Obj["uuid"]:
					del_key = key
		del self.Masters[del_key]

	def GetMasterConnection(self, uuid):
		for key in self.Masters:
			master = self.Masters[key]
			if master["status"] is True:
				if uuid in master["nodes"]:
					return master["conn"]
		return None

	def Start(self):
		self.Context.LogMSG("({classname})# Start".format(classname=self.ClassName),5)
		thread.start_new_thread(self.Worker, ())

	def Stop(slef):
		self.Context.LogMSG("({classname})# Stop".format(classname=self.ClassName),5)
		self.Working = False
		# Remove all connections
		self.Masters.clear()
