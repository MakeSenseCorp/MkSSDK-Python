#!/usr/bin/python
import os
import sys
import thread
import threading

class LocalHWAdaptor():
	def __init__(self):
		self.Device = None