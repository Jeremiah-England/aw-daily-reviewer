# ruff: noqa: TD001, TD002, TD003, FIX002
"""A small little script to print out a summary of what I did today from the activity logged in ActivityWatch."""

import tkinter as tk

from aw_client.client import ActivityWatchClient

from aw_daily_reviewer.core import ActivityWatchCleaner
from aw_daily_reviewer.gui import MainWindow

root = tk.Tk()


def main():
    with ActivityWatchClient("aw-daily-reviewer") as client:
        cleaner = ActivityWatchCleaner(client)
        MainWindow(root, cleaner).grid()
        root.mainloop()


if __name__ == "__main__":
    main()
