import socket
import os
import sys
import subprocess

if os.name != "nt":
	import fcntl
	import struct

	def get_interface_ip(ifname):
		s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		return socket.inet_ntoa(fcntl.ioctl(s.fileno(), 0x8915, struct.pack('256s', ifname[:15]))[20:24])

def GetLocalIP():
	ip = socket.gethostbyname(socket.gethostname())
	if ip.startswith("127.") and os.name != "nt":
		interfaces = [
			"eth0",
			"eth1",
			"eth2",
			"wlan0",
			"wlan1",
			"wifi0",
			"ath0",
			"ath1",
			"ppp0",
			"enp0s3"
			]
		for ifname in interfaces:
			try:
				ip = get_interface_ip(ifname)
				break
			except IOError:
				pass
	return ip

def Ping(address):
	response = subprocess.call("ping -c 1 %s" % address,
			shell=True,
			stdout=open('/dev/null', 'w'),
			stderr=subprocess.STDOUT)
	# Check response
	if response == 0:
		return True
	else:
		return False

def ScanLocalNetwork(network_ip):
	machines = []
	for i in range(1, 32):
		IPAddress = network_ip + str(i)
		res = Ping(IPAddress)
		if True == res:
			machines.append(IPAddress)
	return machines

def ScanLocalNetworkForMasterPort(network_ip):
	machines = []
	for i in range(1, 32):
		IPAddress = network_ip + str(i)

		sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		serverAddr = (IPAddress, 16999)
		sock.settimeout(1)
		try:
			sock.connect(serverAddr)
			machines.append(IPAddress)
			sock.close()
		except:
			pass
	return machines

# Locking for Server Nodes and getting list of Nodes 
# attached to each machine.
def FindLocalMasterNodes():
	print "[Utils] Scanning for Master Nodes"
	localIP = GetLocalIP()
	networkIP = '.'.join((localIP.split('.'))[:-1]) + '.'
	machines = ScanLocalNetworkForMasterPort(networkIP)
	print "[Utils] Found machines,", machines
	return machines