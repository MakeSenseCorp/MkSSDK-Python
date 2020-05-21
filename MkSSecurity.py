#!/usr/bin/python
import os
import sys
import hashlib

class Security():
	def __init__(self):
		pass
	
	def GetMD5Hash(self, content):
		return hashlib.md5(content).hexdigest()
		# For Python 3+ hashlib.md5("whatever your string is".encode('utf-8')).hexdigest()