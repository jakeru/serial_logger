#!/usr/bin/env python3

# Connects to a TCP socket or a serial port and sends
# one or several commands to it.
# Prints the output until the prompt (`>`) is received or until
# a timeout occurs.
#
# Written by Jakob Ruhe

import argparse
import atexit
import os
import readline
import socket
import sys
import time

# Requires pyserial.
import serial


PROMPT = ">"


class Interface:
    def read(self, size, timeout=0):
        raise NotImplementedError()

    def write(self, data):
        raise NotImplementedError()

    def flush_input(self):
        while self.read(1024, timeout=0.1):
            pass


class SerialInterface(Interface):
    def __init__(self, port, baudrate):
        self.dev = serial.Serial(port, baudrate)

    def read(self, size, timeout=0):
        self.dev.timeout = timeout
        return self.dev.read(size)

    def write(self, data):
        self.dev.write(data)


class SocketInterface(Interface):
    def __init__(self, host, port):
        self.dev = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.dev.connect((host, port))

    def read(self, size, timeout=0):
        self.dev.settimeout(timeout)
        try:
            return self.dev.recv(size)
        except socket.timeout:
            return b""

    def write(self, data):
        self.dev.send(data)


def wait_for_response(interface, timeout):
    start = time.time()
    found_prompt = False
    newline = False
    while True:
        if (time_left := start + timeout - time.time()) <= 0:
            break
        data = interface.read(1, timeout=time_left)
        found_prompt = data == PROMPT.encode() and newline
        if found_prompt or time.time() >= start + timeout:
            break
        newline = data == b"\n"
        sys.stdout.buffer.write(data)
    if not found_prompt:
        if not newline:
            print("")
        print("Timeout before prompt was found. Perhaps increase timeout?")


def read_available_input(interface):
    while data := interface.read(1024, timeout=0.1):
        sys.stdout.buffer.write(data)


def interactive(interface, timeout):
    histfile = os.path.join(os.path.expanduser("~"), ".serial_client_history")
    try:
        readline.read_history_file(histfile)
        readline.set_history_length(1000)
        length = readline.get_current_history_length()
        plural = "s" if length != 1 else ""
        print(f"Read {length} line{plural} from history file '{histfile}'.")
    except FileNotFoundError:
        pass
    atexit.register(readline.write_history_file, histfile)
    try:
        while True:
            cmd = input(PROMPT + " ")
            read_available_input(interface)
            interface.write((cmd + "\n").encode())
            wait_for_response(interface, timeout)
    except (EOFError, KeyboardInterrupt):
        pass


def split_host_and_port(host_colon_port):
    host, port = host_colon_port.split(":")
    return host if host else "localhost", int(port)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Serial client",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--serial",
        help="The serial device to connect to",
    )
    parser.add_argument(
        "--socket",
        metavar="HOST:PORT",
        help="Host and port to connect to, separated by `:`",
    )
    parser.add_argument(
        "--baudrate",
        type=int,
        default=115200,
        help="Baudrate of the serial device",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=1,
        help="Timeout in seconds",
    )
    parser.add_argument(
        "cmd",
        nargs="*",
        help=("Command to run. Interactive mode is activated if no command is given."),
    )
    return parser.parse_args()


def main():
    args = parse_args()
    if args.socket and args.serial:
        print("Please specify either --socket or --serial, not both.")
        sys.exit(1)
    if args.socket:
        try:
            host, port = split_host_and_port(args.socket)
        except ValueError:
            print(
                (
                    "Please specify target to connect to as '<host>:<port>', "
                    "or just ':<port>' for localhost."
                )
            )
            sys.exit(1)
        interface = SocketInterface(host, port)
    elif args.serial:
        interface = SerialInterface(args.serial, args.baudrate)
    else:
        print("Please specify either --socket or --serial.")
        sys.exit(1)
    if args.cmd:
        interface.write((" ".join(args.cmd) + "\n").encode())
        wait_for_response(interface, args.timeout)
    else:
        print(
            (
                "No command given. Entering interactive mode. "
                "Use ctrl+c or ctrl+d to exit."
            )
        )
        interactive(interface, args.timeout)


if __name__ == "__main__":
    main()
