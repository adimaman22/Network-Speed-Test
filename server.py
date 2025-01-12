import socket
import struct
import threading
import time
import os
from ansi_colors import *

# HotSpot IP:
ServerIP= '172.20.10.10' # Adi HotSpot
# ServerIP= '192.168.144.127' # Tomer HotSpot

# Constants for the packet formats and magic cookie
MAGIC_COOKIE = 0xabcddcba
OFFER_TYPE = 0x2
REQUEST_TYPE = 0x3
PAYLOAD_TYPE = 0x4

# Load ports from environment variables with fallback defaults (not from the well-Known ports 0-1023)
SERVER_UDP_PORT = int(os.getenv('SERVER_UDP_PORT', 15000))
SERVER_TCP_PORT = int(os.getenv('SERVER_TCP_PORT', 16000))

def get_local_ip():
    """
    Returns the current IP address of the server.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # connect to: 8.8.8.8 (Google DNS) on HTTP
        s.connect(("8.8.8.8", 80))  # Connect to an external server to get the current IP
        ip_address = s.getsockname()[0] # (ip,port), so 0 is the ip
    except Exception as e:
        ip_address = ServerIP  # Fallback to ServerIP if error occurs
    finally:
        s.close()
    return ip_address


def udp_offer_sender(udp_socket):
    """
    Continuously sends UDP offer messages to broadcast address every second.
      - Sends a packet containing the server's details for clients to detect availability.
    No inputs, runs indefinitely unless an exception occurs.
    """
    print(f"{INFO_COLOR}Starting UDP Offer Broadcast...{RESET_COLOR}")
    try:
        offer_message = struct.pack('!IBHH', MAGIC_COOKIE, OFFER_TYPE, SERVER_UDP_PORT, SERVER_TCP_PORT)
        udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        while True:
            udp_socket.sendto(offer_message, ('<broadcast>', SERVER_UDP_PORT))
            # print(f"{SUCCESS_COLOR}Offer broadcast sent!{RESET_COLOR}")
            time.sleep(1)
    except Exception as e:
        print(f"{ERROR_COLOR}Error in UDP offer sender: {e}{RESET_COLOR}")


def handle_tcp_connection(client_socket):
    """
    Handles incoming TCP connections for speed testing.
    - Receives a file size request and sends the requested amount of dummy data.    
    
    Args:
        client_socket (socket): The connected client socket for communication.
    """
    try:
        data = client_socket.recv(1024).decode().strip()

        if not data or not data.isdigit() or int(data) <= 0:
                print(f"{ERROR_COLOR}Invalid TCP request received.{RESET_COLOR}")
                return False

        file_size_bytes = int(data)
        print(f"{SUCCESS_COLOR}TCP Request received: {file_size_bytes} bytes{RESET_COLOR}")

        total_bytes_sent = 0
        chunk_size = 1024
        
        while total_bytes_sent < file_size_bytes:
            remaining_bytes = file_size_bytes - total_bytes_sent
            chunk_to_send = b'a' * min(chunk_size, remaining_bytes)
            client_socket.sendall(chunk_to_send)
            total_bytes_sent += len(chunk_to_send)

        print(f"{SUCCESS_COLOR}TCP transfer completed.{RESET_COLOR}")
        return True

    except Exception as e:
        print(f"{ERROR_COLOR}Error handling TCP connection: {e}{RESET_COLOR}")
        return False

    finally:
        client_socket.close()

def start_tcp_server(tcp_socket):
    """
    Starts the TCP server to handle incoming client connections for speed tests.
    Binds the server to the configured TCP port and handles each connection in a new thread.

    Args:
        tcp_socket (socket): The connected client socket for communication.
    """
    try:
        while True:
            client_socket, client_address = tcp_socket.accept()
            print(f"{INFO_COLOR}New TCP connection from {client_address}{RESET_COLOR}")
            threading.Thread(target=handle_tcp_connection, args=(client_socket,)).start()
    except Exception as e:
        print(f"{ERROR_COLOR}Error in TCP server: {e}{RESET_COLOR}")


def handle_udp_connection(data, client_address, udp_socket):
    """
    Handles a single UDP speed test request by sending the requested file size back to the client.

    Args:
        - data: Received data packet containing request details
        - client_address: The address of the client sending the request
        - udp_socket: The socket used for communication

    Returns:
        - bool: True if the transfer was successful, False if an error occurred.
    """
    try:
        if len(data) != 13:
            return False

        unpacked_data = struct.unpack('!IBQ', data)
        magic_cookie, message_type, file_size = unpacked_data
        if magic_cookie != MAGIC_COOKIE or message_type != REQUEST_TYPE:
            print(f"{ERROR_COLOR}Invalid UDP request received, closing connection.{RESET_COLOR}")
            return False

        print(f"{SUCCESS_COLOR}UDP Request received for {file_size} bytes from {client_address}{RESET_COLOR}")

        chunk_size = 1024 # split into chunks of 1024 bytes each
        chunks = (file_size + chunk_size - 1) // chunk_size

        for chunk_number in range(chunks):
            payload_header = struct.pack('!IBQQ', MAGIC_COOKIE, PAYLOAD_TYPE, chunks, chunk_number)
            remaining_bytes = file_size - (chunk_number * chunk_size)
            payload_message = b'd' * min(chunk_size, remaining_bytes)
            udp_socket.sendto(payload_header + payload_message, client_address)

        print(f"{SUCCESS_COLOR}UDP transfer completed.{RESET_COLOR}")
        return True

    except Exception as e:
        print(f"{ERROR_COLOR}Error handling UDP connection: {e}{RESET_COLOR}")
        return False

def start_udp_server(udp_socket):
    """
    Starts the UDP server and listens for incoming speed test requests.
    - This function runs an infinite loop, waiting for incoming UDP packets from clients.
    - Each incoming request is handled in a separate thread using the `handle_udp_connection` function.
    - Each received request is handled in a separate thread.

    Args:
        udp_socket (socket): The UDP socket used for receiving client requests.
    """
    try:
        while True:
            data, client_address = udp_socket.recvfrom(2048)
            threading.Thread(target=handle_udp_connection, args=(data, client_address, udp_socket), daemon=True).start()
    except Exception as e:
        print(f"{ERROR_COLOR}Error in UDP server: {e}{RESET_COLOR}")


# Main function to start both servers
def main():
    """
    Main entry point for the server application.
    This function initializes both the TCP and UDP servers and starts them
    on separate threads to handle incoming client requests concurrently.

    Steps Performed:
    1. Initializes the UDP and TCP sockets.
    2. Binds the sockets to the specified ports and configures socket options.
    3. Starts the UDP broadcast for service discovery (`udp_offer_sender`).
    4. Starts the TCP and UDP servers for handling speed test requests (`start_tcp_server`, `start_udp_server`).
    5. Keeps the server running indefinitely unless an exception occurs.
    """
    udp_socket, tcp_socket = None, None

    try:

        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) 
        udp_socket.bind(('0.0.0.0', SERVER_UDP_PORT))
        # udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024 * 1024)
        udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1024 * 1024)
        print(f"{SUCCESS_COLOR}UDP Server started on port {SERVER_UDP_PORT}{RESET_COLOR}")

        tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        tcp_socket.bind(('0.0.0.0', SERVER_TCP_PORT))
        tcp_socket.listen()
        print(f"{SUCCESS_COLOR}TCP Server started on port {SERVER_TCP_PORT}{RESET_COLOR}")

        print(f"{HIGHLIGHT_COLOR}Server started, listening on IP address {get_local_ip()}{RESET_COLOR}")

        # Starting all servers in separate threads
        threading.Thread(target=udp_offer_sender, args=(udp_socket,), daemon=True).start()
        threading.Thread(target=start_tcp_server, args=(tcp_socket,), daemon=True).start()
        threading.Thread(target=start_udp_server, args=(udp_socket,), daemon=True).start()

        while True:
            time.sleep(1)

    except Exception as e:
        print(f"{ERROR_COLOR}Critical error during server startup: {e}{RESET_COLOR}")

    finally:
        if udp_socket:
            udp_socket.close()
        if tcp_socket:
            tcp_socket.close()


if __name__ == "__main__":
    main()
