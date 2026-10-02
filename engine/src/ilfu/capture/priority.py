"""Keep the app from disturbing a live call: transcription yields to other programs, while the
threads that write the audio get a little extra priority."""

from __future__ import annotations

import os
import sys


def lower_process_priority() -> None:
    """Run the whole app below normal priority so a video call always wins the CPU."""
    try:
        if sys.platform == "win32":
            import ctypes

            below_normal = 0x00004000  # BELOW_NORMAL_PRIORITY_CLASS
            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            kernel32.SetPriorityClass(kernel32.GetCurrentProcess(), below_normal)
        else:
            os.nice(5)
    except (OSError, AttributeError):
        pass


def boost_current_thread() -> None:
    """Give the audio writer thread a bit more priority than the transcription threads."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        kernel32.SetThreadPriority(kernel32.GetCurrentThread(), 2)  # THREAD_PRIORITY_HIGHEST
    except (OSError, AttributeError):
        pass
