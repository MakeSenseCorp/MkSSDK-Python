#!/usr/bin/python
import os
import sys

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