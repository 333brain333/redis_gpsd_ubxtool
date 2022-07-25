"""A thread-safe priority queue keeping its elements unique
"""

import collections
import threading
from typing import DefaultDict, Deque, Set, Generic, TypeVar

T = TypeVar('T')


class OrderedSetPriorityQueue(Generic[T]):
    """A thread-safe priority queue keeping its elements unique"""

    def __init__(self, maxlen:int = 0) -> None:
        self.maxlen = maxlen
        self._deques: DefaultDict[int, Deque[T]] = \
            collections.defaultdict(collections.deque)
        self._elem_sets: DefaultDict[int, Set[T]] = \
            collections.defaultdict(set)
        self._lock = threading.Condition(threading.RLock())

    def __contains__(self, item: T) -> bool:
        """Check if the item is already queued."""
        with self._lock:
            for elem_set in self._elem_sets.values():
                if item in elem_set:
                    return True
            return False

    def contains(self, item: T, priority: int) -> bool:
        """Check if the item is already queued with this exact priority."""
        with self._lock:
            if priority not in self._elem_sets:
                return False
            return item in self._elem_sets[priority]

    def discard(self, item: T) -> bool:
        """Remove an item from the queue, disregarding its stored priority."""
        with self._lock:
            if item not in self:
                return False
            removed_count = 0
            for set_prio, elem_set in self._elem_sets.items():
                if item in elem_set:
                    self._deques[set_prio].remove(item)
                    elem_set.remove(item)
                    removed_count += 1
            assert removed_count in (0, 1)
            self._clean_up()
            return removed_count > 0

    def insert(self, item: T, priority: int = 0) -> bool:
        """Returns False if item already is queued with the same priority.
        If is has not been queued yet, it is added and True is returned.
        If it already was queued but with a different priority,
        the entry with the old priority will be removed,
        and the new one is added."""
        with self._lock:
            if self.contains(item, priority) or self.__len__() == self.maxlen:
                return False
            self.discard(item)
            self._deques[priority].appendleft(item)
            self._elem_sets[priority].add(item)
            self._lock.notify()
            return True

    def __bool__(self) -> bool:
        """True if the queue is not empty."""
        with self._lock:
            assert bool(self._elem_sets) == bool(self._deques)
            return bool(self._elem_sets)

    def __len__(self) -> int:
        """Number of elements in the queue."""
        with self._lock:
            return sum(map(len, self._elem_sets.values()))

    def pop(self) -> T:
        """Pop the oldest item from the highest priority."""
        if self.__len__() == 0:
            raise IndexError 
        with self._lock:
            while not self._elem_sets:
                self._lock.wait()
            priority = sorted(self._deques.keys())[-1]
            item = self._deques[priority].pop()
            self._elem_sets[priority].remove(item)
            self._clean_up()
            return item

    def _clean_up(self) -> None:
        """Internal function used to clean up unused data structures."""
        with self._lock:
            assert sorted(self._deques.keys()) == sorted(self._elem_sets.keys())
            priorities = list(self._elem_sets.keys())
            for priority in priorities:
                if not self._deques[priority]:
                    del self._deques[priority]
                if not self._elem_sets[priority]:
                    del self._elem_sets[priority]