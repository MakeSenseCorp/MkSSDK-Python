#!/usr/bin/python
import os
import sys
import json
import thread
import threading

from mksdk import MkSAbstractConnector

class LocalHWConnector(MkSAbstractConnector.AbstractConnector):
	def __init__(self, local_device):
		MkSAbstractConnector.AbstractConnector.__init__(self, local_device)
