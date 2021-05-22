from .Printable import Printable
from .Network import Network
from .enums import NodeRole
from .Registry import Registrable
from .Emulator import Emulator
from .Configurable import Configurable
from .enums import NetworkType
from ipaddress import IPv4Address, IPv4Interface
from typing import List, Dict, Set, Tuple
from string import ascii_letters
from random import choice

DEFAULT_SOFTWARES: List[str] = ['curl', 'nano', 'vim-nox', 'mtr-tiny', 'iproute2', 'iputils-ping', 'tcpdump', 'termshark', 'dnsutils', 'jq', 'ipcalc']

class File(Printable):
    """!
    @brief File class.

    This class represents a file on a node.
    """

    __content: str
    __path: str

    def __init__(self, path: str, content: str = ''):
        """!
        @brief File constructor.

        Put a file onto a node.

        @param path path of the file.
        @param content content of the file.
        """
        self.__path = path
        self.__content = content

    def setPath(self, path: str):
        """!
        @brief Update file path.

        @param path new path.
        """
        self.__path = path

    def setContent(self, content: str):
        """!
        @brief Update file content.

        @param content content.
        """
        self.__content = content

    def appendContent(self, content: str):
        """!
        @brief Append to file.

        @param content content.
        """
        self.__content += content

    def get(self) -> Tuple[str, str]:
        """!
        @brief Get file path and content.

        @returns a tuple where the first element is path and second element is 
        content
        """
        return (self.__path, self.__content)

    def print(self, indent: int) -> str:
        out = ' ' * indent
        out += "{}:\n".format(self.__path)
        indent += 4
        for line in self.__content.splitlines():
            out += ' ' * indent
            out += '> '
            out += line
            out += '\n'
        return out

class Interface(Printable):
    """!
    @brief Interface class.

    This class represents a network interface card.
    """

    __network: Network
    __address: IPv4Address

    __latency: int       # in ms
    __bandwidth: int     # in bps
    __drop: float        # percentage

    def __init__(self, net: Network):
        """!
        @brief Interface constructor.

        @param net network to connect to.
        """
        self.__address = None
        self.__network = net
        (l, b, d) = net.getDefaultLinkProperties()
        self.__latency = l
        self.__bandwidth = b
        self.__drop = d

    def setLinkProperties(self, latency: int = 0, bandwidth: int = 0, packetDrop: float = 0):
        """!
        @brief Set link properties.

        @param latency (optional) latency to add to the link in ms, default 0.
        @param bandwidth (optional) egress bandwidth of the link in bps, 0 for unlimited, default 0.
        @param packetDrop (optional) link packet drop as percentage, 0 for unlimited, default 0.
        """

        assert latency >= 0, 'invalid latency'
        assert bandwidth >= 0, 'invalid bandwidth'
        assert packetDrop >= 0 and packetDrop <= 100, 'invalid packet drop'

        self.__latency = latency
        self.__bandwidth = bandwidth
        self.__drop = packetDrop

    def getLinkProperties(self) -> Tuple[int, int, int]:
        """!
        @brief Get link properties.

        @returns tuple (latency, bandwidth, packet drop)
        """
        return (self.__latency, self.__bandwidth, self.__drop)

    def getNet(self) -> Network:
        """!
        @brief Get the network that this interface attached to.

        @returns network.
        """
        return self.__network

    def setAddress(self, address: IPv4Address):
        """!
        @brief Set IPv4 address of this interface.

        @param address address.
        """
        self.__address = address

    def getAddress(self):
        """!
        @brief Get IPv4 address of this interface.

        @returns address.
        """
        return self.__address

    def print(self, indent: int) -> str:
        out = ' ' * indent
        out += 'Interface:\n'

        indent += 4
        out += ' ' * indent
        out += 'Connected to: {}\n'.format(self.__network.getName())
        out += ' ' * indent
        out += 'Address: {}\n'.format(self.__address)
        out += ' ' * indent
        out += 'Link Properties: {}\n'.format(self.__address)

        indent += 4
        out += ' ' * indent
        out += 'Added Latency: {} ms\n'.format(self.__latency)
        out += ' ' * indent
        out += 'Egress Bandwidth Limit: {} bps\n'.format('unlimited' if self.__bandwidth <= 0 else self.__bandwidth)

        return out

