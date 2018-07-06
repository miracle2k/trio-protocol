class Loop:
    def __init__(self, nursery):
        self.nursery = nursery

    def create_task(self, task):
        async def wrapper():
            await task
        self.nursery.start_soon(wrapper)