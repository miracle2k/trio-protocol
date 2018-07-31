import asyncio


UNSET = object()


class Task:

    def __init__(self):
        self._done_callbacks = []
        self._cancelled = False
        self._result = UNSET
        self._exception = None
        self._cancel_scope = None

    def add_done_callback(self, callback):
        self._done_callbacks.append(callback)

    def done(self):
        return bool(self._result is not UNSET or self._exception or self._cancelled)

    def cancelled(self):
        return self._done

    def exception(self):
        if self._cancelled:
            raise asyncio.CancelledError()
        if not self._exception:
            raise InvalidStateError()
        return self._exception

    def cancel(self):
        if self.done():
            return False

        self._cancel_scope.cancel()
        return True


def task_set_result(task: Task, result):
    task._result = result
    for callback in task._done_callbacks:
        callback(task)


def task_set_exception(task: Task, exception):
    task._exception = exception
    for callback in task._done_callbacks:
        callback(task)


def task_set_cancelled(task: Task, exception):
    task._cancelled = True
    for callback in task._done_callbacks:
        callback(task)
