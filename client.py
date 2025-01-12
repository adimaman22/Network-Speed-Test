import socket
import struct
import threading
import time
import os
from ansi_colors import *

# Constants for the packet formats and magic cookie
MAGIC_COOKIE = 0xabcddcba
OFFER_TYPE = 0x2
REQUEST_TYPE = 0x3
PAYLOAD_TYPE = 0x4

# Configurable ports using environment variables
SERVER_UDP_PORT = int(os.getenv('SERVER_UDP_PORT', 15000))

def listen_for_offers():
    """
    Listens for UDP offers from the server.
    - Opens a UDP socket and waits for broadcast offers from the server.
    - If a valid offer is received, it returns the server's IP and port numbers.

    Returns:
        tuple: (server_ip, tcp_port, udp_port)
    """
    print(f"{INFO_COLOR}Client started, listening for offer requests...{RESET_COLOR}")

    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # ReUse of running port 
    udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    udp_socket.bind(('', SERVER_UDP_PORT))
    udp_socket.settimeout(35)  # Prevent infinite loop

    try:

        while True:

            try:
                data, server_address = udp_socket.recvfrom(2048)
                magic_cookie, message_type, server_udp_port, server_tcp_port = struct.unpack('!IBHH', data)

                if magic_cookie == MAGIC_COOKIE and message_type == OFFER_TYPE:
                    print(f"{SUCCESS_COLOR}Received offer from {server_address[0]} on UDP port: {server_udp_port}, and TCP port: {server_tcp_port}{RESET_COLOR}")
                    udp_socket.close()
                    return server_address[0], server_tcp_port, server_udp_port

            
            except (socket.timeout):
                print(f"{WARNING_COLOR}Timed out while waiting for an offer.{RESET_COLOR}")
                continue
                
            except (struct.error, ValueError):
                print(f"{ERROR_COLOR}Invalid offer received.{RESET_COLOR}")
                continue

    finally:
        udp_socket.close()

def get_user_input():
    """
    Collects and validates user input for file size and number of connections.
    - Prompts the user to enter file size, number of TCP and UDP connections.
    - Ensures inputs are positive integers.

    Returns:
        tuple: (file_size, tcp_connections, udp_connections)
    """
    try:
        # File size input
        file_size = input(f"{INFO_COLOR}Enter file size (bytes): {RESET_COLOR}").strip()
        if not file_size.isdigit() or int(file_size) <= 0:
            print(f"{ERROR_COLOR}Invalid file size. Must be a positive integer.{RESET_COLOR}")
            return None
        file_size = int(file_size)

        # TCP connections input
        tcp_connections = input(f"{INFO_COLOR}Enter number of TCP connections: {RESET_COLOR}").strip()
        if not tcp_connections.isdigit() or int(tcp_connections) <= 0:
            print(f"{ERROR_COLOR}Invalid number for TCP connections. Must be a positive integer.{RESET_COLOR}")
            return None
        tcp_connections = int(tcp_connections)

        # UDP connections input
        udp_connections = input(f"{INFO_COLOR}Enter number of UDP connections: {RESET_COLOR}").strip()
        if not udp_connections.isdigit() or int(udp_connections) <= 0:
            print(f"{ERROR_COLOR}Invalid number for UDP connections. Must be a positive integer.{RESET_COLOR}")
            return None
        udp_connections = int(udp_connections)

        # Return validated inputs
        return file_size, tcp_connections, udp_connections

    except Exception as e:
        print(f"{ERROR_COLOR}Error while collecting input: {e}{RESET_COLOR}")
        return None

def initiate_tcp_test(server_ip, tcp_port, file_size, tcp_connections, transfer_id):
    """
    Initiates a single TCP speed test.
    - Connects to the server using TCP and sends a request for a specific file size.
    - Receives data from the server and calculates transfer speed.

    Args:
        server_ip (str): Server IP address
        tcp_port (int): TCP Port number
        file_size (int): Total file size in bytes
        tcp_connections (int): Number of TCP connections
        transfer_id (int): ID of the transfer for logging purposes
    """
    try:
        tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tcp_socket.connect((server_ip, tcp_port))

        segment_size = file_size // tcp_connections

        start_time = time.time()
        tcp_socket.sendall(f"{segment_size}\n".encode())

        bytes_receive = 0
        chunk_size = 1024

        while bytes_receive < segment_size:
            c = tcp_socket.recv(chunk_size)
            if not c:
                break
            bytes_receive += len(c)
        
        end_time = time.time()
        print(f"{SUCCESS_COLOR}TCP transfer #{transfer_id} finished, total time: {end_time - start_time:.2f} seconds, total speed: {segment_size * 8 / (end_time - start_time):.2f} bits/second{RESET_COLOR}")

    except Exception as e:
        print(f"{ERROR_COLOR}Error during TCP speed test: {e}{RESET_COLOR}")

    finally:
        tcp_socket.close()

