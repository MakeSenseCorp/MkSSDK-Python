#!/usr/bin/python
import os
import sys
import thread
import threading
import socket

from mksdk import MkSAbstractNode

class MasterNode(AbstractNode):
	def __init__(self):
		AbstractNode.__init__(self)
		# Members
		self.PortsForClients				= [1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32]
		self.MasterHostName					= socket.gethostname()
		self.MasterVersion					= "1.0.1"
		self.PackagesList					= ["Gateway","LinuxTerminal","USBManager"] # Default Master capabilities.
		self.LocalSlaveList					= [] # Used ONLY by Master.
		# Sates
		self.States = {
			'IDLE': 						self.StateIdle,
			'WORKING': 						self.StateWorking
		}
		# Handlers
		self.MasterNodeHandlers				= {
			'get_port': 					self.GetPortHandler,
			'get_local_nodes': 				self.GetLocalNodesHandler,
			'get_master_info':				self.GetMasterInfoHandler
		}

		self.ChangeState("IDLE")

	def GetPortHandler(self, sock):
		pass

	def GetLocalNodesHandler(self):
		pass

	def GetMasterInfoHandler(self):
		pass

	def HandlerRouter(self, sock, data):
		pass
