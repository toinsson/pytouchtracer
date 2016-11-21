"""
This is the slave application that runs on the MS surface pro tablet to capture
touch events and send them to the master part of the app. This script is 
responsible to launch different Kivy based app like game or pattern with a call
to subprocess.call, the user will then hit escape to exit. The command is sent
with zeromq in a client/server scenario.
OBS: this script should be executed at the root of the repo.
"""

import zmq
import time
import subprocess
import threading
import Queue

class ConnectionError(Exception):
    def __init__(self, msg, value):
        self.msg = msg
        self.value = value
    def __str__(self):
        return repr(self.msg)

## static ips
local_server_ip = 'localhost'
surface_server_ip = '130.209.246.21'

class LPClient(object):
    """Lazy Pirate Client, will connect to a server with polling, does 
    REQUEST_RETRIES tries with REQUEST_TIMEOUT before closing. Execute in main
    thread with blocking.
    """

    def __init__(self, 
        server,
        port,
        REQUEST_TIMEOUT = 2500,
        REQUEST_RETRIES = 3,
        ):

        super(LPClient, self).__init__()

        self.REQUEST_TIMEOUT = REQUEST_TIMEOUT
        self.REQUEST_RETRIES = REQUEST_RETRIES
        self.SERVER_ENDPOINT = "tcp://"+server+":%s" % port

        print self.SERVER_ENDPOINT

        self.context = zmq.Context(1)

        print "I: Connecting to server"
        self.client = self.context.socket(zmq.REQ)
        self.client.connect(self.SERVER_ENDPOINT)

        self.poll = zmq.Poller()
        self.poll.register(self.client, zmq.POLLIN)

    def send_pyobj(self, request):
        retries_left = self.REQUEST_RETRIES

        while retries_left:

            print "I: Sending (%s)" % request
            self.client.send_pyobj(request)

            expect_reply = True
            while expect_reply:
                socks = dict(self.poll.poll(self.REQUEST_TIMEOUT))

                if socks.get(self.client) == zmq.POLLIN:
                    reply = self.client.recv()

                    if not reply:
                        break

                    if reply: ## reply code is ok
                        print "I: Server replied OK (%s)" % reply
                        retries_left = 0#self.REQUEST_RETRIES
                        expect_reply = False
                    else:
                        print "E: Malformed reply from server: %s" % reply

                else:
                    print "W: No response from server, retrying"
                    # Socket is confused. Close and remove it.
                    self.client.setsockopt(zmq.LINGER, 0)
                    self.client.close()
                    self.poll.unregister(self.client)
                    retries_left -= 1
                    if retries_left == 0:
                        print "E: Server seems to be offline, abandoning"
                        raise ConnectionError(self.SERVER_ENDPOINT+' is offline', 0)
                        # break
                    print "I: Reconnecting and resending (%s)" % request

                    # Create new connection
                    self.client = self.context.socket(zmq.REQ)
                    self.client.connect(self.SERVER_ENDPOINT)
                    self.poll.register(self.client, zmq.POLLIN)
                    self.client.send_pyobj(request)

    def term(self):
        ## could be put in a enter/exit
        self.context.term()


class ThreadedServer(threading.Thread):
    """Simple server executing in own thread, continuously listen for request.
    On receive, will match msgType to its command dictionary and call found
    function.
    """
    def __init__(self, cmd_dict, port):
        super(ThreadedServer, self).__init__()

        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.REP)
        self.socket.bind("tcp://*:%s" % port)

        # store the list of function to be used when receiving msg
        self.request_alive = False
        self.cmd_dict = cmd_dict
        self.loop_event = threading.Event()
        self.loop_event.set()
        self.start()

    def stop(self):
        self.loop_event.clear()


    def run(self):
        while self.loop_event.is_set():
            # print 'read'
            try:
                message = self.socket.recv_pyobj(zmq.NOBLOCK)
                self.request_alive = True
            except zmq.Again:
                continue

            try:
                msgType = message['msgType']
                print msgType

                if 'args' in message.keys():
                    args = message['args']
                    self.cmd_dict[msgType](*args)
                else:
                    self.cmd_dict[msgType]()
                print 'cmd done'

                # send reply
                rpl = dict(type='exit')
                self.socket.send_pyobj(rpl)
                self.request_alive = False

                if msgType == 'runAndDie':
                    self.loop_event.clear()

            except KeyError:
                msgType = 'error'
                print "wrong format, msg['type'] not recognized"
                pass

            time.sleep(0.1)

        print 'exiting'


