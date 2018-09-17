#!/usr/bin/python
import os
import sys
import thread
import threading
import socket

from mksdk import MkSAbstractNode

class SlaveNode(AbstractNode):
	def __init__(self):
		AbstractNode.__init__(self)
		self.MasterNodesList				= []
		self.SlaveListenerPort 				= 0
		# Sates
		self.States = {
			'IDLE': 						self.SlaveStateIdle,
			'CONNECT_MASTER':				self.SlaveStateConnectMaster,
			'CONNECTED': 					self.SlaveConnected,
			'START_LISTENER':				self.SlaveStartListener
		}
		# Handlers
		self.ServerNodeHandlers				= {
		}
		# Callbacks
		self.LocalServerDataArrivedCallback			= None

		self.ChangeState("IDLE")

	def SlaveStateIdle(self):
		self.ChangeState("CONNECT_MASTER")
		# Init state logic must be here.

	def CleanMasterList(self):
		# print "[DEBUG] CleanMasterList", len(self.MasterNodesList)
		for master in self.MasterNodesList:
			self.RemoveConnection(master[0])
		self.MasterNodesList = []

	def SlaveStateConnectMaster(self):
		if 0 == self.Ticker % 20:
			if self.OnMasterSearchCallback is not None:
				self.OnMasterSearchCallback()
			# Clean master nodes list.
			self.CleanMasterList()
			# Find all master nodes on the network.
			self.FindMasters()
			# masterIPPortList = MkSUtils.FindLocalMasterNodes()
			# for masterIpPort in masterIPPortList:
			#	sock, status = self.ConnectNodeSocket(masterIpPort)
			#	if True == status:
			#		self.MasterNodesList.append([sock, masterIpPort[0]])
			#	else:
			#		print "[Node Server] Could not connect"

			# Foreach master node need to send request of list nodes related to  master,
			# also if master is local than node need to ask for port.
			for master in self.MasterNodesList:
				# Find local master and get port port number.
				if self.MyLocalIP in master[1] and False == self.isPureSlave:
					self.SlaveState 	= "CONNECTED"
					self.MasterSocket 	= master[0]
					# This is node's master, thus send port request.
					self.MasterSocket.send("MKS: Data\n{\"command\":\"get_port\",\"direction\":\"request\",\"uuid\":\"" + self.UUID + "\",\"type\":" + str(self.Type) + "}\n")
					#self.MasterSocket.send("MKS: Data\n{\"command\":\"get_local_nodes\",\"direction\":\"request\",\"uuid\":\"" + self.UUID + "\",\"type\":" + str(self.Type) + "}\n")
				#else:
				#	master[0].send("MKS: Data\n{\"command\":\"get_local_nodes\",\"direction\":\"request\"}\n")
				#	if True == self.isPureSlave:
				#		self.SlaveState = "CONNECTED"
			#if len(self.MasterNodesList) > 0:
			#	if self.OnMasterFoundCallback is not None:
			#		self.OnMasterFoundCallback(self.MasterNodesList)
	
	def SlaveConnected(self):
		self.ChangeState("CONNECTED")
		# Check if slave has a port.
		if (0 == self.SlaveListenerPort and False == self.isPureSlave) or (0 == len(self.MasterNodesList) and True == self.isPureSlave):
			self.ChangeState("CONNECT_MASTER")

	def SlaveStartListener(self):
		status = self.TryStartListener()
		if True == status:
			self.IsListenerEnabled = True
			self.ChangeState("CONNECTED")

	def HandlerRouter(self, sock, data):
		if None is not self.LocalServerDataArrivedCallback:
			self.LocalServerDataArrivedCallback(data, sock)
