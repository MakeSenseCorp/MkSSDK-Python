#!/usr/bin/python
import os
import sys
import signal
import json
import time
import thread
import threading

class FileUpload():
	def __init__(self, name, size, chanks):
		self.Name 					= name
		self.Size 					= size
		self.LastFragmentNumber 	= chanks
		self.FragmentsCount			= 0
		self.Fragments 				= []
		self.Timestamp 				= 0
		self.CreationTimeStamp		= time.time()
		self.UploadDone				= False

		for i in range(1, self.LastFragmentNumber + 1):
			self.FragmentsCount += i

	def AddFragment(self, content, index, size):
		self.Fragments.append({ 
				'content': content,
				'index': index,
				'size': size
			})
		self.Timestamp = time.time()
		self.UploadDone = self.CheckFileUploaded()
		return self.UploadDone

	def CheckFileUploaded(self):
		counter = 0
		for item in self.Fragments:
			counter += item["index"]

		if counter == self.FragmentsCount:
			return True
		return False

	def GetFileRaw(self):
		data = []
		for index in range(1, self.LastFragmentNumber+1):
			for item in self.Fragments:
				if str(item["index"]) == str(index):
					data += item["content"]
					break
		return data, len(data)
	
	def CheckTimeout(self):
		delta_ts = self.Timestamp - self.CreationTimeStamp
		if delta_ts < 0:
			return True
		if delta_ts > 1000:
			return delta_ts
		
		return False

class Manager():
	def __init__(self, node_context):
		self.ClassName 						= "File Uploader"
		self.Ctx 							= node_context
		self.Locker							= threading.Lock()
		self.OnNewWorkItemEvent				= threading.Event() # Not in use
		self.ExitFlag						= False
		self.Uploaders						= {}
		self.UploaderKeys 					= []
		self.UploaderNextIndex				= 0

	def Worker(self):
		while(self.ExitFlag):
			# Logic
			self.Locker.acquire()
			uploader = self.GetNextUploader()
			if uploader is not None:
				if uploader.UploadDone is True:
					data, length = uploader.GetFileRaw()
					self.Ctx.File.SaveArray(os.path.join("packages",uploader.Name), data)
					self.Ctx.Node.EmitOnNodeChange({
						'event': "upload_progress",
						'data': {
							"status": "done",
							"precentage": "100%",
							"message": "Upload package done...",
							"file": uploader.Name
						}
					})
					self.RemoveCurrentUploader()
				elif uploader.CheckTimeout() is True:
					self.Ctx.Node.EmitOnNodeChange({
						'event': "upload_progress",
						'data': {
							"status": "timeout",
							"precentage": "100%",
							"message": "Upload package TIMEOUT error"
						}
					})
					self.RemoveCurrentUploader()
			self.Locker.release()
			time.sleep(1)

		# Clean all resurces before exit
		self.Uploaders = {}
	
	def Run(self):
		self.ExitFlag = True
		thread.start_new_thread(self.Worker, ())
	
	def Stop(self):
		self.ExitFlag = False
	
	def RemoveCurrentUploader(self):
		del self.Uploaders[self.UploaderKeys[self.UploaderNextIndex]]
		del self.UploaderKeys[self.UploaderNextIndex]
	
	def GetNextUploader(self):
		if len(self.UploaderKeys) == 0:
			self.UploaderNextIndex = 0
		else:
			if (len(self.UploaderKeys) - 1) == self.UploaderNextIndex:
				self.UploaderNextIndex = 0
			else:
				self.UploaderNextIndex += 1
		
		if len(self.UploaderKeys) > 0:
			return self.Uploaders[self.UploaderKeys[self.UploaderNextIndex]]
		else:
			return None
	
	def UpdateUploader(self, data):
		self.Locker.acquire()
		upload = self.Uploaders[data["file"]]

		content 	= data["content"]
		chunkSize 	= data["chunk_size"]
		index 		= data["chunk"]

		upload.AddFragment(content, index, chunkSize)
		self.Ctx.Node.EmitOnNodeChange({
			'event': "upload_progress",
			'data': {
				"status": "inprogress",
				"precentage": "{0}%".format(index/upload.LastFragmentNumber*100),
				"message": "Upload package ..."
			}
		})
		self.Locker.release()
	
	def AddNewUploader(self, data):
		self.Locker.acquire()
		size 		= data["size"]
		fileName	= data["file"]
		chunks 		= data["chunks"]
		content 	= data["content"]
		chunkSize 	= data["chunk_size"]
		index 		= data["chunk"]

		upload = FileUpload(fileName, size, chunks)
		upload.AddFragment(content, index, chunkSize)
		self.Uploaders[fileName] = upload
		self.UploaderKeys.append(fileName)
		self.Locker.release()