class SimplePublisher(object):
    """
    """
    def __init__(self, port):

        super(SimplePublisher, self).__init__()

        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.PUB)
        self.socket.bind("tcp://*:%s" % port)

    def send_topic(self, topic, data):
        self.socket.send(topic+' '+data)

    def close(self):
        self.socket.close()
        self.context.term()


class ThreadedSubscriber(threading.Thread):
    """
    """
    def __init__(self, server, port, queue, noblock = False, topic = "", purge = True):

        super(ThreadedSubscriber, self).__init__()

        ## 0mq socket
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.SUB)
        self.socket.connect ("tcp://"+server+":%s" % port)
        self.socket.setsockopt(zmq.SUBSCRIBE, topic)  # all messages
        self.socket.setsockopt(zmq.SUBSCRIBE, "kill")  # kill message

        self.dataqueue = queue
        self.noblock = noblock
        self.purge = purge

        self.loop_event = threading.Event()
        self.loop_event.set()

        self.start()

    def run(self):
        print('run')
        while self.loop_event.is_set():

            if self.noblock:
                try:
                    m = self.socket.recv(zmq.NOBLOCK)
                except zmq.ZMQError:
                    time.sleep(1./10)
                    continue

            else:
                m = self.socket.recv()

            if m == "kill ":
                print("client thread closing!")
                break  # producer closed connection

            else:
                if self.purge:  # remove last item if consummer didn't
                    try:
                        self.dataqueue.get(block=False)
                        self.dataqueue.put(m)
                    except Queue.Empty:
                        self.dataqueue.put(m)
                else:
                    self.dataqueue.put(m)

        print("client thread closed!" )

    def stop(self):
        print 'call stop'
        self.loop_event.clear()


## the protcol for the message is: msg -> res
## msg: python dictionary since the receive call is recv_pyobj
##      dict{msgType='command', command=List}
##        List = python list for subprocess.call
##      dict{msgType='exit'}
##
## res: python dictionary since the receive call is recv_pyobj
##      dict{msgType='command', command=returnCode}
##        returnCode = return code from subprocess.call
##      dict{msgType='exit'}


class Server(object):
    """Server class, will be on MS Surface Pro 3.
    """
    def __init__(self, port):
        super(Server, self).__init__()

        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.REP)
        self.socket.bind("tcp://*:%s" % port)

    def run(self):
        while True:
            message = self.socket.recv_pyobj()

            try:
                msgType = message['msgType']
            except KeyError:
                msgType = 'error'
                print "wrong format, msg['type'] not recognized"
                pass

            if msgType == 'exit':
                rpl = dict(type='exit')
                self.socket.send_pyobj(rpl)
                break

            if msgType == 'command':
                cmd = message['command']
                p = subprocess.Popen(cmd)
                rpl = dict(type='command', command=True)
                self.socket.send_pyobj(rpl)

            time.sleep(1)


class Client(object):
    """Client class, will be master computer - deprecated.
    """
    def __init__(self, port, server):
        super(Client, self).__init__()

        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.REQ)
        self.socket.connect ("tcp://"+server+":%s" % port)

    def send(self, message):
        self.socket.send_pyobj(message)
        msg = self.socket.recv_pyobj()
        return msg


class Message(object):
    """Protocol message.
    command example: command = ['python', 'touchrecorder/game.py', '--local']
    """
    def __init__(self, msgType, command=''):
        super(Message, self).__init__()
        self.msg = dict()
        if msgType == 'command':
            self.msg['msgType'] = 'command'
            self.msg['command'] = command

        if msgType == 'exit':
            self.msg['msgType'] = 'exit'


## command line interface
import argparse

if __name__ == '__main__':
    desc = ''.join(['Run as main will start a server.'])
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument('--server', help='server IP, default 130.209.246.21', required=False, default=surface_server_ip)
    parser.add_argument('--port', help='communition port, default 5556', required=False, default="5556")
    args = parser.parse_args()

    surfacePro = Server(args.port)
    surfacePro.run()