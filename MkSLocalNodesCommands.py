#!/usr/bin/python
import os
import sys
import json

class LocalNodeCommands:
	def __init__(self):
		pass

	def GetHeader(self):
		return "MKS: Data\n"

	def GetFooter(self):
		return "\n"

	def GetLocalNodesRequest(self):
		packet = self.GetHeader()
		packet += "{\"command\":\"get_local_nodes\",\"direction\":\"request\"}"
		packet += self.GetFooter()

		return packet

	def GetLocalNodesResponse(self, nodes):
		packet = self.GetHeader()
		packet += "{\"command\":\"get_local_nodes\",\"direction\":\"response\",\"nodes\":[" + nodes + "]}"
		packet += self.GetFooter()

		return packet

	def GetPortRequest(self, uuid, node_type):
		packet = self.GetHeader()
		packet += "{\"command\":\"get_port\",\"direction\":\"request\",\"uuid\":\"" + uuid + "\",\"type\":" + str(node_type) + "}"
		packet += self.GetFooter()

		return packet

	def GetPortResponse(self, port):
		packet = self.GetHeader()
		packet += "{\"command\":\"get_port\",\"direction\":\"response\",\"port\":" + str(port) + "}"
		packet += self.GetFooter()

		return packet

	def GetMasterInfoRequest(self):
		packet = self.GetHeader()
		packet += "{\"command\":\"get_master_info\",\"direction\":\"request\"}"
		packet += self.GetFooter()

		return packet

	def GetMasterInfoResponse(self, uuid, host_name, nodes):
		packet = self.GetHeader()
		packet += "{\"command\":\"get_master_info\",\"direction\":\"response\",\"info\":{\"hostname\":\"" + str(host_name) + "\",\"uuid\":\"" + uuid + "\",\"nodes\":[" + nodes + "]}}"
		packet += self.GetFooter()

		return packet

	def MasterAppendNodeResponse(self, ip, port, uuid, node_type):
		packet = self.GetHeader()
		packet += "{\"command\":\"master_append_node\",\"direction\":\"response\",\"node\":{\"ip\":\"" + str(ip) + "\",\"port\":" + str(port) + ",\"uuid\":\"" + uuid + "\",\"type\":" + str(node_type) + "}}"
		packet += self.GetFooter()

		return packet

	def MasterRemoveNodeResponse(self, ip, port, uuid, node_type):
		packet = self.GetHeader()
		packet += "{\"command\":\"master_remove_node\",\"direction\":\"response\",\"node\":{\"ip\":\"" + str(ip) + "\",\"port\":" + str(port) + ",\"uuid\":\"" + uuid + "\",\"type\":" + str(node_type) + "}}"
		packet += self.GetFooter()

		return packet

	def SetSensorInfoRequest(self, uuid, sensors):
		packet = self.GetHeader()
		packet += "{\"command\":\"set_sensor_info\",\"direction\":\"request\",\"uuid\":\"" + uuid + "\",\"sensors\":[" + sensors + "]}"
		packet += self.GetFooter()

		return packet

	def GetSensorInfoRequest(self):
		packet = self.GetHeader()
		packet += "{\"command\":\"get_sensor_info\",\"direction\":\"request\"}"
		packet += self.GetFooter()

		return packet

	def GetSensorInfoResponse(self, uuid, sensors):
		packet = self.GetHeader()
		packet += "{\"command\":\"get_sensor_info\",\"direction\":\"response\",\"uuid\":\"" + uuid + "\",\"sensors\":[" + sensors + "]}"
		packet += self.GetFooter()

		return packet

	def ExitRequest(self):
		packet = self.GetHeader()
		packet += "{\"command\":\"exit\",\"direction\":\"request\"}"
		packet += self.GetFooter()

		return packet

	def ExitResponse(self, status):
		packet = self.GetHeader()
		packet += "{\"command\":\"exit\",\"direction\":\"response\",\"status\":\"" + str(status) + "\"}"
		packet += self.GetFooter()

		return packet

	def SendPingRequest(self, destination, source):
		packet = self.GetHeader()
		packet += json.dumps({	
								'command': 'ping',
								'direction': 'proxy_request',
								'payload': {
									'header': {
										'destination': str(destination),
										'source': str(source)
									},
									'data': {

									}
								}
							})
		packet += self.GetFooter()
		return packet

	def ProxyRequest(self, destination, source, command, data):
		packet = self.GetHeader()
		packet += json.dumps({	
								'command': command,
								'direction': 'proxy_request',
								'payload': {
									'header': {
										'destination': str(destination),
										'source': str(source)
									},
									'data': data
								}
							})
		packet += self.GetFooter()
		return packet

	def ProxyResponse(self, data, payload):
		packet = self.GetHeader()

		source 		= data["payload"]["header"]["source"]
		destination = data["payload"]["header"]["destination"]

		data["direction"] 							= 'proxy_response'
		data["payload"]["header"]["source"] 		= destination
		data["payload"]["header"]["destination"] 	= source
		data["payload"]["data"] 					= payload

		packet += json.dumps(data)
		packet += self.GetFooter()
		return packet

# =============== GetNodeInfo ==============================================================================================

	def GetNodeInfoRequest(self, destination, source, data, is_proxy):
		packet = self.GetHeader()

		if (True == is_proxy):
			direction = 'proxy_request'
		else:
			direction = 'request'

		packet += json.dumps({	
								'command': 'get_node_info',
								'direction': direction,
								'payload': {
									'header': {
										'destination': str(destination),
										'source': str(source)
									},
									'data': data
								}
							})
		packet += self.GetFooter()
		return packet

	def GetNodeInfoResponse(self, data):
		packet = self.GetHeader()

		if ("proxy" in data["direction"]):
			direction = 'proxy_response'
		else:
			direction = 'response'

		source 		= data["payload"]["header"]["source"]
		destination = data["payload"]["header"]["destination"]

		data["direction"] 							= direction
		data["payload"]["header"]["source"] 		= destination
		data["payload"]["header"]["destination"] 	= source

		packet += json.dumps(data)
		packet += self.GetFooter()
		return packet

# =============== GetNodeInfo ==============================================================================================

	def ProxyMessageRequest(self, destination, source, data):
		packet = self.GetHeader()
		packet += json.dumps({	
								'command': 'proxy_gateway',
								'direction': 'request',
								'payload': {
									'header': {
										'destination': str(destination),
										'source': str(source)
									},
									'data': data
								}
							})
		packet += self.GetFooter()

		return packet

	def ProxyMessageResponse(self, destination, source, data):
		packet = self.GetHeader()
		packet += json.dumps({	
								'command': 'proxy_gateway',
								'direction': 'response',
								'payload': {
									'header': {
										'destination': str(destination),
										'source': str(source)
									},
									'data': data
								}
							})
		packet += self.GetFooter()

		return packet
