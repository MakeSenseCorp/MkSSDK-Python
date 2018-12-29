#!/usr/bin/python
import os
import sys
import time
import thread
import threading
import subprocess

class ShellExecutor():
	def __init__(self):
		self.SudoSocket = None
		self.IsRunning 	= False
		# self.Pipe 		= subprocess.Popen("", shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE)

	def Run(self):
		self.IsRunning = True
		thread.start_new_thread(self.Worker, ())

	def Stop(self):
		pass
		#self.Pipe.stdin.write("exit")
		#self.Pipe.stdin.flush()

	def Worker(self):
		while self.IsRunning:
			pass

	def ConnectSudoService(self):
		pass

	def DisconnectSudoService(self):
		pass

	def ExecuteCommand(self, command):
		#print "ExecuteCommand ENTER"
		#self.Pipe.stdin.write(command)
		#print "D_1"
		#self.Pipe.stdin.flush()
		#print "D_2"
		#data = self.Pipe.stdout.read()
		#print "ExecuteCommand EXIT"
		#return data
		proc = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE)
		return proc.stdout.read()