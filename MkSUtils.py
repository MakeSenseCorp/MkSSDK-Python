import socket
import os
import sys
import subprocess
import re
import array

class Utils():
	def __init__(self):
		pass
	
	def GetSystemIPs(self):
		proc = subprocess.Popen("ip a", shell=True, stdout=subprocess.PIPE)
		data = proc.stdout.read()
		data = re.sub(' +', ' ', data)
		cmdRows = data.split("\n")
		
		items 	= []
		ip 		= ""
		mac 	= ""
		subnet 	= ""
		
		for row in cmdRows[:-1]:
			cols = row.split(" ")
			if (cols[0] != ""):
				# Start of new interface
				if (cols[0] != "1:"):
					# Not first interface
					items.append([ip, mac])
					ip = ""
					mac = ""
			if ("link/ether" in cols[1]):
				mac = cols[2]
			if ("inet" == cols[1]):
				net = cols[2].split('/')
				ip = net[0]
				subnet = net[1]
		items.append([ip, mac])	
		return items

if os.name != "nt":
	import fcntl
	import struct

	def get_interface_ip(ifname):
		s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		return socket.inet_ntoa(fcntl.ioctl(s.fileno(), 0x8915, struct.pack('256s', ifname[:15]))[20:24])

def format_ip(addr):
	return str(ord(addr[0])) + '.' + \
		str(ord(addr[1])) + '.' + \
		str(ord(addr[2])) + '.' + \
		str(ord(addr[3]))

def all_interfaces():
	max_possible = 128  # arbitrary. raise if needed.
	bytes = max_possible * 32
	s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
	names = array.array('B', '\0' * bytes)
	outbytes = struct.unpack('iL', fcntl.ioctl(
		s.fileno(),
		0x8912,  # SIOCGIFCONF
		struct.pack('iL', bytes, names.buffer_info()[0])
	))[0]
	namestr = names.tostring()
	lst = []
	for i in range(0, outbytes, 40):
		name = namestr[i:i+16].split('\0', 1)[0]
		ip   = namestr[i+20:i+24]
		lst.append((name, ip))
	return lst

def GetIPList():
	ip_list = []
	ifs = all_interfaces()
	for i in ifs:
		ip_list.append({
			'iface':i[0],
			'ip': format_ip(i[1])
		})
	return ip_list

def GetLocalIP():
	ip = socket.gethostbyname(socket.gethostname())
	print(ip)
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
			"enp0s3",
			"wlp2s0"
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
	for i in range(1, 16):
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
	localIP = GetLocalIP()
	networkIP = '.'.join((localIP.split('.'))[:-1]) + '.'
	machines = ScanLocalNetworkForMasterPort(networkIP)
	return machines

def ReadFromSocket(ip, port, data, size=1024):
	sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	serverAddr = (ip, port)
	sock.settimeout(1)
	try:
		sock.connect(serverAddr)
		sock.sendall(data)
		response = sock.recv(size)
		sock.close()
		return response
	except:
		print ("ERROR")
		sock.close()
		return ""