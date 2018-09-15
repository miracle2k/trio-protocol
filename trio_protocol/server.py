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

    def __init__(self, listeners, nursery, cancel_scope):
        self._listeners = listeners
        self._nursery = nursery
        self._cancel_scope = cancel_scope
        self._closed = trio.Event()

    def close(self):
        """This causes the server to stop listening to new tasks.
        """
        self._cancel_scope.cancel()

    async def wait_closed(self):
        """This causes the server to stop listening to new tasks.
        """
        await self._closed.wait()

    @property
    def sockets(self):
        return [get_socket(l) for l in self._listeners]


async def create_server(nursery, protocol_factory, host=None, port=None, sock=None, 
                        ssl=None) -> Server:
    """This will spawn a task in `nursery` that listens to connections on 
    the given port or socket. For every incoming connection, a separate task
    will be spawned, and the `asyncio.Protocol` returned by `protocol_factory`
    will be used to manage the connection.

    The `create_server` function itself returns once the server is setup and
    ready for connections.

    This is the asyncio equivalent of `Loop.create_server` and
    `Loop.create_unix_server`.

    The return value is an instance of `Server`.
    """ 
    async def run_server(task_status=trio.TASK_STATUS_IGNORED):
        if sock:
            listeners = [trio.SocketListener(from_stdlib_socket(sock.sock))]
        else:
            if ssl:
                listeners = await trio.open_ssl_over_tcp_listeners(port, ssl, host=host)
            else:    
                listeners = await trio.open_tcp_listeners(port, host=host)

        # An outer nursery to run connection tasks in.
        server = None
        async with trio.open_nursery() as connection_nursery:
            # We can cancel serve_listeners() via this scope, without cancelling
            # the connection tasks.
            with trio.open_cancel_scope() as cancel_scope:
                server = Server(listeners=listeners, nursery=nursery, cancel_scope=cancel_scope)
                task_status.started(server)
                await trio.serve_listeners(
                    functools.partial(handle_connection, protocol_factory),
                    listeners,
                    handler_nursery=connection_nursery
                )
        if server is not None:
            server._closed.set()

    return await nursery.start(run_server)


async def run_server(protocol_factory, host, port):
    async with trio.open_nursery() as nursery:
        await create_server(nursery, protocol_factory, host, port)


async def handle_connection(protocol_factory, stream):
    """Called for a single, incoming connection to the server. If the
    connection ends, so does this function.
    """
    protocol = protocol_factory()
    transport = Transport(stream, protocol)

    protocol.connection_made(transport)

    async def read_proc():
        """Read from the socket and feed data to the protocol,
        as long as the protocol does not ask us to pause.
        """
        while True:
            # If we were paused, wait until we are unpaused.
            if transport._reading_paused:
                await transport._reading_resumed_event.wait()

            # Has close() been called? Read no more.
            if transport._should_close:
                return

            # Read a chunk of data
            data = await stream.receive_some(2**16)

            # EOF? The client closed the connection
            if not data:
                # Notify the protocol
                protocol_did_close = transport._protocol.eof_received()

                # if not protocol_did_close:
                #     pass
                # By calling close() we ensure the writer will also shutdown.
                transport.close()

                return

            # Fee data to the protocol
            else:
                transport._protocol.data_received(data)

    async def write_proc():
        while True:
            # Wait for data to be available
            await transport._can_write_event.wait()

            # If there is no data (and we are closed), end.
            if not transport._write_buffer and transport._should_close:
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
            await transport._should_cancel_event.wait()
            
            # If a read proc is hanging on read, this will end it.
            await stream.aclose()

    except Exception as e:
        await stream.aclose()
        transport._protocol.connection_lost(exc=e)
        raise
    finally:
        transport._protocol.connection_lost(exc=None)  