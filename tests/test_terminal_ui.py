import io

from wizcli.ui.terminal import TerminalUI

CLEAR = "\033[H\033[2J"


class FakeTTY(io.StringIO):
    def isatty(self) -> bool:
        return True


class Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def test_first_draw_true_second_false_until_interval():
    clock = Clock()
    ui = TerminalUI(min_interval=0.1, out=io.StringIO(), clock=clock)
    assert ui.draw("T", ["a"]) is True
    clock.t = 0.05
    assert ui.draw("T", ["a"]) is False
    clock.t = 0.1
    assert ui.draw("T", ["a"]) is True


def test_box_lines_have_equal_width():
    out = io.StringIO()
    TerminalUI(out=out, clock=Clock()).draw("Title", ["short", "a much longer line here"])
    rows = out.getvalue().splitlines()
    assert len(rows) == 4
    assert len({len(r) for r in rows}) == 1
    assert rows[0].startswith("┌─ Title ") and rows[0].endswith("┐")
    assert rows[-1].startswith("└") and rows[-1].endswith("┘")
    assert all(r.startswith("│") and r.endswith("│") for r in rows[1:-1])


def test_long_title_still_equal_width():
    out = io.StringIO()
    TerminalUI(out=out, clock=Clock()).draw("A very long title indeed", ["x"])
    assert len({len(r) for r in out.getvalue().splitlines()}) == 1


def test_no_ansi_when_not_a_tty():
    out = io.StringIO()
    ui = TerminalUI(out=out, clock=Clock())
    ui.draw("T", ["a"])
    ui.clear()
    assert "\033" not in out.getvalue()
    assert "┌" in out.getvalue()


def test_clear_sequence_when_tty():
    out = FakeTTY()
    ui = TerminalUI(out=out, clock=Clock())
    ui.clear()
    assert out.getvalue() == CLEAR
    out.truncate(0)
    out.seek(0)
    ui.draw("T", ["a"])
    assert out.getvalue().startswith(CLEAR + "┌")


def test_defaults_to_current_stdout(capsys):
    TerminalUI(clock=Clock()).draw("T", ["a"])
    assert "┌" in capsys.readouterr().out
