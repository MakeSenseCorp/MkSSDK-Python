#!/usr/bin/python
import os
import sys
import json
import time
import thread
import threading
import socket

from mksdk import MkSAbstractNode
from mksdk import MkSLocalNodesCommands

class ApplicationNode(MkSAbstractNode.AbstractNode):
	def __init__(self, master_ip_list):
		MkSAbstractNode.AbstractNode.__init__(self)
		self.Commands 								= MkSLocalNodesCommands.LocalNodeCommands()
		self.MasterStaticIPList 					= master_ip_list
		self.MasterNodesList						= []
		# Sates
		self.States = {
			'IDLE': 								self.StateIdle,
			'SEARCH_MASTERS':						self.StateSearchMasters,
			'WORKING': 								self.StateWorking
		}
		# Handlers
		self.ResponseHandlers	= {
			'get_local_nodes': 						self.GetLocalNodeResponseHandler,
			'get_master_info': 						self.GetMasterInfoResponseHandler,
			'master_append_node':					self.MasterAppendNodeResponseHandler,
			'master_remove_node':					self.MasterRemoveNodeResponseHandler,
			'get_sensor_info': 						self.GetSensorInfoResponseHandler,
			'undefined':							self.UndefindHandler
		}
		# Callbacks
		self.LocalServerDataArrivedCallback			= None
		self.OnGetLocalNodesResponeCallback 		= None
		self.OnGetMasterInfoResponseCallback		= None
		self.OnMasterAppendNodeResponseCallback		= None
		self.OnMasterRemoveNodeResponseCallback 	= None
		self.OnGetSensorInfoResponseCallback 		= None
		# Flags
		self.SearchDontClean 						= False
		self.MasterNodeLocatorRunning				= False
		self.IsListenerEnabled 						= False
		# Const
		self.SEARCH_MASTER_INTERVAL 				= 60

		self.ChangeState("IDLE")

	def GetLocalNodeResponseHandler(self, json_data):
		# Get connection and change local type
		if self.OnGetLocalNodesResponeCallback is not None:
			nodes = json_data['nodes']
			self.OnGetLocalNodesResponeCallback(nodes)

	def GetMasterInfoResponseHandler(self, data):
		# Get connection and change local type
		if self.OnGetMasterInfoResponseCallback is not None:
			self.OnGetMasterInfoResponseCallback(data)

	def MasterAppendNodeResponseHandler(self, json_data):
		# Get connection and change local type
		if self.OnMasterAppendNodeResponseCallback is not None:
			node = json_data['node']
			self.OnMasterAppendNodeResponseCallback(node)

	def MasterRemoveNodeResponseHandler(self, data):
		if self.OnMasterRemoveNodeResponseCallback is not None:
			self.OnMasterRemoveNodeResponseCallback(data)

	def GetSensorInfoResponseHandler(self, data):
		if self.OnGetSensorInfoResponseCallback is not None:
			self.OnGetSensorInfoResponseCallback(data)

	def UndefindHandler(self, data, sock):
		if None is not self.LocalServerDataArrivedCallback:
			self.LocalServerDataArrivedCallback(data, sock)

	def SearchForMasters(self):
		# Clean master nodes list.
		if False == self.SearchDontClean:
			self.CleanMasterList()
		# Find all master nodes on the network.
		return self.FindMasters()

	def StateIdle(self):
		if self.MasterStaticIPList is None:
			ret = self.SearchForMasters()
			if ret > 0:
				self.ChangeState("WORKING")
				thread.start_new_thread(self.MasterNodeLocator, ())
			else:
				self.ChangeState("SEARCH_MASTERS")
				self.SearchDontClean = False
		else:
			for ip in self.MasterStaticIPList:
				sock, status = self.ConnectMaster(ip)
				if status is True:
					self.NodeMasterAvailable(sock)
					if self.OnMasterFoundCallback is not None:
						self.OnMasterFoundCallback([sock, ip])
			self.ChangeState("WORKING")

	def StateSearchMasters(self):
		if 0 == self.Ticker % 20:
			if self.MasterStaticIPList is None:
				ret = self.SearchForMasters()
				if ret > 0:
					self.ChangeState("WORKING")
			else:
				for ip in self.MasterStaticIPList:
					sock, status = self.ConnectMaster(ip)
					if status is True:
						self.NodeMasterAvailable(sock)
						if self.OnMasterFoundCallback is not None:
							self.OnMasterFoundCallback([sock, ip])
				self.ChangeState("WORKING")

	def StateWorking(self):
		if 0 == self.Ticker % 40:
			# Check for master list.
			if not self.MasterNodesList:
				# Master list is empty
				self.ChangeState("SEARCH_MASTERS")
				self.SearchDontClean = False
				self.StopMasterNodeLocator()

			payload = self.Commands.GetLocalNodesRequest()
			for item in self.MasterNodesList:
				item.Socket.send(payload)

	def StartMasterNodeLocator(self):
		self.MasterNodeLocatorRunning = True

	def StopMasterNodeLocator(self):
		self.MasterNodeLocatorRunning = False

	def MasterNodeLocator(self):
		self.StartMasterNodeLocator()
		self.SearchDontClean = True
		while True == self.MasterNodeLocatorRunning:
			# Rest for several seconds.
			time.sleep(self.SEARCH_MASTER_INTERVAL)
			print "[Node] MasterNodeLocator WORKING"
			# Search network.
			self.SearchForMasters()

	def HandlerRouter(self, sock, data):
		jsonData 	= json.loads(data)
		command 	= jsonData['command']
		direction 	= jsonData['direction']

		if command in self.ResponseHandlers:
			if "response" == direction:
				self.ResponseHandlers[command](jsonData)

	def NodeDisconnectHandler(self, sock):
		# Check if disconneced connection is a master.
		for node in self.MasterNodesList:
			if sock == node.Socket:
				self.MasterNodesList.remove(node)
				if self.OnMasterDisconnectedCallback is not None:
					self.OnMasterDisconnectedCallback()

	def NodeMasterAvailable(self, sock):
		# Append new master to the list
		conn = self.GetConnection(sock)
		# TODO - Check if we don't have this connection already
		self.MasterNodesList.append(conn)
		# Get Master slave nodes.
		packet = self.Commands.GetLocalNodesRequest()
		sock.send(packet)
	
	def CleanMasterList(self):
		for node in self.MasterNodesList:
			self.RemoveConnection(node.Socket)
		self.MasterNodesList = []

	def GetMasters(self):
		return self.MasterNodesList

	def GetMasterNodes(self, ip):
		for node in self.MasterNodesList:
			if ip == node.IP:
				packet = self.Commands.GetLocalNodesRequest()
				node.Socket.send(packet)
				return

	def GetNodeByUUID(self, uuid):
		for conn in self.Connections:
			if conn.UUID == uuid:
				return conn
		return None
