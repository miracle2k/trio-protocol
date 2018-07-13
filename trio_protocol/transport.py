import trio


class Transport:
    """In `asyncio` every protocol has access to transport. It can use that
    transport to write data, and to interact with flow control, as well as
    close the connection. `asyncio`  has background tasks that will handle 
    the requested actions.

    We do the same thing. This class implements the same interfae as an
    `asyncio` transport. Protocols do not understand they are not running on
    top of `asyncio`.
    """

    def __init__(self, stream):
        self.stream = stream

        self.should_close = False
        self.can_read = True
        self.can_read_event = None
        self.can_write_event = trio.Event()
        self.should_cancel_event = trio.Event()

        self.to_write = b''

    def write(self, data):
        if not data:
            return

        self.to_write += data
        self.can_write_event.set()

        # TODO
        # if too much buffer, call pause writing
        # when buffer consumed, call resume writing

    def _get_and_clear_write_buffer(self):
        data = self.to_write
        self.to_write = b''
        self.can_write_event.clear()
        return data

    def pause_reading(self):
        # Protocol asks us to stop reading
        self.can_read = False
        self.can_read_event = trio.Event()

    def resume_reading(self):
        self.can_read_event.set()

    def get_extra_info(self, key: str):
        if key == 'sockname':
            return ("", "")
        if key == 'peername':
            return ("", "")

    def close(self):
        """We are being asked to close the connection.
        """
        self.should_close = True
        self.should_cancel_event.set()

        # Make sure the read proc stops waiting
        if self.can_read_event:
            self.can_read_event.set()
        self.can_write_event.set()