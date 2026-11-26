"""Failures as return values, without classes that carry state.

A function that can fail for an expected reason returns either its value or a Failure. A Failure is a str subclass
without attributes: its text is the reason. A caller tests the result with isinstance(result, Failure) before it uses
the value. Nothing returns None, and nothing raises for an expected bad input.
"""

from __future__ import annotations

from typing import Callable, TypeVar, Union

T = TypeVar("T")
U = TypeVar("U")


class Failure(str):
    """The reason a function failed, as text. It has no attributes: the text is all there is."""


def failed(reason: str) -> Failure:
    """A failure with its reason."""
    return Failure(reason)


def then(result: Union[T, Failure], function: Callable[[T], U]) -> Union[U, Failure]:
    """Applies the function to a value; a failure passes through unchanged."""
    if isinstance(result, Failure):
        return result
    return function(result)
