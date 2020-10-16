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

'''
1. No such device
2. [Errno 11] Resource temporarily unavailable
'''

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
		self.Sensetivity 				= 98
		self.UserFPS	 				= 1
		# Events
		self.OnFrameChangeCallback		= None
		self.OnCameraFailCallback		= None
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
		# Error Handling
		self.ErrorCount					= 0
		self.RebootCount				= 0
		self.LocalRebootRequired		= False

		self.InitCameraDriver()

	def SetHighDiff(self, value):
		self.ImP.SetHighDiff(value)
	
	def SetSecondsPerFrame(self, value):
		self.SecondsPerFrame = value
	
	def SetFPS(self, value):
		self.UserFPS = value
	
	def SetSensetivity(self, sensetivity):
		self.Sensetivity = sensetivity
	
	def GetFPS(self):
		return self.FPS
	
	def Pause(self):
		if self.CameraDriverValid is True:
			fcntl.ioctl(self.Device, v4l2.VIDIOC_STREAMOFF, self.BufferType)
			self.IsGetFrame = False
			time.sleep(1)
	
	def Resume(self):
		if self.CameraDriverValid is True:
			fcntl.ioctl(self.Device, v4l2.VIDIOC_STREAMON, self.BufferType)
			self.IsGetFrame = True
			time.sleep(1)
	
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
		time.sleep(1)

	def Frame(self):
		# Allocate new buffer
		#self.Buffer 			= v4l2.v4l2_buffer()
		#self.Buffer.type 		= v4l2.V4L2_BUF_TYPE_VIDEO_CAPTURE
		#self.Buffer.memory 	= v4l2.V4L2_MEMORY_MMAP
		frame = None
		try:
			# Needed for virtual FPS and UVC driver
			time.sleep(self.SecondsPerFrame)
			# Get image from the driver queue
			fcntl.ioctl(self.Device, v4l2.VIDIOC_DQBUF, self.Buffer)           
			# Read frame from memory maped object
			raw_frame 		= self.Memory.read(self.Buffer.length)
			# Convert to Image
			img_raw_Frame 	= Image.open(BytesIO(raw_frame))
			output 			= BytesIO()
			# Save as JPEG format
			img_raw_Frame.save(output, "JPEG", quality=25, optimize=True, progressive=True)
			frame 			= output.getvalue()
			# Set memory to zero offset
			self.Memory.seek(0)
			# Requeue the buffer
			fcntl.ioctl(self.Device, v4l2.VIDIOC_QBUF, self.Buffer)
			self.FrameCount += 1
		except Exception as e:
			print ("({classname})# Frame [ERROR] ({0})".format(e, classname=self.ClassName))
			self.ErrorCount += 1
			if "No such device" in e:
				self.CameraDriverValid = False
			else:
				if self.ErrorCount > 3:
					self.LocalRebootRequired = True
			return None, True

		return frame, False
	
	def SetState(self, state):
		self.State = state
	
	def GetState(self):
		return self.State
	
	def StartGettingFrames(self):
		self.IsGetFrame = True

	def StopGettingFrames(self):
		self.IsGetFrame = False

	def Start(self):
		self.WorkingStatusLock.acquire()
		if (self.IsCameraWorking is False):
			thread.start_new_thread(self.CameraThread, ())
		self.WorkingStatusLock.release()

	def Stop(self):
		self.WorkingStatusLock.acquire()
		if self.CameraDriverValid is True:
		    fcntl.ioctl(self.Device, v4l2.VIDIOC_STREAMOFF, self.BufferType)
		self.IsCameraWorking = False
		self.WorkingStatusLock.release()
	
	def Reboot(self):
		self.WorkingStatusLock.acquire()
		# Stop camera stream
		fcntl.ioctl(self.Device, v4l2.VIDIOC_STREAMOFF, self.BufferType)
		# Remove MMAP
		self.Memory.close()
		# Clode FD for this camera
		os.close(self.Device)
		# Init camera
		self.InitCameraDriver()
		self.LocalRebootRequired = False
		self.RebootCount += 1
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
		try:
			while self.IsCameraWorking is True:
				self.WorkingStatusLock.release()
				if self.LocalRebootRequired is True:
					self.Reboot()
					self.ErrorCount = 0

				if self.IsGetFrame is True:
					frame_cur, error = self.Frame()
					if (error is False):
						frame_dif = self.ImP.CompareJpegImages(frame_cur, frame_pre)
						frame_pre = frame_cur

						self.FPS = 1.0 / float(time.time()-ts)
						if frame_cur is not None:
							print("({classname})# [FRAME] ({0}) ({1}) ({dev}) (diff={diff}) (fps={fps}) (reboot_count={reboot_count})".format(	str(self.FrameCount),
																								str(len(frame_cur)),
																								diff=str(frame_dif),
																								fps=str(self.FPS),
																								dev=str(self.DevicePath),
																								reboot_count=str(self.RebootCount),
																								classname=self.ClassName))
							if self.Sensetivity > frame_dif:
								if self.OnFrameChangeCallback is not None:
									self.OnFrameChangeCallback({
										"device_path": self.DevicePath,
										"uid": self.UID,
										"user_fps": self.UserFPS,
										"fps": str(self.FPS),
										"sensetivity": self.Sensetivity
									}, frame_cur)
						ts = time.time()			
					else:
						print ("({classname})# Cannot fetch frame ... {0}".format(self.IsCameraWorking, classname=self.ClassName))
						if self.CameraDriverValid is False:
							# Remove MMAP
							self.Memory.close()
							# Clode FD for this camera
							os.close(self.Device)
							# Stop camera thread
							self.Stop()
							# Emit to user
							if self.OnCameraFailCallback is not None:
								self.OnCameraFailCallback(self.UID)
				else:
					time.sleep(1)
				self.WorkingStatusLock.acquire()
		except Exception as e:
			print ("({classname})# CameraThread [ERROR] {0}".format(e, classname=self.ClassName))
			# Emit to user
			if self.OnCameraFailCallback is not None:
				self.OnCameraFailCallback(self.UID)
		
		print ("({classname})# Exit camera thread {0}".format(self.UID, classname=self.ClassName))
