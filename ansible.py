#
# Ansible - simple relay server for file transfer
#
# Usage:
#
# $ ansible receive <channel_name> <destination_file>
#
# In anoter host,
# $ ansible send <channel_name> <source_file>
#
from twisted.web import server, resource
from twisted.internet import reactor, endpoints, protocol

import re
import time
import uuid
import json
from pprint import pprint


ANSIBLES_MAX = 100
ANSIBLE_PORT_WEB = 5000
ANSIBLE_PORT_TRANSPORT = 5001

ansible_map = {}
address_map = {}

def address_map_put(client_ip, client_uuid, channel, transport):
    if client_ip not in address_map:
        address_map[client_ip] = {}
    if client_uuid not in address_map[client_ip]:
        address_map[client_ip][client_uuid] = {}

    if channel is not None:
        address_map[client_ip][client_uuid]['channel'] = channel
    if transport is not None:
        address_map[client_ip][client_uuid]['transport'] = transport

def address_map_get(client_ip, client_uuid):
    if (client_ip in address_map) and (client_uuid in address_map[client_ip]):
        return address_map[client_ip][client_uuid]
    return None

def address_map_del(client_ip, client_uuid):
    if (client_ip in address_map) and (client_uuid in address_map[client_ip]):
        del address_map[client_ip][client_uuid]
        if len(address_map[client_ip]) == 0:
            del address_map[client_ip]

def cleanup_channel(client_ip):
    if client_ip not in address_map:
        return

    channel = address_map[client_ip].values()[0]['channel']
    if channel not in ansible_map:
        return

    # Disconnect clients
    ansible = ansible_map[channel]

    for target in ['sender', 'receiver']:
    #for target in ['sender']:
        if target in ansible:
            target_info = address_map_get(ansible[target][0], ansible[target][1])
            if target_info and 'transport' in target_info:
                target_info['transport'].loseConnection()
                address_map_del(ansible[target][0], ansible[target][1])

    del ansible_map[channel]

    print "AnsibleTransport: channel '{}' is cleaned up".format(channel)
    pprint(ansible_map)


# Ansible Web Server
class AnsibleWeb(resource.Resource):
    isLeaf = True

    def _process_send(self, request, channel):
        if channel not in ansible_map:
            return json.dumps({'result': False, 'reason': 'there is no receiver'})

        client_ip = request.getClientIP()
        client_uuid = uuid.uuid4().hex

        if 'sender' not in ansible_map[channel]:
            ansible_map[channel]['sender'] = (client_ip, client_uuid)
            address_map_put(client_ip, client_uuid, channel, None)

        elif ansible_map[channel]['sender'] != (client_ip, client_uuid):
            return json.dumps({'result': False, 'reason': 'this channel is already in use'})

        return json.dumps({'result': True, 'uuid': client_uuid})


    def _process_receive(self, request, channel):
        if len(ansible_map) >= ANSIBLES_MAX:
            return json.dumps({'result': False,
                               'reason': 'the number of ansibles reaches its limit: {}'.format(ANSIBLES_MAX)})

        client_ip = request.getClientIP()
        client_uuid = uuid.uuid4().hex

        # Remove the expired channel
        if (channel in ansible_map) and (ansible_map[channel]['expired_at'] < time.time()):
            del ansible_map[channel]

        if channel not in ansible_map:
            ansible_map[channel] = {'receiver': (client_ip, client_uuid), 'created_at': time.time()}
            ansible_map[channel]['expired_at'] = ansible_map[channel]['created_at'] + (60 * 5) # 5 minutes
            address_map_put(client_ip, client_uuid, channel, None)

        elif ansible_map[channel]['receiver'] != (client_ip, client_uuid):
            return json.dumps({'result': False, 'reason': 'this channel is already in use'})

        return json.dumps({'result': True, 'uuid': client_uuid})


    def render_GET(self, request):
        print 'AnsibleWeb: {} => {}'.format(request.getClientIP(), request.uri)
        retval = json.dumps({'result': False, 'reason': 'invalid endpoint'})

        if re.match('^/send/[^/?]+$', request.uri):
            (_, _, channel) = request.uri.split('/')
            retval = self._process_send(request, channel)

        if re.match('^/receive/[^/?]+$', request.uri):
            (_, _, channel) = request.uri.split('/')
            retval = self._process_receive(request, channel)

        if re.match('^/script$', request.uri):
            with open('ansible.sh', 'r') as f:
                retval = f.read()

        pprint(ansible_map)
        return retval


# Ansible Transport Server
class AnsibleTransport(protocol.Protocol):
    def __init__(self, factory):
        self.factory = factory
        self.client_uuid = ''
        self.client_ip = ''

    def connectionMade(self):
        self.factory.numProtocols = self.factory.numProtocols + 1

        # Store client ip
        self.client_ip = self.transport.getPeer().host


    def connectionLost(self, reason):
        self.factory.numProtocols = self.factory.numProtocols - 1

        # Clean up this channel
        cleanup_channel(self.client_ip)


    def dataReceived(self, data):

        # First 32 bytes received is client uuid
        if len(self.client_uuid) < 32:
            n_read = 32 - len(self.client_uuid)
            self.client_uuid += data[:n_read]
            data = data[n_read:]

        # If this is valid client, store client transport
        if len(self.client_uuid) == 32:
            client_info = address_map_get(self.client_ip, self.client_uuid)
            if client_info is None:
                self.transport.loseConnection()
                return

            elif 'transport' not in client_info:
                address_map_put(self.client_ip, self.client_uuid, None, self.transport)

                print 'AnsibleTransport: {}/{}'.format(self.client_ip, self.client_uuid)
                pprint(address_map)

        if len(data) == 0:
            return

        channel = client_info['channel']
        ansible = ansible_map[channel]
        if ('sender' in ansible) and (ansible['sender'] == (self.client_ip, self.client_uuid)):
            receiver_ip, receiver_uuid = ansible['receiver']
            receiver_info = address_map_get(receiver_ip, receiver_uuid)
            receiver_info['transport'].write(data)


class AnsibleTransportFactory(protocol.Factory):
    def __init__(self):
        self.numProtocols = 0

    def buildProtocol(self, addr):
        return AnsibleTransport(self)


# Reactor
endpoint = endpoints.TCP4ServerEndpoint(reactor, ANSIBLE_PORT_WEB)
endpoint.listen(server.Site(AnsibleWeb()))

endpoint = endpoints.TCP4ServerEndpoint(reactor, ANSIBLE_PORT_TRANSPORT)
endpoint.listen(AnsibleTransportFactory())

reactor.run()
