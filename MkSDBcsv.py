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
from datetime import datetime
import Queue

from mksdk import MkSFile

class Database():
	def __init__(self):
		self.ClassName 				= "Database"
		self.ThreadRunning 			= False
		self.CurrentFolderPath      = ""
		self.QueueLock      	    = threading.Lock()
		self.Orders      			= Queue.Queue()
		# Events
		
		# Create file system for storing videos
		if not os.path.exists("csv_db"):
			os.makedirs("csv_db")
		
		self.GenrateFolder()
		self.RunServer()
	
	def GenrateFolder(self):
		now = datetime.now()
		
		if not os.path.exists(os.path.join("csv_db", str(now.year))):
			os.makedirs(os.path.join("csv_db", str(now.year)))
		
		if not os.path.exists(os.path.join("csv_db", str(now.year), str(now.month))):
			os.makedirs(os.path.join("csv_db", str(now.year), str(now.month)))
		
		if not os.path.exists(os.path.join("csv_db", str(now.year), str(now.month), str(now.day))):
			os.makedirs(os.path.join("csv_db", str(now.year), str(now.month), str(now.day)))
		
		self.CurrentFolderPath = os.path.join("csv_db", str(now.year), str(now.month), str(now.day))

	def Worker(self):
		try:
			file = MkSFile.File()
			self.ThreadRunning = True
			while self.ThreadRunning:
				item = self.Orders.get(block=True,timeout=None)
				file.Append(item["file"], item["data"])
				
				# Check if date was changed
				now = datetime.now()
				if self.CurrentFolderPath != os.path.join("csv_db", str(now.year), str(now.month), str(now.day)):
					self.GenrateFolder()
				
		except Exception as e:
			print ("({classname})# [ERROR] Stoping CSV DB worker ... {0}".format(str(e), classname=self.ClassName))
			self.ServerRunning = False
	
	def RunServer(self):
		if self.ThreadRunning is False:
			thread.start_new_thread(self.Worker, ())
	
	def WriteDB(self, key, values):
		self.QueueLock.acquire()
		# dt_object = datetime.fromtimestamp(timestamp)
		data_csv = str(time.time()) + ","
		for item in values:
			data_csv += str(item) + ","
		data_csv = data_csv[:-1] + "\n"
		
		self.Orders.put( {
			'file': os.path.join(self.CurrentFolderPath, key + ".csv"),
			'data': data_csv
		})
		self.QueueLock.release()

	def ReadDB(self, key, day):
		pass