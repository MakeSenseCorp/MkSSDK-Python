import os
import sys
import time
import thread
import threading
import subprocess
import gc
import Queue
from subprocess import call
from subprocess import Popen, PIPE
from PIL import Image
from io import BytesIO

import logging
logging.basicConfig(
	filename='app.log',
	level=logging.DEBUG,
    format='%(asctime)s.%(msecs)03d %(levelname)s %(module)s - %(funcName)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)

class VideoCreator():
	def __init__(self):
		self.ClassName 	= "VideoCreator"
		self.ObjName 	= "VideoCreator"
		self.Orders 	= Queue.Queue()
		self.IsRunning	= True
		self.FPS		= 8
		thread.start_new_thread(self.OrdersManagerThread, ())
	
	def SetFPS(self, fps):
		self.FPS = fps

	def AddOrder(self, order):
		self.Orders.put(order)
		self.IsRunning = True

	def OrdersManagerThread(self):
		# TODO - Put in TRY CATCH
		while (self.IsRunning is True):
			item = self.Orders.get(block=True,timeout=None)
			try:
				images = item["images"]
				file_path = "{0}/video_{1}.avi".format(item["path"], str(time.time()))
				print ("({classname})# Start video encoding ({0}) ...".format(file_path, classname=self.ClassName))
				recordingProcess = Popen(['ffmpeg', '-y', '-f', 'image2pipe', '-vcodec', 'mjpeg', '-r', str(self.FPS), '-i', '-', '-vcodec', 'mpeg4', '-qscale', '5', '-r', str(self.FPS), file_path], stdin=PIPE)
				for frame in images:
					image = Image.open(BytesIO(frame))
					image.save(recordingProcess.stdin, 'JPEG')
				recordingProcess.stdin.close()
				recordingProcess.wait()
				images = []
				item = None
				print ("({classname})# Start video encoding ({0}) ... DONE".format(file_path, classname=self.ClassName))
				gc.collect()
			except Exception as e:
				print ("[VideoCreator] Exception", e)
