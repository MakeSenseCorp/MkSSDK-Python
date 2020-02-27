#!/usr/bin/python
import os
import sys
import time
if sys.version_info[0] < 3:
	import thread
else:
	import _thread
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
		#self.Pipe.stdin.write(command)
		#self.Pipe.stdin.flush()
		#data = self.Pipe.stdout.read()
		#return data
		data = None
		try:
			proc = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE)
			data = proc.stdout.read()
		except Exception as e:
			print("ExecuteCommand Exception", e)
		return data