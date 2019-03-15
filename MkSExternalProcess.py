#!/usr/bin/python
import os
import sys
import json
if sys.version_info[0] < 3:
	import thread
else:
	import _thread
import threading
import time
import subprocess
from subprocess import call

class LocalPipe():
	def __init__(self, pipe):
		self.Pipe 				= pipe
		self.Buffer 			= ""
		self.LineBuffer 		= []
		self.BufferLength 		= 0
		self.ErrorBuffer 		= ""
		self.ErrorBufferLength 	= 0

	# Read from process and clear buffer after limit reached.
	def ReadToBufferWithLimit(self, limit):
		if (len(self.Buffer) > limit):
			self.ClearLineBuffer()
		self.LineBuffer.append(self.Pipe.stdout.readline())
		self.Pipe.poll()
	
	def ReadToBuffer(self):
		self.Buffer += self.Pipe.stdout.read()
		self.Pipe.poll()

	def GetBuffer(self):
		return self.Buffer

	def ClearBuffer(self):
		self.Buffer = ""
		
	def GetLineBuffer(self):
		return self.LineBuffer

	def ClearLineBuffer(self):
		self.LineBuffer = []
	
	def ClearErrorBuffer(self):
		self.ErrorBuffer = ""
	
	def ReadErrorBuffer(self):
		return self.Pipe.stderr.read()

	def IsPipeError(self):
		return self.Pipe.returncode is not None

	def GetError(self):
		return self.Pipe.returncode

class ExternalProcess():
	def __init__(self):
		# Locals
		self.Pipe 							= None
		self.PipeStdOutLength				= 0
		self.Status							= False
		# Callbacks
		self.OnProcessDataPipeCallback 		= None
		self.OnProcessErrorCallback 		= None
		self.OnProcessDoneCallback			= None
		# Lockers & Signals
		self.ExitEvent 						= False
		self.PipeLock 						= threading.Lock()

	def Worker(self):
		ErrorCounter = 0
		while(self.ExitEvent):
			self.PipeLock.acquire()
			if self.Pipe.Pipe.returncode is not None:
				self.ExitEvent = False
			try:
				# Read error.
				error = self.Pipe.ReadErrorBuffer()
				if error is not None:
					if len(error) > 0:
						self.Pipe.ClearErrorBuffer()
						if self.OnProcessErrorCallback is not None:
							self.OnProcessErrorCallback(error)
				
				# Read stdout.
				self.Pipe.ReadToBuffer()
				data = self.Pipe.GetBuffer()
				if data is not None:
					if self.PipeStdOutLength != len(data):
						self.PipeStdOutLength = len(data)
						if self.OnProcessDataPipeCallback is not None:
							self.OnProcessDataPipeCallback(data)
			except Exception as e:
				print ("[ExternalProcess]# (ERROR)", e)
				if ErrorCounter > 3:
					self.KillProcess()
				ErrorCounter += 1

			self.PipeLock.release()
			time.sleep(0.5)

		if self.OnProcessDoneCallback is not None:
			self.Pipe.ReadToBuffer()
			self.OnProcessDoneCallback(self.Pipe.GetBuffer())
		
		self.Status = False

	def CallProcess(self, process):
		self.ExitEvent 	= True
		self.Status 	= True
		proc = subprocess.Popen(process, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
		print ("[ExternalProcess]# Process started", process)
		self.Pipe = LocalPipe(proc)
		thread.start_new_thread(self.Worker, ())
	
	def KillProcess(self):
		self.ExitEvent = False
	
	def ClearProcessDataBuffer(self):
		self.PipeLock.acquire()
		self.Pipe.ClearBuffer()
		self.PipeLock.release()
	
	def GetStatus(self):
		return self.Status