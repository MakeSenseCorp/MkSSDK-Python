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
		while retry < 3:
			time.sleep(2)
			conn, status = self.Context.ConnectNode(ip, 16999)
			if status is True:
				return conn, status
			retry += 1
		
		return None, status

	def SendGetNodesList(self, master):
		if (time.time() - master["ts"] > 60):
			if master["conn"] is not None:
				message = self.Conext.BasicProtocol.BuildRequest("DIRECT", "MASTER", self.UUID, "get_master_nodes", {}, {})
				packet  = self.Conext.BasicProtocol.AppendMagic(message)
				self.Conext.SocketServer.Send(master["conn"].Socket, packet)
			master["ts"] = time.time()

	def Worker(self):
		while(self.Working is True):
			for key in self.Masters:
				master = self.Masters[key]
				if master["status"] is False:
					# Connect to the master
					# Check if this socket already exist !!!!!!!
					conn, status = self.ConnectMasterWithRetries(master["ip"])
					if status is True:
						master["conn"] = conn
						master["ts"] = time.time()
						# Get nodes list
						self.SendGetNodesList(conn)
						# Register master node
				else:
					# Get nodes list
					self.SendGetNodesList(master["conn"])
				time.sleep(1)

	def Append(self, master):
		if master["ip"] in self.Masters:
			return
		
		master["status"] = False
		master["nodes"]  = []
		self.Masters[master["ip"]] = master

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
		self.Working = True

	def Stop(slef):
		self.Working = False
		# Disconnect and remove all connections
