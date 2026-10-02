"""
Minimal Qtile configuration fixture for headless/integration tests and demo.
Defines explicit numeric groups ('1'..'9') to avoid relying on
Qtile's built-in default config, with a top bar showing active groups.
"""
from libqtile.config import Group, Screen
from libqtile import layout, bar, widget

groups = [Group(str(i)) for i in range(1, 10)]
keys = []
layouts = [layout.Max()]
screens = [
    Screen(
        top=bar.Bar(
            [
                widget.GroupBox(
                    highlight_method="block",
                    active="#cdd6f4",
                    inactive="#6c7086",
                ),
                widget.Spacer(10),
                widget.WindowName(foreground="#89b4fa"),
            ],
            28,
            background="#11111b",
        )
    )
]
