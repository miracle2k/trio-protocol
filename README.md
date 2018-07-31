# trio-protocol

This implements the `asyncio.Transport` interface and foundational asyncio classes sucsh as `asyncio.Task` on top of [`trio`](https://github.com/python-trio/trio), to aid porting `asyncio` libraries. The idea is to allow `trio` to run an [`asyncio.Protocol`](https://docs.python.org/3/library/asyncio-protocol.html#protocols), making it possible for a single code base to run on both frameworks.

It is **not a goal** of `trio-protocol` to let you run `asyncio` code on `trio` without any changes. If you need this, look at [`asyncio-trio`](https://github.com/python-trio/trio-asyncio).


#### What is and is not currently supported

This is an early version. You can use it to support some basic `asyncio` servers. However, it lacks:

- Support for clients (only servers have been tested)
- A test suite.
- Robust experience running it in production.
- Likely, implementations for useful/necessary methods that asyncio code is using in the wild, and should be added.


## Usage

Let's say you want to run the [`asyncio-len-prefixed-string-protocol.py` from the python3-samples repository](https://github.com/eliben/python3-samples/blob/master/async/asyncio-len-prefixed-string-protocol.py) on top of `trio`. 

If you follow the link, you see that the module first implements subclass of `asyncio.Protocol`, which it then subclasses further. Ultimately, the protocol as implemented reads strings from the client, prefixed by length, and sends back an `"ok"` message.

At the bottom of the file, you'll find the following code to start the server:

```python
loop = asyncio.get_event_loop()
coro = loop.create_server(MyStringReceiver, '127.0.0.1', 5566)
server = loop.run_until_complete(coro)
print('serving on {}'.format(server.sockets[0].getsockname()))

try:
    loop.run_forever()
except KeyboardInterrupt:
    print("exit")
finally:
    server.close()
    loop.close()
```

This creates an `asyncio` server running on port `5566`. Every connection to that port will be served by the `MyStringReceiver` protocol. Specifically, `loop.create_server()` will setup the server's socket (since it is an `async` function, it will not do anything until awaited, which in this case we do via `loop.run_until_complete`). Whenever someone connects to the server, asyncio will schedule a task to handle the connection. We run `loop.run_forever()` to have the loop be active and process these tasks.

Now let's run this on `trio` instead. Replace this section of the code with:

```python
import trio
from trio_protocol import run_server

trio.run(run_server, MyStringReceiver, '127.0.0.1', 5566)
```

And that would work! The code is a bit shorter than the original, partly because setting up trio is just less verbose, and partly because we do less: We do not handle `KeyboardInterrupt` cleanly, and we do not print a message once we are ready to accept connections. Instead, `trio_protocol.run_server` is a shortcut that does everything for us: It opens a nursery, starts a server, and runs the `asyncio.Protocol` on that server.

If we want to copy the original code more exactly, I can do this:

```python
import trio
from trio_protocol import create_server

async def run_server():
    async with trio.open_nursery() as nursery:
         server = await create_server(nursery, MyStringReceiver, '127.0.0.1', 5566)
         print('serving on {}'.format(server.sockets[0].getsockname()))

try:
    trio.run(run_server)
except KeyboardInterrupt:
    print("exit")
```

```trio_protocol.create_server``` will start listening on the socket. It will return a `trio_protocol.Server` object that is intended to mirror `asyncio.Server`. You are then free to run your own code, with the server running in the background, similar to the `asyncio` version.

>>> Note: To test this server, you can use:
>>> `python -c "import struct; print((b'%shello world' % struct.pack('<L', 12)).decode('ascii'))" | nc localhost 5566`


### What if the protocol needs access to the loop

If the protocol uses the `asyncio` loop, for example to start background tasks, you can use `trio_protocol.Loop` which is a loop-like class that supports some of the commonly used methods such as `call_later` or `create_task`. Most protocols are written to accept a `loop` argument, so you would do:

```python
import functools
import trio
from trio_protocol import Loop, run_server

async def run_server():
    async with trio.open_nursery() as nursery:
        loop = Loop(nursery)
        protocol_factory = functools.partial(MyProtocol, loop=loop)
        await create_server(nursery, protocol_factory, '127.0.0.1', 5566)

trio.run(run_server)
```

Background task the protocol want to spawn now run within the nursery given to `trio_protocol.Loop`.

Note: It is strictly a requirement that the protocol class you want to run uses an explicit loop. Most `asyncio` interfaces are written in such a way that when an explicit loop is not passed, the current global loop will be used automatically. This won't work, because you would end up using the `asyncio` loop.
