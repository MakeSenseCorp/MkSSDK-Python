import time

class TimeSchedulerThreadless():
	def __init__(self):
		self.ClassName		= "TimeSchedulerThreadless"
		self.TimeItems 		= {} # Key - Interval time

	def AddTimeItem(self, interval, callback):
		if interval not in self.TimeItems:
			self.TimeItems[interval] = []
		item = {
			"callback": callback,
			"ts": time.time()
		}
		self.TimeItems[interval].append(item)
	
	def RemoveTimeItem(self, interval, callback):
		if interval in self.TimeItems:
			callbacks = self.TimeItems[interval]
			for item in callbacks:
				if item["callback"] == callback:
					callbacks.remove(item)
					return True
		return False
	
	def Tick(self):
		now = time.time()
		for interval in self.TimeItems:
			callbacks = self.TimeItems[interval]
			for callback in callbacks:
				if now - callback["ts"] > interval:
					callback["callback"]()
					callback["ts"] = time.time()
