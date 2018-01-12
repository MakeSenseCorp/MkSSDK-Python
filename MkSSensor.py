#!/usr/bin/python

class Sensor:
	Name  = ""
	ID	  = 0
	UUID  = 0
	Type  = 0
	Value = 0
	
	def __init__(self, id, type, local_id):
		self.ID   = local_id
		self.UUID = id[:-1] + str(local_id)
		self.Type = type
	
	def SetInterval(self, interval):
		self.UpdateInterval = interval
