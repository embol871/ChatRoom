class ClientInfo:
    def __init__(self, nickname=None, ip=None, udp_port=None):
        self.nickname = nickname
        self.ip = ip
        self.udp_port = udp_port
        self.my_ip = None
        self.tcp_port = None
        self.server_socket = None
        self.udp_socket = None
        self.tcp_chat_socket = None
        self.running = False
        self.peer_list = {}
        self.active_chats = {}

    def __str__(self):
        return f"{self.nickname} ({self.my_ip}:{self.udp_port})"

    def to_message(self):
        return f"NEW {self.nickname} {self.my_ip} {self.udp_port}"

    @staticmethod
    def from_message(msg):
        _, nickname, ip, port = msg.split()
        return ClientInfo(nickname, ip, int(port))
