"""The other side of gui/background.py: a function of the program (writing the
redacted copy, checking it) run in a process of its own, which sends back
what it returns, or the error it raised.

Nothing here uses Qt: the process imports only this and what the function needs.
"""

from __future__ import annotations


def run_and_send(conn, language: str, func, args: tuple) -> None:
    """Send through CONN (a pipe) (True, FUNC(*ARGS)), or (False, the error),
    with the interface in LANGUAGE, as in the window (for the error's text)."""
    from ..core import interface

    # El proceso nuevo arranca con el idioma por omisión; se fija el de la ventana para que el
    # texto de un error llegue en ese idioma.
    interface.use(language)
    try:
        answer = (True, func(*args))
    except BaseException as e:  # noqa: BLE001 (all of them go back to the window)
        answer = (False, e)
    try:
        conn.send(answer)
    # If pickling fails (an exception holding a file or a lock, say), only its text goes back.
    except Exception:  # (an error that can't be sent as it is)
        conn.send((False, RuntimeError(str(answer[1]))))
    conn.close()
