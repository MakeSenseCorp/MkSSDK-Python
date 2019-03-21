#!/usr/bin/python
import os
import sys

class File ():
	def __init__(self):
		self.Name = "Save/Load from file"

	def SaveStateToFile (self, filename, data):
		file = open(filename, "w")
		file.write(data)
		file.close()

	def SaveArrayToFile (self, filename, data):
		file = open(filename, "wb")
		array = bytearray(data)
		file.write(array)
		file.close()

	def AppendToFile (self, filename, data):
		file = open(filename, "a")
		file.write(data)
		file.close()

	def LoadContent(self, filename):
		if os.path.isfile(filename) is True:
			file = open(filename, "r")
			data = file.read()
			file.close()
			return data
		return ""
	
	def LoadStateFromFile (self, filename):
		return self.LoadContent(filename)