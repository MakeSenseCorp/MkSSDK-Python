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

	def AppendToFile (self, filename, data):
		file = open(filename, "a")
		file.write(data)
		file.close()

	def LoadContent(self, filename):
		if os.path.isfile(filename) == True:
			file = open(filename, "r")
			data = file.read()
			file.close()
			return data
		return ""
	
	def LoadStateFromFile (self, filename):
		return self.LoadContent(filename)