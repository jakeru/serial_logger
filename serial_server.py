#!/usr/bin/env python3

# This tool can run continuously to serve clients that want access
# to the same serial port.
# The data sent from clients is line buffered.
# This tool can be installed as a systemd service.
#
# Written by Jakob Ruhe

import argparse
import socket
import select
import sys
import io

# Requires pip package pyserial
import serial


class LineBuf:
    def __init__(self):
        self.buf = io.BytesIO()

    def write(self, data):
        self.buf.write(data)

    def readline(self):
        data = self.buf.getvalue()
        pos = data.find(b"\n")
        if pos == -1:
            return None
        line = data[0 : pos + 1]
        self.buf = io.BytesIO(data[pos + 1 :])
        return line


class Client:
    def __init__(self, sock, addr):
        self.sock = sock
        self.addr = addr
        self.buf = LineBuf()

    def read(self):
        try:
            data = self.sock.recv(1024)
        except OSError:
            return None
        if not data:
            return None
        self.buf.write(data)
        return data

    def readline(self):
        return self.buf.readline()

    def write(self, data):
        try:
            self.sock.send(data)
        except OSError:
            pass

    def fileno(self):
        return self.sock.fileno()

    def close(self):
        self.sock.close()


class Serial:
    def __init__(self, dev):
        self.dev = dev
        self.buf = LineBuf()

    def read(self):
        data = self.dev.read()
        if not data:
            return None
        self.buf.write(data)
        return data

    def readline(self):
        return self.buf.readline()

    def write(self, data):
        self.dev.write(data)

    def fileno(self):
        return self.dev.fileno()


def process_serial(clients, ser):
    data = ser.read()
    sys.stdout.write(data.decode("utf-8", "backslashreplace"))
    for c in clients.values():
        c.write(data)


def process_clients(clients, ser):
    remove_clients = []
    for c in clients:
        data = c.read()
        if not data:
            remove_clients.append(c)
            continue
        while line := c.readline():
            ser.write(line)
    return remove_clients


def run(ser, serversocket):
    clients = {}
    while True:
        fds = [serversocket.fileno(), ser.fileno()]
        for c in clients.values():
            fds.append(c.sock.fileno())
        r, w, x = select.select(fds, [], [])
        if serversocket.fileno() in r:
            sock, addr = serversocket.accept()
            clients[sock.fileno()] = Client(sock, addr)
        if ser.fileno() in r:
            process_serial(clients, ser)
        ready_clients = [c for fd, c in clients.items() if fd in r]
        remove_clients = process_clients(ready_clients, ser)
        for c in remove_clients:
            del clients[c.fileno()]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Serial Logger - share a serial device through a socket",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "device",
        help="The serial device to read from",
    )
    parser.add_argument(
        "--baudrate",
        type=int,
        default=115200,
        help="Baudrate of the serial device",
    )
    parser.add_argument(
        "--bind",
        default="localhost",
        help="Address to bind server socket to",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5555,
        help="Port to listen for connections on",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    ser = Serial(serial.Serial(args.device, args.baudrate))
    serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    serversocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    serversocket.bind((args.bind, args.port))
    serversocket.listen()
    sys.stdout.reconfigure(line_buffering=True)
    try:
        run(ser, serversocket)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
