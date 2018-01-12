#!/usr/bin/python

class Device:
	def __init__(self, uuid, type, ostype, osversion, brandname):
		self.UUID  		= uuid
		self.Type  		= type
		self.OSType  	= ostype
		self.OSVersion 	= osversion
		self.BrandName 	= brandname

