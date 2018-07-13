class Loop:
    """This implements those parts of the asyncio Loop API that are
    likely to be used within a protocol implementation.

    This includes starting tasks, which in trio can only be done within
    the context of a nursery. For this reason, our version of the Loop
    needs access to a trio nursery.
    """
    def __init__(self, nursery):
        self.nursery = nursery

    def create_task(self, task):
        async def wrapper():
            await task
        self.nursery.start_soon(wrapper)