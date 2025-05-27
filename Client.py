import socket
import threading
import json
import time
import random
from common import ClientInfo


class GroupChatClient:
    PROTOCOL_VERSION = "1.0"

    def __init__(self):
        self.info = ClientInfo()

    def start(self, server_host='localhost', server_port=8888):
        try:
            self.info.nickname = input("Nickname eingeben: ").strip()
            if not self.info.nickname:
                print("Ungültiger Nickname")
                return

            self.setup_udp_socket()
            self.setup_tcp_chat_socket()
            self.connect_to_server(server_host, server_port)
            self.register_with_server()

            self.info.running = True

            threading.Thread(target=self.handle_server_messages, daemon=True).start()
            threading.Thread(target=self.handle_udp_messages, daemon=True).start()
            threading.Thread(target=self.tcp_chat_server, daemon=True).start()

            self.TUI()

        except Exception as e:
            print(f"Client-Fehler: {e}")
        finally:
            self.stop()

    def setup_udp_socket(self):
        self.info.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.info.udp_socket.bind(('', 0))
        self.info.udp_port = self.info.udp_socket.getsockname()[1]
        print(f"UDP Socket auf Port {self.info.udp_port}")

    def setup_tcp_chat_socket(self):
        self.info.tcp_chat_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.info.tcp_chat_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.info.tcp_chat_socket.bind(('', 0))
        self.info.tcp_port = self.info.tcp_chat_socket.getsockname()[1]
        self.info.tcp_chat_socket.listen(5)
        print(f"TCP Chat Socket auf Port {self.info.tcp_port}")

    def connect_to_server(self, host, port):
        self.info.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.info.server_socket.connect((host, port))
        self.info.my_ip = self.info.server_socket.getsockname()[0]
        print(f"Mit Server verbunden: {host}:{port}")

    def register_with_server(self):
        register_data = {
            'nickname': self.info.nickname,
            'ip': self.info.my_ip,
            'udp_port': self.info.udp_port
        }
        self.send_to_server('REGISTER', register_data)

    def send_to_server(self, message_type, json_data=None, additional_headers=None):
        try:
            body = json.dumps(json_data) if json_data else ""
            headers = [
                f"{message_type} {self.PROTOCOL_VERSION}",
                f"Host: {self.info.my_ip}",
                f"Content-Length: {len(body.encode('utf-8'))}"
            ]
            if additional_headers:
                for key, value in additional_headers.items():
                    headers.append(f"{key}: {value}")
            message = "\r\n".join(headers) + "\r\n\r\n" + body
            self.info.server_socket.send(message.encode('utf-8'))
            return True
        except Exception as e:
            print(f"Fehler beim Senden an Server: {e}")
            return False

    def receive_from_server(self):
        try:
            header_lines = []
            current_line = b''

            while True:
                char = self.info.server_socket.recv(1)  # FEHLER: war self.server_socket
                if not char:
                    return None, None, None

                if char == b'\n':  # Bytestring endet mit \n
                    line = current_line.decode('utf-8').rstrip('\r')
                    if not line:  # Leere Zeile = Ende der Header
                        break
                    header_lines.append(line)
                    current_line = b''
                else:
                    current_line += char

            if not header_lines:
                return None, None, None

            # Erste Zeile parsen: MESSAGE_TYPE PROTOCOL_VERSION
            first_line = header_lines[0].split()
            if len(first_line) != 2:
                return None, None, None

            message_type = first_line[0]
            protocol_version = first_line[1]

            # Header parsen
            headers = {}
            for line in header_lines[1:]:
                if ':' in line:
                    key, value = line.split(':', 1)
                    headers[key.strip()] = value.strip()

            # Body lesen falls Content-Length vorhanden
            body = ""
            if 'Content-Length' in headers:
                content_length = int(headers['Content-Length'])
                if content_length > 0:
                    body_data = b''
                    while len(body_data) < content_length:
                        chunk = self.info.server_socket.recv(
                            content_length - len(body_data))  # FEHLER: war self.server_socket
                        if not chunk:
                            return None, None, None
                        body_data += chunk
                    body = body_data.decode('utf-8')

            return message_type, headers, body

        except Exception:
            return None, None, None

    def send_udp_header_message(self, message_type, json_data, target_ip, target_port, additional_headers=None):
        try:
            body = json.dumps(json_data) if json_data else ""

            headers = []
            headers.append(f"{message_type} {self.PROTOCOL_VERSION} ")
            headers.append(f"From: {self.info.nickname}")  # FEHLER: war self.info.nickname
            headers.append(f"Host: {self.info.my_ip}")  # FEHLER: war self.info.my_ip
            headers.append(f"Content-Length: {len(body.encode('utf-8'))}")

            if additional_headers:
                for key, value in additional_headers.items():
                    headers.append(f"{key}: {value}")

            message = "\r\n".join(headers) + "\r\n\r\n" + body

            self.info.udp_socket.sendto(message.encode('utf-8'),
                                        (target_ip, target_port))  # FEHLER: war self.info.udp_socket
            return True
        except Exception as e:
            print(f"Fehler beim UDP-Senden: {e}")
            return False

    def parse_udp_header_message(self, data):
        try:
            message_str = data.decode('utf-8')

            if '\r\n\r\n' not in message_str:
                return None, None, None

            header_part, body = message_str.split('\r\n\r\n', 1)
            header_lines = header_part.split('\r\n')

            if not header_lines:
                return None, None, None

            first_line = header_lines[0].split()
            if len(first_line) != 2:
                return None, None, None

            message_type = first_line[0]
            protocol_version = first_line[1]

            headers = {}
            for line in header_lines[1:]:
                if ':' in line:
                    key, value = line.split(':', 1)
                    headers[key.strip()] = value.strip()

            return message_type, headers, body

        except Exception as e:
            print(f"Fehler beim UDP-Parsen: {e}")
            return None, None, None

    def send_tcp_header_message(self, socket_obj, message_type, json_data=None, additional_headers=None):
        try:
            body = json.dumps(json_data) if json_data else ""

            headers = []
            headers.append(f"{message_type} {self.PROTOCOL_VERSION} ")
            headers.append(f"From: {self.info.nickname}")  # FEHLER: war self.info.nickname
            headers.append(f"Host: {self.info.my_ip}")  # FEHLER: war self.info.my_ip
            headers.append(f"Content-Length: {len(body.encode('utf-8'))}")

            if additional_headers:
                for key, value in additional_headers.items():
                    headers.append(f"{key}: {value}")

            message = "\r\n".join(headers) + "\r\n\r\n" + body

            socket_obj.send(message.encode('utf-8'))
            return True
        except Exception as e:
            print(f"Fehler beim TCP-Senden: {e}")
            return False

    def receive_tcp_header_message(self, socket_obj):
        try:
            header_lines = []
            current_line = b''

            while True:
                char = socket_obj.recv(1)
                if not char:
                    return None, None, None

                if char == b'\n':
                    line = current_line.decode('utf-8').rstrip('\r')
                    if not line:  # Leere Zeile = Ende der Header
                        break
                    header_lines.append(line)
                    current_line = b''
                else:
                    current_line += char

            if not header_lines:
                return None, None, None

            first_line = header_lines[0].split()
            if len(first_line) != 2:
                return None, None, None

            message_type = first_line[0]
            protocol_version = first_line[1]

            headers = {}
            for line in header_lines[1:]:
                if ':' in line:
                    key, value = line.split(':', 1)
                    headers[key.strip()] = value.strip()

            body = ""
            if 'Content-Length' in headers:
                content_length = int(headers['Content-Length'])
                if content_length > 0:
                    body_data = b''
                    while len(body_data) < content_length:
                        chunk = socket_obj.recv(content_length - len(body_data))
                        if not chunk:
                            return None, None, None
                        body_data += chunk
                    body = body_data.decode('utf-8')

            return message_type, headers, body

        except Exception:
            return None, None, None

    def handle_server_messages(self):
        while self.info.running:  # FEHLER: war self.info.running
            try:
                message_type, headers, body = (self.receive_from_server())
                if not message_type:
                    break

                json_data = json.loads(body) if body else {}

                if message_type == 'REGISTER_OK':
                    print(f"✓ {json_data.get('message')}")
                elif message_type == 'USER_LIST':
                    self.update_peer_list(json_data.get('users', []))
                elif message_type == 'USER_JOINED':
                    self.handle_user_joined(json_data)
                elif message_type == 'USER_LEFT':
                    self.handle_user_left(json_data)
                elif message_type == 'BROADCAST_MSG':
                    self.handle_broadcast_message(json_data)
                elif message_type == 'ERROR':
                    print(f"Server-Fehler: {json_data.get('message')}")
                elif message_type == 'BROADCAST_OK':
                    print("Broadcast gesendet")

            except Exception as e:
                if self.info.running:  # FEHLER: war self.info.running
                    print(f"Fehler bei Server-Kommunikation: {e}")
                break

    def update_peer_list(self, users):
        self.info.peer_list = {}
        for user in users:
            self.info.peer_list[user['nickname']] = {
                'ip': user['ip'],
                'udp_port': user['udp_port']
            }

    def handle_user_joined(self, json_data):
        nickname = json_data.get('nickname')
        self.info.peer_list[nickname] = {
            'ip': json_data.get('ip'),
            'udp_port': json_data.get('udp_port')
        }
        print(f"\n{nickname} ist beigetreten")

    def handle_user_left(self, json_data):
        nickname = json_data.get('nickname')
        if nickname in self.info.peer_list:
            del self.info.peer_list[nickname]
        if nickname in self.info.active_chats:
            self.info.active_chats[nickname].close()
            del self.info.active_chats[nickname]
        print(f"\n{nickname} hat den Chat verlassen")

    def handle_broadcast_message(self, json_data):
        sender = json_data.get('sender')
        msg = json_data.get('message')
        print(f"[BROADCAST] {sender}: {msg}")

    def handle_udp_messages(self):
        while self.info.running:
            try:
                data, addr = self.info.udp_socket.recvfrom(4096)  # Größerer Buffer für Header
                message_type, headers, body = self.parse_udp_header_message(data)

                if not message_type:
                    continue

                json_data = json.loads(body) if body else {}

                if message_type == 'CHAT_REQUEST':
                    self.handle_chat_request(headers, json_data, addr)
                elif message_type == 'CHAT_RESPONSE':
                    self.handle_chat_response(headers, json_data, addr)

            except Exception as e:
                if self.info.running:
                    print(f"UDP-Fehler: {e}")

    def handle_chat_request(self, headers, json_data, addr):
        initiator = headers.get('From')
        tcp_port = json_data.get('tcp_port')

        print(f"Chat-Anfrage von {initiator} erhalten")

        # Antwort senden
        response_data = {
            'accepted': True,
            'tcp_port': self.info.tcp_port
        }

        additional_headers = {
            'To': initiator,
            'Request-ID': headers.get('Request-ID', 'unknown')
        }

        self.send_udp_header_message(
            'CHAT_RESPONSE',
            response_data,
            addr[0],
            addr[1],
            additional_headers
        )

        # TCP-Verbindung zum Initiator aufbauen
        try:
            chat_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            chat_socket.connect((addr[0], tcp_port))

            hello_data = {
                'nickname': self.info.nickname
            }

            self.send_tcp_header_message(chat_socket, 'CHAT_HELLO', hello_data)

            self.info.active_chats[initiator] = chat_socket

            chat_thread = threading.Thread(
                target=self.handle_peer_chat,
                args=(chat_socket, initiator)
            )
            chat_thread.daemon = True
            chat_thread.start()

            print(f"Chat mit {initiator} erfolgreich gestartet")

        except Exception as e:
            print(f"Fehler beim Verbinden mit {initiator}: {e}")

    def handle_chat_response(self, headers, json_data, addr):
        responder = headers.get('From')
        accepted = json_data.get('accepted', False)

        if accepted:
            print(f"Chat-Anfrage von {responder} akzeptiert")
        else:
            print(f"Chat-Anfrage von {responder} abgelehnt")

    def tcp_chat_server(self):
        while self.info.running:
            try:
                client_socket, client_addr = self.info.tcp_chat_socket.accept()

                # Warten auf Identifikation (Header-basiert)
                try:
                    message_type, headers, body = self.receive_tcp_header_message(client_socket)

                    if message_type == 'CHAT_HELLO':
                        json_data = json.loads(body) if body else {}
                        peer_nickname = json_data.get('nickname')

                        if not peer_nickname:
                            peer_nickname = headers.get('From', 'Unknown')

                        self.info.active_chats[peer_nickname] = client_socket

                        chat_thread = threading.Thread(
                            target=self.handle_peer_chat,
                            args=(client_socket, peer_nickname)
                        )
                        chat_thread.daemon = True
                        chat_thread.start()

                        print(f"Chat mit {peer_nickname} erfolgreich gestartet")

                except Exception as e:
                    print(f"Fehler bei Chat-Identifikation: {e}")
                    client_socket.close()

            except Exception as e:
                if self.info.running:
                    print(f"TCP Chat Server Fehler: {e}")

    def handle_peer_chat(self, chat_socket, peer_nickname):
        try:
            while self.info.running:
                message_type, headers, body = self.receive_tcp_header_message(chat_socket)
                if not message_type:
                    break

                if message_type == 'CHAT_MSG':
                    json_data = json.loads(body) if body else {}
                    msg_text = json_data.get('message')
                    timestamp = headers.get('Timestamp', '')

                    if timestamp:
                        print(f"[{peer_nickname}] ({timestamp}): {msg_text}")
                    else:
                        print(f"[{peer_nickname}]: {msg_text}")
                elif message_type == 'CHAT_CLOSE':
                    print(f"Chat mit {peer_nickname} wurde von der Gegenseite beendet")
                    break

        except Exception as e:
            print(f"Chat-Fehler mit {peer_nickname}: {e}")
        finally:
            if peer_nickname in self.info.active_chats:
                del self.info.active_chats[peer_nickname]
            chat_socket.close()
            print(f"Chat mit {peer_nickname} beendet")

    def start_chat_with_peer(self, peer_nickname):
        if peer_nickname not in self.info.peer_list:
            print(f"Benutzer {peer_nickname} nicht gefunden")
            return

        if peer_nickname in self.info.active_chats:
            print(f"Chat mit {peer_nickname} bereits aktiv")
            return

        peer_info = self.info.peer_list[peer_nickname]

        chat_request_data = {
            'tcp_port': self.info.tcp_port
        }

        request_id = f"{self.info.nickname}_{int(time.time())}_{random.randint(1000, 9999)}"

        additional_headers = {
            'To': peer_nickname,
            'Request-ID': request_id
        }

        try:
            self.send_udp_header_message(
                'CHAT_REQUEST',
                chat_request_data,
                peer_info['ip'],
                peer_info['udp_port'],
                additional_headers
            )
            print(f"Chat-Anfrage an {peer_nickname} gesendet - warte auf Verbindung...")
        except Exception as e:
            print(f"Fehler beim Senden der Chat-Anfrage: {e}")

    def send_chat_message(self, peer_nickname, message):
        if peer_nickname not in self.info.active_chats:
            print(f"Kein aktiver Chat mit {peer_nickname}")
            return

        chat_msg_data = {
            'message': message
        }

        # Timestamp hinzufügen
        additional_headers = {
            'To': peer_nickname,
            'Timestamp': time.strftime('%H:%M:%S')
        }

        try:
            self.send_tcp_header_message(
                self.info.active_chats[peer_nickname],
                'CHAT_MSG',
                chat_msg_data,
                additional_headers
            )
        except Exception as e:
            print(f"Fehler beim Senden an {peer_nickname}: {e}")

    def close_chat_with_peer(self, peer_nickname):
        if peer_nickname not in self.info.active_chats:
            print(f"Kein aktiver Chat mit {peer_nickname}")
            return

        try:
            # CHAT_CLOSE Nachricht senden
            additional_headers = {
                'To': peer_nickname
            }

            self.send_tcp_header_message(
                self.info.active_chats[peer_nickname],
                'CHAT_CLOSE',
                None,
                additional_headers
            )

            self.info.active_chats[peer_nickname].close()
            del self.info.active_chats[peer_nickname]

            print(f"Chat mit {peer_nickname} beendet")

        except Exception as e:
            print(f"Fehler beim Beenden des Chats mit {peer_nickname}: {e}")

    def broadcast_message(self, message):
        broadcast_data = {
            'message': message
        }
        self.send_to_server('BROADCAST', broadcast_data)

    def TUI(self):
        print("*************** Peer Group Chat ***************")
        print("Wahlen Sie eine Aktion:")
        print(" 1                       - Benutzer auflisten")
        print(" 2 <Name>                - Chat mit Benutzer starten")
        print(" 3 <Name> + <Nachricht>  - Nachricht an Benutzer")
        print(" 4 <Name>                - Chat mit Benutzer beenden")
        print(" 5                       - Aktive Chats anzeigen")
        print(" 6 <Nachricht>           - Broadcast-Nachricht")
        print(" exit                    - Chat verlassen")
        print()

        while self.info.running:
            try:
                command = input("Aktion eingeben: \n").strip()
                if command:
                    self.handle_command(command)
                    if command.lower() == 'exit':
                        break
            except KeyboardInterrupt:
                print("\nBeende Client...")
                self.info.running = False
                break
            except EOFError:
                print("\nEingabe beendet, beende Client...")
                self.info.running = False
                break

    def handle_command(self, command):
        parts = command.split(' ', 2)
        cmd = parts[0].lower()

        if cmd == 'exit':
            self.info.running = False
        elif cmd == '1':
            print(f"Aktuelle Benutzer: {list(self.info.peer_list.keys())}")

        elif cmd == '2':
            if len(parts) < 2:
                print("Bitte geben Sie den Nickname des Benutzers ein")
                return
            self.start_chat_with_peer(parts[1])
        elif cmd == '3':
            if len(parts) < 3:
                print("Bitte geben Sie den Nickname des Benutzers und die Nachricht ein")
                return
            self.send_chat_message(parts[1], parts[2])
        elif cmd == '4':
            if len(parts) < 2:
                print("Bitte geben Sie den Nickname des Benutzers ein mit dem sie den chat beenden wollen")
                return
            self.close_chat_with_peer(parts[1])
        elif cmd == '5':
            if self.info.active_chats:
                print(f"Aktive Chats: {list(self.info.active_chats.keys())}")
            else:
                print("Keine aktiven Chats")
        elif cmd == '6':
            if len(parts) < 2:
                print("Bitte geben Sie eine Nachricht für den Broadcast ein")
                return
            self.broadcast_message(' '.join(parts[1:]))
        else:
            print("Unbekannter Befehl")

    def stop(self):
        self.info.running = False
        for socket_obj in [self.info.server_socket, self.info.udp_socket, self.info.tcp_chat_socket]:
            if socket_obj:
                try:
                    socket_obj.close()
                except:
                    pass

def main():
    client = GroupChatClient()

    # Server-Adresse abfragen
    server_host = input("Server-Host (Enter für localhost): ").strip()
    if not server_host:
        server_host = 'localhost'

    server_port = input("Server-Port (Enter für 8888): ").strip()
    if not server_port:
        server_port = 8888
    else:
        server_port = int(server_port)

    try:
        client.start(server_host, server_port)
    except KeyboardInterrupt:
        print("\nClient wird beendet...")
    finally:
        client.stop()
        print("\nClient beendet")


if __name__ == "__main__":
    main()