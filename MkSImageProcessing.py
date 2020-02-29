import numpy as np
from PIL import Image
from PIL import ImageFilter
from io import BytesIO

class MkSImageComperator():
	def __init__(self):
		self.ObjName 	= "ImageProcessing"
		self.HighDiff	= 5000 # MAX = 261120
	
	def SetHighDiff(self, value):
		self.HighDiff = value

	def CompareJpegImages(self, img_one, img_two):
		if (img_one is None or img_two is None):
			return 0
		
		try:
			emboss_img_one = Image.open(BytesIO(img_one)).filter(ImageFilter.EMBOSS)
			emboss_img_two = Image.open(BytesIO(img_two)).filter(ImageFilter.EMBOSS)

			im = [None, None] 								# to hold two arrays
			for i, f in enumerate([emboss_img_one, emboss_img_two]):
				# .filter(ImageFilter.GaussianBlur(radius=2))) # blur using PIL
				im[i] = (np.array(f
				.convert('L')            					# convert to grayscale using PIL
				.resize((32,32), resample=Image.BICUBIC)) 	# reduce size and smooth a bit using PIL
				).astype(np.int)   							# convert from unsigned bytes to signed int using numpy
			diff_precentage = (float(self.HighDiff - (np.abs(im[0] - im[1]).sum())) / self.HighDiff) * 100
			
			if (diff_precentage < 0):
				return 0
			
			return diff_precentage
		except Exception as e:
			print ("[MkSImageProcessing] Exception", e)
			return 0