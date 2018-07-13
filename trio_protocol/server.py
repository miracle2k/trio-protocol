import trio
from trio.socket import from_stdlib_socket
import functools
from .loop import Loop
from .transport import Transport



def get_socket(listener):
    if hasattr(listener, 'transport_listener'):
        listener = listener.transport_listener
    return listener.socket


class Server:
    """
    Emulates the interface of:
    https://docs.python.org/3/library/asyncio-eventloop.html#asyncio.Server
    """

    def __init__(self, listeners, nursery):
        self._listeners = listeners
        self._nursery = nursery

    def close(self):
        # TODO: This will shutdown the server, but, apparently, not the server_listeners()
        # task!
        for l in self._listeners:
            self._nursery.start_soon(l.aclose)

    @property
    def sockets(self):
        return [get_socket(l) for l in self._listeners]


async def create_server(nursery, protocol_factory, host=None, port=None, sock=None, ssl=None):
    """Will start the server in the nursery.

    Returns when it is ready for connections.
    """ 
    async def run_server(task_status=trio.TASK_STATUS_IGNORED):
        if sock:
            listeners = [trio.SocketListener(from_stdlib_socket(sock.sock))]
        else:
            if ssl:
                listeners = await trio.open_ssl_over_tcp_listeners(port, ssl, host=host)
            else:    
                listeners = await trio.open_tcp_listeners(port, host=host)

        server = Server(listeners=listeners, nursery=nursery)
        task_status.started(server)

        await trio.serve_listeners(
            functools.partial(handle_connection, protocol_factory),
            listeners)

    return await nursery.start(run_server)


async def run_server(protocol_factory, host, port):
    async with trio.open_nursery() as nursery:
        await create_server(nursery, protocol_factory, host, port)


async def handle_connection(protocol_factory, stream):
    protocol = protocol_factory()
    transport = Transport(stream)

    protocol.connection_made(transport)

    async def read_proc():
        """Read from the socket and feed data to the protocol,
        as long as the protocol does not ask us to pause.
        """
        while True:
            # If we were paused, wait until we are unpaused.
            if not transport.can_read:
                await transport.can_read_event.wait()

            # Has close() been called? Read no more.
            if transport.should_close:
                return

            # Read a chunk of data
            data = await stream.receive_some(2**16)

            # EOF? The client closed the connection
            if not data:
                # Notify the protocol
                protocol_did_close = protocol.eof_received()

                # if not protocol_did_close:
                #     pass
                # By calling close() we ensure the writer will also shutdown.
                transport.close()

                return

            # Fee data to the protocol
            else:
                protocol.data_received(data)

    async def write_proc():
        while True:
            # Wait for data to be available
            await transport.can_write_event.wait()

            # If there is no data (and we are closed), end.
            if not transport.to_write and transport.should_close:
                return

            # Write the data and reset.
            data = transport._get_and_clear_write_buffer()
            await stream.send_all(data)

    try:
        async with trio.open_nursery() as nursery:
            # Start a read and a write proc
            nursery.start_soon(read_proc)
            nursery.start_soon(write_proc)

            # Wait until the connection is closed.
            await transport.should_cancel_event.wait()
            
            # If a read proc is hanging on read, this will end it.
            await stream.aclose()

    except Exception as e:
        await stream.aclose()
        protocol.connection_lost(exc=e)
        raise
    finally:
        protocol.connection_lost(exc=None)  