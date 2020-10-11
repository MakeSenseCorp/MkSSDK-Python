import os
import sys
import time
import thread
import threading
import v4l2
import fcntl
import mmap
import base64
import gc

from PIL import Image
from io import BytesIO

from mksdk import MkSVideoRecording
from mksdk import MkSImageProcessing

GEncoder = MkSVideoRecording.VideoCreator()

class UVCCamera():
	def __init__(self, path):
		self.ClassName 					= "UVCCamera"
		self.ImP						= MkSImageProcessing.MkSImageComperator()
		self.Name 						= ""
		self.IsGetFrame 				= False
		self.IsCameraWorking 			= False
		self.SecondsPerFrame			= 0.4
		self.CurrentImageIndex 			= 0
		self.State 						= 0
		self.FrameCount  				= 0
		self.FPS 						= 0.0
		# Events
		self.OnFrameChangeHandler		= None
		self.OnMotionDetectedCallback	= None
		self.OnFaceDetectedCallback		= None
		# Synchronization
		self.WorkingStatusLock 			= threading.Lock()
		# Camera HW
		self.Device 					= None
		self.DevicePath 				= path
		self.Memory 					= None
		self.CameraDriverValid 			= True
		self.Buffer 					= None
		self.CameraDriverName 			= ""
		self.UID 						= ""

		self.InitCameraDriver()

	def SetHighDiff(self, value):
		self.ImP.SetHighDiff(value)
	
	def SetSecondsPerFrame(self, value):
		self.SecondsPerFrame = value
	
	def SetSensetivity(self, sensetivity):
		self.Sensetivity = sensetivity
	
	def GetFPS(self):
		return self.FPS
	
	def InitCameraDriver(self):
		self.Device = os.open(self.DevicePath, os.O_RDWR | os.O_NONBLOCK, 0)

		if self.Device is None:
			self.CameraDriverValid = False
			return
		
		capabilities = v4l2.v4l2_capability()
		fcntl.ioctl(self.Device, v4l2.VIDIOC_QUERYCAP, capabilities)

		if capabilities.capabilities & v4l2.V4L2_CAP_VIDEO_CAPTURE == 0:
			self.CameraDriverValid = False
			return
		# Set camera name
		self.CameraDriverName 	= capabilities.card.replace(" ", "")
		self.UID 				= self.CameraDriverName.replace("(","-").replace(")","-").replace(":","-").replace(" ","-")
		print ("({classname})# [INFO] {0} {1}".format(self.CameraDriverName, self.UID, classname=self.ClassName))

		# Setup video format (V4L2_PIX_FMT_MJPEG)
		capture_format 						= v4l2.v4l2_format()
		capture_format.type 				= v4l2.V4L2_BUF_TYPE_VIDEO_CAPTURE
		capture_format.fmt.pix.pixelformat 	= v4l2.V4L2_PIX_FMT_MJPEG
		capture_format.fmt.pix.width  		= 640
		capture_format.fmt.pix.height 		= 480
		fcntl.ioctl(self.Device, v4l2.VIDIOC_S_FMT, capture_format)

		# Tell the driver that we want some buffers
		req_buffer         = v4l2.v4l2_requestbuffers()
		req_buffer.type    = v4l2.V4L2_BUF_TYPE_VIDEO_CAPTURE
		req_buffer.memory  = v4l2.V4L2_MEMORY_MMAP
		req_buffer.count   = 1
		fcntl.ioctl(self.Device, v4l2.VIDIOC_REQBUFS, req_buffer)

		# Map driver to buffer
		self.Buffer         	= v4l2.v4l2_buffer()
		self.Buffer.type    	= v4l2.V4L2_BUF_TYPE_VIDEO_CAPTURE
		self.Buffer.memory  	= v4l2.V4L2_MEMORY_MMAP
		self.Buffer.index   	= 0
		fcntl.ioctl(self.Device, v4l2.VIDIOC_QUERYBUF, self.Buffer)
		self.Memory 			= mmap.mmap(self.Device, self.Buffer.length, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=self.Buffer.m.offset)
		# Queue the buffer for capture
		fcntl.ioctl(self.Device, v4l2.VIDIOC_QBUF, self.Buffer)

		# Start streaming
		self.BufferType = v4l2.v4l2_buf_type(v4l2.V4L2_BUF_TYPE_VIDEO_CAPTURE)
		fcntl.ioctl(self.Device, v4l2.VIDIOC_STREAMON, self.BufferType)
		time.sleep(5)

	def Frame(self):
		# Allocate new buffer
		self.Buffer 		= v4l2.v4l2_buffer()
		self.Buffer.type 	= v4l2.V4L2_BUF_TYPE_VIDEO_CAPTURE
		self.Buffer.memory 	= v4l2.V4L2_MEMORY_MMAP
		frame_garbed 		= False
		retry_counter		= 0
		frame 				= None
		try:
			while frame_garbed is False and retry_counter < 5:
				# Needed for virtual FPS and UVC driver
				time.sleep(self.SecondsPerFrame)
				# Get image from the driver queue
				try:
					fcntl.ioctl(self.Device, v4l2.VIDIOC_DQBUF, self.Buffer)
					frame_garbed = True
				except Exception as e:
				    retry_counter += 1
				    print ("({classname})# [ERROR] UVC driver cannot dqueue frame ... ({0})".format(retry_counter, classname=self.ClassName))
            
			if frame_garbed is False:
				# Reset uvc driver
				fcntl.ioctl(self.Device, v4l2.VIDIOC_STREAMOFF, self.BufferType)
				self.Memory.close()
				self.InitCameraDriver()
				return None, True
            
			# Read frame from memory maped object
			raw_frame 		= self.Memory.read(self.Buffer.length)
			img_raw_Frame 	= Image.open(BytesIO(raw_frame))
			output 			= BytesIO()
			img_raw_Frame.save(output, "JPEG", quality=15, optimize=True, progressive=True)
			print("DEBUG")
			frame 			= output.getvalue()

			self.Memory.seek(0)
			# Requeue the buffer
			fcntl.ioctl(self.Device, v4l2.VIDIOC_QBUF, self.Buffer)
			self.FrameCount +=  1
		except Exception as e:
			if "No such device" in e:
				self.CameraDriverValid = False
				self.StopCamera()
				return None, True
			else:
				print ("({classname})# {0}".format(e, classname=self.ClassName))

		return frame, False
	
	def SetState(self, state):
		self.State = state
	
	def GetState(self):
		return self.State
	
	def StartGettingFrames(self):
		self.IsGetFrame = True

	def StopGettingFrames(self):
		self.IsGetFrame = False

	def StartCamera(self):
		self.WorkingStatusLock.acquire()
		if (self.IsCameraWorking is False):
			thread.start_new_thread(self.CameraThread, ())
		self.WorkingStatusLock.release()

	def StopCamera(self):
		self.WorkingStatusLock.acquire()
		if self.CameraDriverValid is True:
		    fcntl.ioctl(self.Device, v4l2.VIDIOC_STREAMOFF, self.BufferType)
		self.IsCameraWorking = False
		self.WorkingStatusLock.release()

	def CameraThread(self):
		global GEncoder

		frame_cur 			 = None
		frame_pre 			 = None
		frame_dif 	 		 = 0
		ts 					 = time.time()

		self.IsCameraWorking = True
		self.IsGetFrame 	 = True
		
		self.WorkingStatusLock.acquire()
		while self.IsCameraWorking is True:
			self.WorkingStatusLock.release()
			if self.IsGetFrame is True:
				frame_cur, error = self.Frame()
				if (error is False):
					frame_dif = self.ImP.CompareJpegImages(frame_cur, frame_pre)
					frame_pre = frame_cur

					self.FPS = 1.0 / float(time.time()-ts)
					if frame_cur is not None:
						print("({classname})# [FRAME] ({0}) ({1}) ({dev}) (diff={diff}) (fps={fps})".format(	str(self.FrameCount),
																							str(len(frame_cur)),
																							diff=str(frame_dif),
																							fps=str(self.FPS),
																							dev=str(self.Device),
																							classname=self.ClassName))
					ts = time.time()			
				else:
					print ("({classname})# ERROR - Cannot fetch frame ...".format(classname=self.ClassName))
			else:
				time.sleep(1)
			self.WorkingStatusLock.acquire()
