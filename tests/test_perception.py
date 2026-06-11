from understudy.perception.snapshot import count_actionable, new_lines

ARIA_FIXTURE = """\
- banner:
  - heading "The Flickering Reach" [level=1]
- main:
  - log: You stand at the gate of the settlement.
  - textbox "Action"
  - button "Send"
  - button "Roll"
- contentinfo:
  - text: turn 3
"""

NO_CONTROLS = """\
- main:
  - heading "Loading" [level=2]
  - text: please wait
"""


def test_count_actionable_finds_controls():
    assert count_actionable(ARIA_FIXTURE) == 3  # textbox + 2 buttons


def test_count_actionable_zero_on_dead_screen():
    assert count_actionable(NO_CONTROLS) == 0


def test_new_lines_returns_only_fresh_content():
    after = ARIA_FIXTURE + '  - log: A guard approaches you.\n'
    delta = new_lines(ARIA_FIXTURE, after)
    assert "A guard approaches you." in delta
    assert "You stand at the gate" not in delta


def test_new_lines_empty_when_nothing_changed():
    assert new_lines(ARIA_FIXTURE, ARIA_FIXTURE) == ""
