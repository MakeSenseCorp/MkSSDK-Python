#!/usr/bin/python
import os
import sys
import json
if sys.version_info[0] < 3:
	import thread
else:
	import _thread
import threading
from flask import Flask, render_template, jsonify, Response, request
#from flask_cors import CORS

class EndpointAction(object):
	def __init__(self, page, args):
		self.Page = page + ".html"
		self.DataToJS = args

	def __call__(self, *args):
		return render_template(self.Page, data=self.DataToJS), 200, {
			'Cache-Control': 'no-cache, no-store, must-revalidate',
			'Pragma': 'no-cache',
			'Expires': '0',
			'Cache-Control': 'public, max-age=0'
		}

class WebInterface():
	def __init__(self, name, port):
		self.ClassName 	= "WebInterface"
		self.App 		= Flask(name)
		self.Port 		= port

		#self.App.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

		#CORS(self.App)
		#self.Log = logging.getLogger('werkzeug')
		#self.Log.disabled = True
		#self.App.logger.disabled = True

	def WebInterfaceWorker_Thread(self):
		print ("({classname})# Starting local webface on port ({port}) ...".format(classname=self.ClassName, port=str(self.Port)))
		self.App.run(host='0.0.0.0', port=self.Port)

	def Run(self):
		thread.start_new_thread(self.WebInterfaceWorker_Thread, ())

	def AddEndpoint(self, endpoint=None, endpoint_name=None, handler=None, args=None, method=['GET']):
		if handler is None:
			self.App.add_url_rule(endpoint, endpoint_name, EndpointAction(endpoint_name, args))
		else:
			self.App.add_url_rule(endpoint, endpoint_name, handler, methods=method)
