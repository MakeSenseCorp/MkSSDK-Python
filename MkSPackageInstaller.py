#!/usr/bin/python
import os
import sys
import signal
import json
import time
import thread
import threading
import re
import zipfile

from mksdk import MkSQueue

class Manager():
	def __init__(self, node_context):
		self.ClassName 		= "Package Installer"
		self.Ctx 			= node_context
		self.Queue    		= MkSQueue.Manager(self.Callback)
		self.HandlerMethod	= {
			"install_zip": 	    self.InstallZIP_HandlerMethod,
			"install_git":	    self.InstallGIT_HandlerMethod,
			"uninstall":	    self.Uninstall_HandlerMethod,
		}
	
	def InstallZIP_HandlerMethod(self, data):
		path = os.path.join("packages",data["file"])
		self.Ctx.Node.LogMSG("({classname})# [InstallZIP_HandlerMethod] Unzip package".format(classname=self.ClassName),5)
		self.Ctx.Node.EmitOnNodeChange({
			'event': "install_progress",
			'data': {
				"status": "inprogress",
				"precentage": "10%",
				"message": "Unzip package ..."
			}
		})
		time.sleep(1)
		# Exctruct ZIP file to packages folder
		with zipfile.ZipFile(path, 'r') as file:
			file.extractall(path="packages")
		# Generate path to system.json
		configPath = os.path.join(path.replace(".zip",''),"system.json")
		configFile = self.GetConfigData(configPath)
		if (self.RegisterPackage(configFile) is True):
			self.Ctx.Node.LogMSG("({classname})# [InstallZIP_HandlerMethod] Package installed".format(classname=self.ClassName),5)
			self.Ctx.Node.EmitOnNodeChange({
				'event': "install_progress",
				'data': {
					"status": "done",
					"precentage": "100%",
					"message": "Package installed"
				}
			})

	def InstallGIT_HandlerMethod(self, data):
		# Generate path to system.json
		configPath = os.path.join(self.Ctx.Node.MKSPath,"nodes",data["file"],"system.json")
		configFile = self.GetConfigData(configPath)
		if (self.RegisterPackage(configFile) is True):
			self.Ctx.Node.EmitOnNodeChange({
				'event': "install_progress",
				'data': {
					"status": "done",
					"precentage": "100%",
					"message": "Package installed"
				}
			})

	def Uninstall_HandlerMethod(self, data):
		uuid = data["uuid"]
		self.Ctx.Node.EmitOnNodeChange({
			'event': "uninstall_progress",
			'data': {
				"status": "inprogress",
				"precentage": "10%",
				"message": "Find package"
			}
		})
		time.sleep(1)
		nodes = self.Ctx.InstalledNodesDB["installed_nodes"]
		for node in nodes:
			if node["uuid"] == uuid:
				nodes.remove(node)
				break
		
		self.Ctx.Node.EmitOnNodeChange({
			'event': "uninstall_progress",
			'data': {
				"status": "inprogress",
				"precentage": "40%",
				"message": "Remove package from nodes.json"
			}
		})
		time.sleep(1)
		self.Ctx.InstalledNodesDB["installed_nodes"] = nodes
		# Save new switch to database
		self.Ctx.File.SaveJSON(os.path.join(self.Ctx.Node.MKSPath,"nodes.json"), self.Ctx.InstalledNodesDB)
		self.Ctx.Node.EmitOnNodeChange({
			'event': "uninstall_progress",
			'data': {
				"status": "inprogress",
				"precentage": "90%",
				"message": "Remove package from Gateway DB"
			}
		})
		time.sleep(1)

		message = self.Ctx.Node.Network.BasicProtocol.BuildRequest("MASTER", "GATEWAY", self.Ctx.Node.UUID, "node_uninstall", { 
			'node': {
				"uuid":	uuid
			} 
		}, {})
		self.Ctx.Node.SendPacketGateway(message)

		self.Ctx.Node.EmitOnNodeChange({
			'event': "uninstall_progress",
			'data': {
				"status": "done",
				"precentage": "100%",
				"message": "Package removed"
			}
		})

	def GetConfigData(self, path):
		self.Ctx.Node.LogMSG("({classname})# [InstallZIP_HandlerMethod] Loading system.json".format(classname=self.ClassName),5)
		self.Ctx.Node.EmitOnNodeChange({
			'event': "install_progress",
			'data': {
				"status": "inprogress",
				"precentage": "30%",
				"message": "Load system.json ..."
			}
		})
		time.sleep(1)
		configFileStr = self.Ctx.File.Load(path)
		return json.loads(configFileStr)
	
	def RegisterPackage(self, config_file):
		uuid  = config_file["node"]["info"]["uuid"]
		name  = config_file["node"]["info"]["name"]
		ntype = config_file["node"]["info"]["type"]

		self.Ctx.Node.LogMSG("({classname})# [InstallZIP_HandlerMethod] Register package in node.json".format(classname=self.ClassName),5)
		self.Ctx.Node.EmitOnNodeChange({
			'event': "install_progress",
			'data': {
				"status": "inprogress",
				"precentage": "40%",
				"message": "Register Node ({0}) ...".format(uuid)
			}
		})
		time.sleep(1)

		nodes = self.Ctx.InstalledNodesDB["installed_nodes"]
		for node in nodes:
			if node["uuid"] == uuid:
				self.Ctx.Node.LogMSG("({classname})# [Request_InstallHandler] ERROR - Node installed".format(classname=self.ClassName),5)
				self.Ctx.Node.EmitOnNodeChange({
					'event': "install_progress",
					'data': {
						"status": "error",
						"precentage": "100%",
						"message": "Package already installed"
					}
				})
				return False

		# Update node.json
		nodes.append({
			"enabled": 0, 
			"type": ntype, 
			"name": name, 
			"uuid": uuid
		})
		self.Ctx.InstalledNodesDB["installed_nodes"] = nodes
		# Save new switch to database
		self.Ctx.File.SaveJSON(os.path.join(self.Ctx.Node.MKSPath,"nodes.json"), self.Ctx.InstalledNodesDB)

		self.Ctx.Node.LogMSG("({classname})# [InstallZIP_HandlerMethod] Register package in Gateway".format(classname=self.ClassName),5)
		self.Ctx.Node.EmitOnNodeChange({
			'event': "install_progress",
			'data': {
				"status": "inprogress",
				"precentage": "80%",
				"message": "Register ({0}) in Gateway ...".format(uuid)
			}
		})
		time.sleep(1)
		message = self.Ctx.Node.Network.BasicProtocol.BuildRequest("MASTER", "GATEWAY", self.Ctx.Node.UUID, "node_install", { 
			'node': {
				"uuid":					uuid,
				"type":					ntype,
				"user_id": 				1,	# TODO - Replace
				"is_valid": 			1,	# TODO - Replace
				"created_timestamp": 	1,
				"last_used_timestamp": 	1,
				"name": 				name
			} 
		}, {})
		self.Ctx.Node.SendPacketGateway(message)
		return True

	def Callback(self, item):
		self.HandlerMethod[item["method"]](item["data"])
	
	def Run(self):
		self.Queue.Start()
	
	def Stop(self):
		self.Queue.Stop()
	
	def AddWorkItem(self, item):
		if self.Queue is not None:
			self.Queue.QueueItem(item)
