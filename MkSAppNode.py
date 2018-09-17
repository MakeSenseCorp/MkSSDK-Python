#!/usr/bin/python
import os
import sys
import thread
import threading
import socket

from mksdk import MkSAbstractNode

class ApplicationNode(AbstractNode):
	def __init__(self):
		AbstractNode.__init__(self)
		self.Commands 								= LocalNodeCommands()
		self.MasterNodesList						= []
		# Sates
		self.States = {
			'IDLE': 								self.StateIdle,
			'SEARCH_MASTERS':						self.StateSearchMasters,
			'WORKING': 								self.StateWorking
		}
		# Callbacks
		self.LocalServerDataArrivedCallback			= None
		self.OnMasterSearchCallback					= None
		# Flags
		self.SearchDontClean 						= False

		self.ChangeState("IDLE")

	def SearchForMasters(self):
		# Let user know master search started.
		if self.OnMasterSearchCallback is not None:
			self.OnMasterSearchCallback()
		# Clean master nodes list.
		if False == self.SearchDontClean:
			self.CleanMasterList()
		# Find all master nodes on the network.
		return self.FindMasters()

	def StateIdle(self):
		ret = self.SearchForMasters()
		if ret > 0:
			self.ChangeState("WORKING")
		else:
			self.ChangeState("SEARCH_MASTER")
			self.SearchDontClean = False

	def StateSearchMasters(self):
		if 0 == self.Ticker % 20:
			ret = self.SearchForMasters()
			if ret > 0:
				self.SwitchState("WORKING")

	def StateWorking(self):
		if 0 == self.Ticker % 40:
			# Check for master list.
			if not self.MasterNodesList:
				# Master list is empty
				self.ChangeState("SEARCH_MASTER")
				self.SearchDontClean = False
			else:
				# Serach for master and append if new master available.
				self.ChangeState("SEARCH_MASTER")
				self.SearchDontClean = True

	def NodeConnectHandler(self, conn, addr):
		pass

	def HandlerRouter(self, sock, req):
		if None is not self.LocalServerDataArrivedCallback:
			self.LocalServerDataArrivedCallback(data, sock)

	def NodeDisconnectHandler(self, sock):
		pass

	def NodeMasterAvailable(self, sock):
		# Get Master slave nodes.
		packet = self.CommandsGetLocalNodes()
		sock.send(packet)
	
	def CleanMasterList(self):
		for node in self.MasterNodesList:
			self.RemoveConnection(node.Socket)
		self.MasterNodesList = []
