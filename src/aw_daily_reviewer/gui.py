"""The tkinter GUI for the aw_daily_reviewer package."""
import datetime as dt
import logging
import tkinter as tk
from itertools import pairwise
from tkinter import messagebox, simpledialog, ttk

from aw_daily_reviewer.core import ActivityWatchCleaner

system_timezone = dt.datetime.now().astimezone().tzinfo


logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class ReviewTable(ttk.Treeview):
    def __init__(self, parent: tk.Frame, cleaner: ActivityWatchCleaner):
        self.cleaner = cleaner
        super().__init__(parent)

        # TODO: Add sorting by column
        # TODO: Add input for rating the value of an activity.
        # TODO: Add percentage for the percentage of the day spend on the activity.
        self["columns"] = ("time", "durration", "event")
        self.column("#0", width=59, stretch=False)
        self.column("time", width=100, stretch=False)
        self.column("durration", width=100, stretch=False)
        self.column("event", minwidth=500, width=500, stretch=False)

        self.heading("#0", text="")
        self.heading("time", text="Time")
        self.heading("durration", text="durration")
        self.heading("event", text="Event")

        self.insert("", tk.END, text="test", values=("test", "test", "test"))
        self.visual_mode = False
        self.previously_selected = None
        self.old_selection = set()
        self.bind("<<TreeviewSelect>>", lambda _: self.set_previously_selected())

        # Add some vim-like keybindings
        self.bind("<Double-g>", lambda _: self.go_to_top())
        self.bind("<G>", lambda _: self.go_to_bottom())
        # TODO: Add h/l to open/close the selected node.
        # TODO: Add i for insert/edit mode on a node. Would pop up a dialog to edit the event I think. (Though, inline would be nice.)
        self.bind("j", lambda _: self.select_next())
        self.bind("k", lambda _: self.select_previous())
        self.bind("v", lambda _: self.enter_visual_mode())
        self.bind("V", lambda _: self.enter_visual_mode())
        self.bind("<Double-z>", lambda _: self.center_selected())
        self.bind("<Double-d>", lambda _: self.remove_selected())
        self.bind("<Escape>", lambda _: self.leave_visual_mode())
        self.bind("zf", lambda _: self.group())

    def remove_selected(self):
        selected = self.selection()
        if selected:
            for node in selected:
                self.delete(node)
        self.select_next()  # TODO: Handle end of table case.

    def set_previously_selected(self):
        current_selections = set(map(int, self.selection()))
        if new_selections := current_selections - self.old_selection:
            if self.old_selection and max(new_selections) == max(self.old_selection):
                self.previously_selected = min(new_selections)
            else:
                self.previously_selected = max(new_selections)
        elif removed_selections := self.old_selection - current_selections:
            if self.previously_selected in removed_selections:
                if all(x < self.previously_selected for x in current_selections):
                    self.previously_selected = max(current_selections)
                elif all(x > self.previously_selected for x in current_selections):
                    self.previously_selected = min(current_selections)
                else:
                    self.previously_selected = None

        logger.debug(f"Selections: {current_selections} -- {self.previously_selected}")
        self.old_selection = current_selections

    def enter_visual_mode(self):
        self.visual_mode = True

    def leave_visual_mode(self):
        self.visual_mode = False

    def center_selected(self):
        # This doens't work.
        selected = self.selection()
        if selected:
            y1 = self.yview()[0]
            y2 = self.yview()[1]
            ypix = self.bbox(selected[0])[1]
            minypix = min(self.bbox(x)[1] for x in self.get_children() if self.bbox(x))
            maxypix = max(self.bbox(x)[1] for x in self.get_children() if self.bbox(x))
            fractional_position = (ypix - minypix) / (maxypix - minypix)  # pyright: ignore[reportGeneralTypeIssues]
            y_view_position = fractional_position * (y2 - y1) + y1
            y_view_position_top = y_view_position - (y2 - y1) / 2
            self.yview_moveto(y_view_position_top)

    def select_next(self):
        selected = self.selection()
        if selected:
            next_node = self.next(selected[-1])
            if next_node:
                if (
                    self.visual_mode
                    and str(self.previously_selected) == selected[-1]
                    or self.previously_selected is None
                ):
                    self.selection_add(next_node)
                elif self.visual_mode:
                    self.selection_remove(selected[0])
                    next_node = selected[0]
                else:
                    self.selection_set(next_node)
                self.see(next_node)

    def select_previous(self):
        selected = self.selection()
        if selected:
            previous_node = self.prev(selected[0])
            if previous_node:
                if (
                    self.visual_mode
                    and str(self.previously_selected) == selected[0]
                    or self.previously_selected is None
                ):
                    self.selection_add(previous_node)
                elif self.visual_mode:
                    self.selection_remove(selected[-1])
                    previous_node = selected[-1]
                else:
                    self.selection_set(previous_node)
                self.see(previous_node)

    def go_to_top(self):
        self.yview_moveto(0)
        self.selection_set(self.get_children()[0])

    def go_to_bottom(self):
        self.yview_moveto(1)
        self.selection_set(self.get_children()[-1])

    def update(self):
        self.delete(*self.get_children())
        now = dt.datetime.now(tz=system_timezone)
        start_time = now - dt.timedelta(days=1)
        self.events = self.cleaner.get_collapsed_events(start_time)
        for i, event in enumerate(self.events):
            start = event.timestamp.astimezone(system_timezone)
            end = start + event.duration
            time_str = f"{start.strftime('%H:%M')} - {end.strftime('%H:%M')}"
            self.insert(
                "",
                tk.END,
                id=i,
                text="",
                values=(
                    time_str,
                    str(int(event.duration.total_seconds() / 60)),
                    self.cleaner.format_event_text(event),
                ),
            )

    def group(self):
        """Make the highlighted nodes a subtree of a new node."""
        selected = self.selection()
        self.leave_visual_mode()

        parent = self.parent(selected[0])

        # Get the index of the first selected node.
        index = self.index(selected[0])

        all_indexes = [self.index(node) for node in selected]
        if not all(j - i == 1 for i, j in pairwise(all_indexes)):
            messagebox.showerror(
                "Invalid selection",
                "To group events, you must select a contiguous set of events.",
                parent=self,
            )

        # TODO: Add history/Ctrl + backspace/etc like the data entry for aw-watcher-awk-away.
        result = simpledialog.askstring(
            "Group events",
            "Enter a name for the group:",
            initialvalue=self.item(selected[0], "text"),
            parent=self,
        )
        result = result.strip() if result else selected[0]

        # Get the first selected nodes' event.
        events = [self.events[int(node)] for node in selected]
        start_time_str = events[0].timestamp.astimezone(system_timezone).strftime("%H:%M")
        end_time_str = (events[-1].timestamp + events[-1].duration).astimezone(system_timezone).strftime("%H:%M")
        time_str = f"{start_time_str} - {end_time_str}"
        durration = int((events[-1].timestamp + events[-1].duration - events[0].timestamp).total_seconds() / 60)

        new_node = self.insert(parent, index, text=result, values=(time_str, durration, result))

        for node in selected:
            self.move(node, new_node, "end")


# TODO: Add ability to rate activities.
# TODO: Add saving the group data so we can train something to automatically group events.
class MainWindow(tk.Frame):
    def __init__(self, root: tk.Tk, cleaner: ActivityWatchCleaner):
        self.root = root
        self.cleaner = cleaner
        super().__init__(self.root)

        self.root.title("ActivityWatch Daily Reviewer")

        self.create_widgets()

    def update(self):
        self.review_table.update()

    def create_widgets(self):
        self.review_table = ReviewTable(self, self.cleaner)
        self.review_table.grid()

        self.update_button = ttk.Button(self, text="Update", command=self.update)
        self.update_button.grid()
