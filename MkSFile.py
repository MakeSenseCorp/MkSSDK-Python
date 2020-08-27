#!/usr/bin/python
import os
import sys
import json

class File ():
	def __init__(self):
		self.Name = "Save/Load from file"

	def Save (self, filename, data):
		file = open(filename, "w")
		file.write(data)
		file.close()

	def SaveArray (self, filename, data):
		file = open(filename, "wb")
		array = bytearray(data)
		file.write(array)
		file.close()
	
	def AppendArray (self, filename, data):
		print(filename)
		file = open(filename, "a")
		array = bytearray(data)
		file.write(array)
		file.close()

	def Append (self, filename, data):
		file = open(filename, "a")
		file.write(data)
		file.close()

	def Load(self, filename):
		if os.path.isfile(filename) is True:
			file = open(filename, "r")
			data = file.read()
			file.close()
			return data
		return ""
	
	def SaveJSON(self, filename, data):
		db_file = open(filename, "w")
		json.dump(data, db_file, indent=2)
		db_file.close()
	
	def ListFilesInFolder(self, path):
		onlyfiles = [f for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))]
		return onlyfiles
	
	def ListFoldersInPath(self, path):
		onlyfiles = [f for f in os.listdir(path) if os.path.isdir(os.path.join(path, f))]
		return onlyfiles
	
	def ListAllInFolder(self, path):
		onlyfiles = [f for f in os.listdir(path)]
		return onlyfiles