import pytest

tk = pytest.importorskip("tkinter")


def test_window_builds_and_closes():
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display available")
    from ilfu.gui import App

    app = App(root, backend="fake")
    root.update()
    assert "I-L-F-U" in root.title()
    assert app.recorder is None
    root.destroy()
