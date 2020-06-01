'''
def InitiateLocalServer(self, port):
    if self.IsLocalUIEnabled is True:
        self.UI 			= MkSLocalWebServer.WebInterface("Context", port)
        self.LocalWebPort	= port
        # Data for the pages.
        jsonUIData 	= {
            'ip': str(self.MyLocalIP),
            'port': str(port),
            'uuid': str(self.UUID)
        }
        data = json.dumps(jsonUIData)
        # UI Pages
        self.UI.AddEndpoint("/", 			"index", 		None, 		data)
        self.UI.AddEndpoint("/nodes", 		"nodes", 		None, 		data)
        self.UI.AddEndpoint("/config", 		"config", 		None, 		data)
        self.UI.AddEndpoint("/app", 		"app", 			None, 		data)
        self.UI.AddEndpoint("/mobile", 		"mobile", 		None, 		data)
        self.UI.AddEndpoint("/mobile/app", 	"mobile/app", 	None, 		data)
        # UI RestAPI
        self.UI.AddEndpoint("/test/<key>", 						"test", 						self.TestWithKeyHandler)
        self.UI.AddEndpoint("/get/socket_list/<key>", 			"get_socket_list", 				self.GetConnectedSocketsListHandler)

def AppendFaceRestTable(self, endpoint=None, endpoint_name=None, handler=None, args=None, method=['GET']):
    if self.IsLocalUIEnabled is True:
        self.UI.AddEndpoint(endpoint, endpoint_name, handler, args, method)

def LocalWSDisconnectedHandler(self, ws_id):
    self.UnregisterLocalWS(ws_id)

def LocalWSDataArrivedHandler(self, ws, data):
    # print("({classname})# (WS) {0}".format(data,classname=self.ClassName))
    try:
        packet 		= json.loads(data)
        if ("HANDSHAKE" == self.BasicProtocol.GetMessageTypeFromJson(packet)):
            return
        
        command 	= self.BasicProtocol.GetCommandFromJson(packet)
        direction 	= self.BasicProtocol.GetDirectionFromJson(packet)
        destination = self.BasicProtocol.GetDestinationFromJson(packet)
        source 		= self.BasicProtocol.GetSourceFromJson(packet)

        packet["additional"]["client_type"] = "local_ws"

        self.Logger.Log("({classname})# WS LOCAL [{direction}] {source} -> {dest} [{cmd}]".format(classname=self.ClassName,
                    direction=direction,
                    source=source,
                    dest=destination,
                    cmd=command))

        if direction in "request":
            if command in self.NodeRequestHandlers.keys():
                message = self.NodeRequestHandlers[command](ws, packet)
                ws.send(message)
            else:
                # This command belongs to the application level
                if self.OnApplicationRequestCallback is not None:
                    message = self.OnApplicationRequestCallback(ws, packet)
                    ws.send(message)
        elif direction in "response":
            if command in self.NodeResponseHandlers.keys():
                self.NodeResponseHandlers[command](ws, packet)
            else:
                # This command belongs to the application level
                if self.OnApplicationResponseCallback is not None:
                    self.OnApplicationResponseCallback(ws, packet)
        else:
            pass
    except Exception as e:
        self.Logger.Log("({classname})# ERROR - [LocalWSDataArrivedHandler]\n(EXEPTION)# {error}\n{data}".format(error=str(e),data=data,classname=self.ClassName))

# Used by slave (mostely) toy init local UI
def PreUILoaderHandler(self):
    print ("({classname})# PreUILoaderHandler ...".format(classname=self.ClassName))
    port = 8000 + (self.ServerAdderss[1] - 10000)
    self.InitiateLocalServer(port)
    # UI RestAPI
    self.UI.AddEndpoint("/get/node_widget/<key>",		"get_node_widget",	self.GetNodeWidgetHandler)
    self.UI.AddEndpoint("/get/node_config/<key>",		"get_node_config",	self.GetNodeConfigHandler)

#if self.IsLocalUIEnabled is True:
#	# Run preloader for UI interface
#	if self.UI is None:
#		self.Logger.Log("({classname})# Executing UI preloader (Only valid for local UI aka Webface)".format(classname=self.ClassName))
#		self.PreUILoaderHandler()

# Run UI thread
#if self.IsLocalUIEnabled is True:
#	if self.UI is None:
#		self.Logger.Log("({classname})# Local UI(Webface) is not set ... (NULL)".format(classname=self.ClassName))
#	else:
#		self.Logger.Log("({classname})# Running local UI(Webface)".format(classname=self.ClassName))
#		self.UI.Run()

if self.IsLocalUIEnabled is True:
    # Import Local WebSocket objects
    from mksdk import MkSLocalWebServer
    from mksdk import MkSLocalWS
    self.LocalWSManager = MkSLocalWS.WSManager
    # Register callbacks
    self.LocalWSManager.OnDataArrivedEvent  = self.LocalWSDataArrivedHandler
    self.LocalWSManager.OnWSDisconnected 	= self.LocalWSDisconnectedHandler

# Called after user callback
if self.IsLocalUIEnabled is True:
    # This check is for client nodes
    if (self.Type not in [1, 2]):
        if self.LocalWSManager is not None:
            if self.LocalWSManager.IsServerRunnig() is False and self.LocalMasterConnection is None:
                self.Logger.Log("({classname})# Exiting main thread ... ({0}, {1}) ...".format(self.LocalWSManager.IsServerRunnig(), self.LocalMasterConnection.Socket, classname=self.ClassName))
                self.Exit("Exiting main thread")

def State_StartListener(self):
    self.ServerAdderss = ('', self.SlaveListenerPort)
    status = self.TryStartListener()
    if status is True:
        self.IsListenerEnabled = True
        if self.IsLocalUIEnabled is True:
            self.LocalWSManager.RunServer()
'''