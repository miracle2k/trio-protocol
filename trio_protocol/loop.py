import trio
import inspect
from .task import Task, task_set_result, task_set_cancelled, task_set_exception


class Loop:
    """This implements those parts of the asyncio Loop API that are
    likely to be used within a protocol implementation.

    This includes starting tasks, which in trio can only be done within
    the context of a nursery. For this reason, our version of the Loop
    needs access to a trio nursery.
    """
    def __init__(self, nursery):
        self.nursery = nursery

    def stop(self):
        """Will cancel the cancel_scope of the nursery the loop is bound to.
        """
        self.nursery.cancel_scope.cancel()

    def call_later(self, seconds, async_func, *args) -> Task:
        """Call `async_func` after `seconds`. Returns a `asyncio.Task`
        like interface which allows to cancel the callback.
        """
        async def timeout_then_call():
            await trio.sleep(seconds)
            async_func(*args)
        return self.create_task(timeout_then_call)

    def create_task(self, async_func) -> Task:
        """Spawn `async_func` as a background task in the loop nursery,
        and return a `Task` object with a similar interface as `asyncio.Task`.
        """
        task = Task()
        async def task_wrapper():
            with trio.open_cancel_scope() as scope:
                task._cancel_scope = scope

                try:
                    if inspect.iscoroutine(async_func):
                        result = await async_func
                    else:
                        result = await async_func()
                except Exception as e:
                    task_set_exception(task, e)
                    return

            if scope.cancelled_caught:
                task_set_cancelled(task)
            else:
                task_set_result(task, result)

        self.nursery.start_soon(task_wrapper)
        return task