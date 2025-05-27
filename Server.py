import socket
import threading
import json
import time
from common import ClientInfo


class GroupChatServer:
    PROTOCOL_VERSION = "1.0"

    def __init__(self, host='localhost', port=8888):
        self.host = host
        self.port = port
        self.clients = {}  # {client_socket: ClientInfo}
        self.server_socket = None
        self.running = False

    def start(self):
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(5)
            self.running = True

            print(f"Server gestartet auf {self.host}:{self.port}")

            while self.running:
                try:
                    client_socket, client_addr = self.server_socket.accept()
                    print(f"Neue Verbindung von {client_addr}")

                    client_thread = threading.Thread(
                        target=self.handle_client,
                        args=(client_socket,)
                    )
                    client_thread.daemon = True
                    client_thread.start()

                except Exception as e:
                    if self.running:
                        print(f"Fehler beim Akzeptieren von Verbindungen: {e}")

        except Exception as e:
            print(f"Server-Start-Fehler: {e}")
        finally:
            self.stop()

    def handle_client(self, client_socket):
        try:
            while self.running:
                message_type, headers, body = self.receive_message(client_socket)

                if not message_type:
                    break

                json_data = json.loads(body) if body else {}

                if message_type == 'REGISTER':
                    self.handle_register(client_socket, headers, json_data)
                elif message_type == 'UNREGISTER':
                    self.handle_unregister(client_socket)
                elif message_type == 'BROADCAST':
                    self.handle_broadcast(client_socket, json_data)
                elif message_type == 'GET_USERS':
                    self.handle_get_users(client_socket)
                else:
                    self.send_error(client_socket, f"Unbekannter Nachrichten typ: {message_type}")

        except Exception as e:
            print(f"Client-Handler-Fehler: {e}")
        finally:
            self.disconnect_client(client_socket)

    def send_message(self, client_socket, message_type, json_data=None, additional_headers=None):
        try:
            body = json.dumps(json_data) if json_data else ""
            headers = [
                f"{message_type} {self.PROTOCOL_VERSION}",
                f"Host: {self.host}",
                f"Content-Length: {len(body.encode('utf-8'))}"
            ]

            if additional_headers:
                for key, value in additional_headers.items():
                    headers.append(f"{key}: {value}")

            message = "\r\n".join(headers) + "\r\n\r\n" + body
            client_socket.send(message.encode('utf-8'))
            return True
        except Exception as e:
            print(f"Fehler beim Senden: {e}")
            return False

    def receive_message(self, client_socket):
        try:
            header_lines = []
            current_line = b''

            while True:
                char = client_socket.recv(1)
                if not char:
                    return None, None, None

                if char == b'\n':
                    line = current_line.decode('utf-8').rstrip('\r')
                    if not line:
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
                        chunk = client_socket.recv(content_length - len(body_data))
                        if not chunk:
                            return None, None, None
                        body_data += chunk
                    body = body_data.decode('utf-8')

            return message_type, headers, body

        except Exception:
            return None, None, None

    def handle_register(self, client_socket, headers, json_data):
        try:
            nickname = json_data.get('nickname')
            ip = headers.get('Host', json_data.get('ip'))
            udp_port = json_data.get('udp_port')

            if not nickname or not ip or not udp_port:
                self.send_error(client_socket, "Fehlende Eingabe")
                return

            if any(info.nickname == nickname for info in self.clients.values()):
                self.send_error(client_socket, "Nickname existiert bereits")
                return

            client_info = ClientInfo(nickname, ip, udp_port)
            client_info.server_socket = client_socket

            self.clients[client_socket] = client_info

            response_data = {'message': f'Erfolgreich registriert als {nickname}'}
            self.send_message(client_socket, 'REGISTER_OK', response_data)
            self.send_user_list(client_socket)

            self.broadcast_user_update('USER_JOINED', nickname, ip, udp_port, exclude=client_socket)
            print(f"Client {nickname} registriert von {ip}:{udp_port}")

        except Exception as e:
            self.send_error(client_socket, f"Registration fehlgeschlagen: {e}")

    def handle_unregister(self, client_socket):
        if client_socket in self.clients:
            client_info = self.clients[client_socket]
            nickname = client_info.nickname

            response_data = {
                'message': f'Erfolgreich abgemeldet {nickname}'
            }
            self.send_message(client_socket, 'UNREGISTER_OK', response_data)

            del self.clients[client_socket]

            self.broadcast_user_update('USER_LEFT', nickname, '', 0, exclude=client_socket)

            print(f"Client {nickname} abgemeldet")

    def handle_broadcast(self, client_socket, json_data):
        if client_socket not in self.clients:
            self.send_error(client_socket, "Nicht registriert")
            return

        sender = self.clients[client_socket].nickname
        broadcast_message = json_data.get('message', '')

        broadcast_data = {
            'sender': sender,
            'message': broadcast_message,
            'timestamp': time.time()
        }

        for other_socket, other_info in self.clients.items():
            if other_socket != client_socket:
                self.send_message(other_socket, 'BROADCAST_MSG', broadcast_data)

        response_data = {
            'message': 'Message broadcasted'
        }
        self.send_message(client_socket, 'BROADCAST_OK', response_data)

        print(f"Broadcast von {sender}: {broadcast_message}")

    def handle_get_users(self, client_socket):
        """Aktuelle Benutzerliste senden"""
        self.send_user_list(client_socket)

    def send_user_list(self, client_socket):
        user_list = []
        for other_socket, client_info in self.clients.items():
            if other_socket != client_socket:  # Eigenen Client nicht in Liste
                user_list.append({
                    'nickname': client_info.nickname,
                    'ip': client_info.ip,
                    'udp_port': client_info.udp_port
                })

        response_data = {
            'users': user_list
        }
        self.send_message(client_socket, 'USER_LIST', response_data)

    def broadcast_user_update(self, update_type, nickname, ip, udp_port, exclude=None):
        update_data = {
            'nickname': nickname,
            'ip': ip,
            'udp_port': udp_port,
            'timestamp': time.time()
        }

        for client_socket, client_info in self.clients.items():
            if client_socket != exclude:
                self.send_message(client_socket, update_type, update_data)

    def send_error(self, client_socket, error_message):
        error_data = {
            'message': error_message
        }
        self.send_message(client_socket, 'ERROR', error_data)

    def disconnect_client(self, client_socket):
        if client_socket in self.clients:
            client_info = self.clients[client_socket]
            nickname = client_info.nickname

            del self.clients[client_socket]

            self.broadcast_user_update('USER_LEFT', nickname, '', 0, exclude=client_socket)

            print(f"Client {nickname} getrennt")

        try:
            client_socket.close()
        except:
            pass

    def stop(self):
        self.running = False
        if self.server_socket:
            self.server_socket.close()

def main():
    server = GroupChatServer()
    try:
        server.start()
    except KeyboardInterrupt:
        print("\nServer wird beendet...")
        server.stop()
        print("Server beendet")


if __name__ == "__main__":
    main()
