"""See:

https://github.com/python/cpython/blob/master/Lib/asyncio/transports.py
"""

import trio


class FlowControlMixin:
    """We could have, very reasonably, used the asyncio version of this, which 
    we can import from asyncio.transports._FlowControlMixin. I chose to copy the
    code here for a couple of reasons:

    - It may well break in the future.

    - It has a number of requirements on our subclass (such as the existance
      of the self._protocol field), and it might be easier to have all this stuff
      together in one place.

    - It has some idiosyncrasies, such as hiding all exceptions and calling 
      self._loop.call_exception_handler, which I am not sure we want to reproduce
      in trio.
    """

    def __init__(self, transport):
        self.transport = transport
        self.protocol_paused = False
        self.set_write_buffer_limits()

    @property
    def protocol(self):
        return self.transport._protocol

    def maybe_pause_protocol(self):
        size = self.transport.get_write_buffer_size()
        if size <= self._high_water:
            return
        if not self.protocol_paused:
            self.protocol_paused = True
            self.protocol.pause_writing()

    def maybe_resume_protocol(self):
        if (self.protocol_paused and
                self.transport.get_write_buffer_size() <= self._low_water):
            self.protocol_paused = False
            self.protocol.resume_writing()

    def get_write_buffer_limits(self):
        return (self._low_water, self._high_water)

    def _set_write_buffer_limits(self, high=None, low=None):
        if high is None:
            if low is None:
                high = 64 * 1024
            else:
                high = 4 * low
        if low is None:
            low = high // 4

        if not high >= low >= 0:
            raise ValueError(
                f'high ({high!r}) must be >= low ({low!r}) must be >= 0')

        self._high_water = high
        self._low_water = low

    def set_write_buffer_limits(self, high=None, low=None):
        self._set_write_buffer_limits(high=high, low=low)
        self.maybe_pause_protocol()


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

        self._should_close = False
        self._reading_paused = False
        self._reading_resumed_event = None
        self._can_write_event = trio.Event()
        self._should_cancel_event = trio.Event()

        self._write_buffer = b''
        self._write_flow = FlowControlMixin(self)

    def is_closing(self):
        if self._should_close:
            return True
        return False

    def write(self, data):
        if not data:
            return

        self._write_buffer += data
        self._can_write_event.set()
        self._write_flow.maybe_pause_protocol()

    def _get_and_clear_write_buffer(self):
        data = self._write_buffer
        self._write_buffer = b''
        self._can_write_event.clear()
        self._write_flow.maybe_resume_protocol()
        return data

    def get_write_buffer_limits(self):
        return self._write_flow.get_write_buffer_limits()

    def set_write_buffer_limits(self, high=None, low=None):
        self._write_flow.set_write_buffer_limits(high=high, low=low)

    def get_write_buffer_size(self):
        return len(self._write_buffer)

    def pause_reading(self):
        """Protocols can call this to tell us to stop reading data, if we are
        reading too much and too fast.

        We use an event and a flag to tell the background task to stop reading.
        """
        self._reading_paused = False
        self._reading_resumed_event = trio.Event()

    def resume_reading(self):
        """Protocols can call this to tell us to continue reading data, after
        previously having told us to stop.

        If reading was paused, the background task will be waiting on an event.
        Fullfill the event to signal to the task to continue.
        """
        if self._reading_resumed_event:
            self._reading_resumed_event.set()

    def get_extra_info(self, key: str):
        if key == 'sockname':
            return ("", "")
        if key == 'peername':
            return ("", "")

    def close(self):
        """Protocols can call this to tell us to stop the connection.
        """
        self._should_close = True
        self._should_cancel_event.set()

        # Make sure the read proc stops waiting
        if self._reading_resumed_event:
            self._reading_resumed_event.set()
        self._can_write_event.set()
  