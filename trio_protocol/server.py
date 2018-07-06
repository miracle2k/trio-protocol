import trio
import functools
from .loop import Loop
from .transport import Transport


async def create_server(nursery, protocol_factory, host, port): 
    """Will start the server in the nursery.

    Returns when it is ready for connections.

    TODO: Implement this part, cannot use serve_tcp()
    TODO: Return a server object that can be used to stop everything
    """ 
    async def run_server(task_status=trio.TASK_STATUS_IGNORED):
        task_status.started()
        await trio.serve_tcp(functools.partial(handle_connection, nursery, protocol_factory), port)

    await nursery.start(run_server)


async def handle_connection(nursery, protocol_factory, stream):
    loop = Loop(nursery)
    protocol = protocol_factory(loop)
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
            await stream.send_all(transport.to_write)
            transport.to_write = b''
            transport.can_write_event.clear()

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
    finally:
        protocol.connection_lost(exc=None)  