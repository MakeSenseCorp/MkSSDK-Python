import sys

OS_TYPE = ""

def InitializeGlobal():
	global OS_TYPE
	# ['linux', 'win32', 'cywin', 'darwin'] 
	OS_TYPE = sys.platform

InitializeGlobal()