class Node(Printable, Registrable, Configurable):
    """!
    @brief Node base class.

    This class represents a generic node.
    """

    __name: str
    __asn: int
    __scope: str
    __role: NodeRole
    __interfaces: List[Interface]
    __files: Dict[str, File]
    __softwares: Set[str]
    __build_commands: List[str]
    __start_commands: List[Tuple[str, bool]]
    __ports: List[Tuple[int, int, str]]
    __privileged: bool
    __common_software: Set[str]

    __configured: bool
    __pending_nets: List[Tuple[str, str]]
    __xcs: Dict[Tuple[str, int], Tuple[IPv4Interface, str]]

    def __init__(self, name: str, role: NodeRole, asn: int, scope: str = None):
        """!
        @brief Node constructor.

        @name name name of this node.
        @param role role of this node.
        @param asn network that this node belongs to.
        @param scope scope of the node, if not asn.
        """
        self.__interfaces = []
        self.__files = {}
        self.__asn = asn
        self.__role = role
        self.__name = name
        self.__scope = scope if scope != None else str(asn)
        self.__softwares = set()
        self.__common_software = set()
        self.__build_commands = []
        self.__start_commands = []
        self.__ports = []
        self.__privileged = False

        self.__pending_nets = []
        self.__xcs = {}
        self.__configured = False

        for soft in DEFAULT_SOFTWARES:
            self.__common_software.add(soft)

    def configure(self, emulator: Emulator):
        """!
        @brief configure the node. This is called when rendering.

        NICs will be setup during the configuring procress. No new interfaces
        can be added after configuration.

        @param emulator Emulator object to use to configure.
        """
        assert not self.__configured, 'Node already configured.'

        reg = emulator.getRegistry()

        for (netname, address) in self.__pending_nets:

            hit = False

            if reg.has(self.__scope, "net", netname):
                hit = True
                self.__joinNetwork(reg.get(self.__scope, "net", netname), address)

            if not hit and reg.has("ix", "net", netname):
                hit = True
                self.__joinNetwork(reg.get("ix", "net", netname), address)

            assert hit, 'no network matched for name {}'.format(netname)

        for (peername, peerasn) in list(self.__xcs.keys()):
            peer: Node = None

            if reg.has(str(peerasn), 'rnode', peername): peer = reg.get(str(peerasn), 'rnode', peername)
            elif reg.has(str(peerasn), 'hnode', peername): peer = reg.get(str(peerasn), 'hnode', peername)
            else: assert False, 'as{}/{}: cannot xc to node as{}/{}: no such node'.format(self.getAsn(), self.getName(), peerasn, peername)

            (peeraddr, netname) = peer.getCrossConnect(self.getAsn(), self.getName())
            (localaddr, _) = self.__xcs[(peername, peerasn)]
            assert localaddr.network == peeraddr.network, 'as{}/{}: cannot xc to node as{}/{}: {}.net != {}.net'.format(self.getAsn(), self.getName(), peerasn, peername, localaddr, peeraddr)

            if netname != None:
                self.__joinNetwork(reg.get('xc', 'net', netname), str(localaddr.ip))
                self.__xcs[(peername, peerasn)] = (localaddr, netname)
            else:
                # netname = 'as{}.{}_as{}.{}'.format(self.getAsn(), self.getName(), peerasn, peername)
                netname = ''.join(choice(ascii_letters) for i in range(10))
                net = Network(netname, NetworkType.CrossConnect, localaddr.network)
                self.__joinNetwork(reg.register('xc', 'net', netname, net), str(localaddr.ip))
                self.__xcs[(peername, peerasn)] = (localaddr, netname)

    def addPort(self, host: int, node: int, proto: str = 'tcp'):
        """!
        @brief Add port forwarding.

        @param host port of the host.
        @param node port of the node.
        @param proto protocol.
        """
        self.__ports.append((host, node, proto))

    def getPorts(self) -> List[Tuple[int, int]]:
        """!
        @brief Get port forwardings.

        @returns list of tuple of ports (host, node).
        """
        return self.__ports

    def setPrivileged(self, privileged: bool):
        """!
        @brief Set or unset the node as privileged node.

        Some backend like Docker will require the container to be privileged
        in order to do some privileged operations.

        @param privileged (optional) set if node is privileged.
        """
        self.__privileged = privileged

    def isPrivileged(self) -> bool:
        """!
        @brief Test if node is set to privileged.

        @returns True if privileged, False otherwise.
        """
        return self.__privileged

    def __joinNetwork(self, net: Network, address: str = "auto"):
        """!
        @brief Connect the node to a network.
        @param net network to connect.
        @param address (optional) override address assigment.

        @throws AssertionError if network does not exist.
        """
        
        if address == "auto": _addr = net.assign(self.__role, self.__asn)
        else: _addr = IPv4Address(address)

        _iface = Interface(net)
        _iface.setAddress(_addr)

        self.__interfaces.append(_iface)
        
        net.associate(self)

    def joinNetwork(self, netname: str, address: str = "auto"):
        """!
        @brief Connect the node to a network.
        @param netname name of the network.
        @param address (optional) override address assigment.

        @returns assigned IP address
        @throws AssertionError if network does not exist.
        """
        assert not self.__configured, 'Node already configured.'

        self.__pending_nets.append((netname, address))

    def crossConnect(self, peerasn: int, peername: str, address: str):
        """!
        @brief create new p2p cross-connect connection to a remote node.
        @param peername node name of the peer node.
        @param peerasn asn of the peer node.
        @param address address to use on the interface in CIDR notiation. Must
        be within the same subnet.
        """
        assert peername != self.getName() or peerasn != self.getName(), 'cannot XC to self.'
        self.__xcs[(peername, peerasn)] = (IPv4Interface(address), None)

    def getCrossConnect(self, peerasn: int, peername: str) -> Tuple[IPv4Interface, str]:
        """!
        @brief retrieve IP address for the given peer.
        @param peername node name of the peer node.
        @param peerasn asn of the peer node.

        @returns tuple of IP address and XC network name. XC network name will
        be None if the network has not yet been created.
        """
        assert (peername, peerasn) in self.__xcs, 'as{}/{} is not in the XC list.'.format(peerasn, peername)
        return self.__xcs[(peername, peerasn)]

    def getCrossConnects(self) -> Dict[Tuple[str, int], Tuple[IPv4Interface, str]]:
        """!
        @brief get all cross connects on this node.

        @returns dict, where key is (peer node name, peer node asn) and value is (address on interface, netname)
        """
        return self.__xcs

    def getName(self) -> str:
        """!
        @brief Get node name.

        @returns name.
        """
        return self.__name

    def getAsn(self) -> int:
        """!
        @brief Get node parent AS ASN.

        @returns asm.
        """
        return self.__asn

    def getRole(self) -> NodeRole:
        """!
        @brief Get role of current node.

        Get role type of current node. 

        @returns role.
        """
        return self.__role

    def getFile(self, path: str) -> File:
        """!
        @brief Get a file object, and create if not exist.

        @param path file path.
        @returns file.
        """
        if path in self.__files: return self.__files[path]
        self.__files[path] = File(path)
        return self.__files[path]

    def getFiles(self) -> List[File]:
        """!
        @brief Get all files.

        @return list of files.
        """
        return self.__files.values()

    def setFile(self, path: str, content: str):
        """!
        @brief Set content of the file.

        @param path path of the file. Will be created if not exist, and will be
        override if already exist.
        @param content file content.
        """
        self.getFile(path).setContent(content)

    def appendFile(self, path: str, content: str):
        """!
        @brief Append content to a file.

        @param path path of the file. Will be created if not exist.
        @param content content to append.
        """
        self.getFile(path).appendContent(content)

    def addSoftware(self, name: str):
        """!
        @brief Add new software to node.

        @param name software package name.

        Use this to add software to the node. For example, if using the "docker"
        compiler, this will be added as an "apt-get install" line in Dockerfile.
        """
        self.__softwares.add(name)

    def getSoftwares(self) -> Set[str]:
        """!
        @brief Get set of software.

        @returns set of softwares.
        """
        return self.__softwares

    def getCommonSoftware(self) -> Set[str]:
        """!
        @brief Get set of common software.

        @returns set of softwares.
        """
        return self.__common_software

    def addBuildCommand(self, cmd: str):
        """!
        @brief Add new command to build step.

        @param cmd command to add.

        Use this to add build steps to the node. For example, if using the
        "docker" compiler, this will be added as a "RUN" line in Dockerfile.
        """
        self.__build_commands.append(cmd)
    
    def getBuildCommands(self) -> List[str]:
        """!
        @brief Get build commands.

        @returns list of commands.
        """
        return self.__build_commands

    def insertStartCommand(self, index: int, cmd: str, fork: bool = False):
        """!
        @brief Add new command to start script.

        The command should not be a blocking command. If you need to run a
        blocking command, set fork to true and fork it to the background so
        that it won't block the execution of other commands.

        @param cmd command to add.
        @param fork (optional) fork to command to background?

        Use this to add start steps to the node. For example, if using the
        "docker" compiler, this will be added to start.sh.
        """
        self.__start_commands.insert(index, (cmd, fork))

    def appendStartCommand(self, cmd: str, fork: bool = False):
        """!
        @brief Add new command to start script.

        The command should not be a blocking command. If you need to run a
        blocking command, set fork to true and fork it to the background so
        that it won't block the execution of other commands.

        @param cmd command to add.
        @param fork (optional) fork to command to background?

        Use this to add start steps to the node. For example, if using the
        "docker" compiler, this will be added to start.sh.
        """
        self.__start_commands.append((cmd, fork))

    def getStartCommands(self) -> List[Tuple[str, bool]]:
        """!
        @brief Get start commands.

        @returns list of tuples, where the first element is command, and the
        second element indicates if this command should be forked.
        """
        return self.__start_commands

    def getInterfaces(self) -> List[Interface]:
        """!
        @brief Get list of interfaces.

        @returns list of interfaces.
        """
        return self.__interfaces
        
    def print(self, indent: int) -> str:
        out = ' ' * indent
        out += 'Node {}:\n'.format(self.__name)

        indent += 4
        out += ' ' * indent
        out += 'Role: {}\n'.format(self.__role)
        out += ' ' * indent

        out += 'Interfaces:\n'
        for interface in self.__interfaces:
            out += interface.print(indent + 4)

        out += ' ' * indent
        out += 'Files:\n'
        for file in self.__files.values():
            out += file.print(indent + 4)

        out += ' ' * indent
        out += 'Software:\n'
        indent += 4
        for software in self.__softwares:
            out += ' ' * indent
            out += '{}\n'.format(software)
        indent -= 4

        out += ' ' * indent
        out += 'Additional Build Commands:\n'
        indent += 4
        for cmd in self.__build_commands:
            out += ' ' * indent
            out += '{}\n'.format(cmd)
        indent -= 4

        out += ' ' * indent
        out += 'Additional Start Commands:\n'
        indent += 4
        for (cmd, fork) in self.__start_commands:
            out += ' ' * indent
            out += '{}{}\n'.format(cmd, ' (fork)' if fork else '')
        indent -= 4

        return out