def initiate_udp_test(server_ip, udp_port, file_size, udp_connections, transfer_id):
    """
    Initiates a single UDP speed test.
    This function sends a speed test request to the server and measures the 
    speed and success rate of the received UDP packets.

    The client sends a request to the server specifying the desired file size.
    The server responds by sending data in UDP packets, which the client attempts
    to receive until the transfer completes or times out.

    Args:
        server_ip (str): The IP address of the server.
        udp_port (int): The port number used for the UDP test.
        file_size (int): The total requested file size in bytes.
        udp_connections (int): The number of concurrent UDP connections (used for splitting data).
        transfer_id (int): An identifier for this specific transfer (for logging).
    """
    try:
        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_socket.settimeout(1) # The UDP transfer concludes after no data has been received for 1 second

        segment_size = file_size // udp_connections
        request_segment = struct.pack('!IBQ', MAGIC_COOKIE, REQUEST_TYPE, segment_size)

        start_time = time.time()
        udp_socket.sendto(request_segment, (server_ip, udp_port))

        received_segments = 0
        total_segment_count = 0
        last_received_time = time.time()  # the last time a packet recived
        
        while True:
            try:
                data, _ = udp_socket.recvfrom(2048)
                last_received_time = time.time()  # update the last time a packet recived
                received_segments += 1

                if len(data) < 21: continue

                magic_cookie, message_type, total_segment_count, _ = struct.unpack('!IBQQ', data[:21])

                if magic_cookie != MAGIC_COOKIE or message_type != PAYLOAD_TYPE:
                    continue

                if received_segments == total_segment_count:
                    break

            except socket.timeout as e:
                if time.time() - last_received_time > 1:
                    print(f"{WARNING_COLOR}No packets received for 1 second. Ending UDP transfer.{RESET_COLOR}")
                    break

        end_time = time.time()
        success_rate = (received_segments / total_segment_count) * 100 if total_segment_count != 0 else 0
        print(f"{SUCCESS_COLOR}UDP transfer #{transfer_id} finished, total time: {end_time - start_time:.2f} seconds, total speed: {segment_size * 8 / (end_time - start_time):.2f} bits/second, percentage of packets received successfully: {success_rate:.2f}%{RESET_COLOR}")

    except Exception as e:
        print(f"{WARNING_COLOR}Error during UDP speed test: {e}{RESET_COLOR}")
    
    finally:
        udp_socket.close()

def initiate_speed_test(server_ip, tcp_port, udp_port, file_size, tcp_connections, udp_connections):
    """
    Initiates multiple TCP and UDP tests concurrently using threads.
    - Starts the specified number of TCP and UDP connections.
    - Waits for all transfers to complete before finishing.

    Args:
        server_ip (str): Server IP address
        tcp_port (int): TCP Port number
        udp_port (int): UDP Port number
        file_size (int): Total file size in bytes
        tcp_connections (int): Number of TCP connections
        udp_connections (int): Number of UDP connections
    """
    tcp_threads = []
    udp_threads = []

    for i in range(tcp_connections):
        tcp_thread = threading.Thread(target=initiate_tcp_test, args=(server_ip, tcp_port, file_size, tcp_connections, i+1))
        tcp_threads.append(tcp_thread)
        tcp_thread.start()

    for i in range(udp_connections):
        udp_thread = threading.Thread(target=initiate_udp_test, args=(server_ip, udp_port, file_size, udp_connections, i+1))
        udp_threads.append(udp_thread)
        udp_thread.start()

    for thread in tcp_threads + udp_threads:
        thread.join()

    print(f"{SUCCESS_COLOR}All transfers completed successfully.{RESET_COLOR}")

def main():
    """
    Main entry point for the client program.
    - Listens for offers from the server.
    - Collects user input for test parameters.
    - Initiates speed tests based on the collected data.
    """
    server_ip_address, server_tcp_port, server_udp_port = listen_for_offers()

    if not server_ip_address or not server_tcp_port or not server_udp_port:
        print(f"{ERROR_COLOR}No valid server offer received, exiting.{RESET_COLOR}")
        return
    
    params = get_user_input()
    if params:
        file_size, tcp_connections, udp_connections = params
        print(f"{HIGHLIGHT_COLOR}Starting speed test with File Size: {file_size}, TCP Connections: {tcp_connections}, UDP Connections: {udp_connections}{RESET_COLOR}")

        initiate_speed_test(server_ip_address, server_tcp_port, server_udp_port, file_size, tcp_connections, udp_connections)
    
    else: 
        exit(1)

if __name__ == "__main__":
    main()
