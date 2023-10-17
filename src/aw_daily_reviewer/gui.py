"""The tkinter GUI for the aw_daily_reviewer package."""
import datetime as dt
import json
import logging
import tkinter as tk
from itertools import pairwise
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk

import appdirs
import aw_core
from tkcalendar import DateEntry

from aw_daily_reviewer.core import ActivityWatchCleaner

system_timezone = dt.datetime.now().astimezone().tzinfo


logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def event_to_day_pct(event: aw_core.Event) -> float:
    """Convert an event to the percentage of a day it lasted."""
    return event.duration.total_seconds() / (60 * 60 * 24)


def event_to_day_pct_str(event: aw_core.Event) -> str:
    """Convert an event to the percentage of a day it lasted."""
    return f"{event_to_day_pct(event) * 100:.2f}%"


def event_to_minutes(event: aw_core.Event) -> int:
    """Convert an event to the number of minutes it lasted."""
    return int(event.duration.total_seconds() / 60)


def event_to_time_str(event: aw_core.Event) -> str:
    start = event.timestamp.astimezone(system_timezone)
    end = start + event.duration
    return f"{start.strftime('%H:%M')} - {end.strftime('%H:%M')}"


class ReviewTable(ttk.Treeview):
    def __init__(self, parent: tk.Frame, cleaner: ActivityWatchCleaner):
        self.cleaner = cleaner
        super().__init__(parent)

        # TODO: Add sorting by column
        # TODO: Add input for rating the value of an activity.
        # TODO: Add percentage for the percentage of the day spend on the activity.
        # self["columns"] = ("time", "durration", "event")
        self["columns"] = ("minutes", "days", "event")
        self.event_desc_index = 2

        self.column("#0", width=120, stretch=False)
        self.column("minutes", width=100, stretch=False, anchor="center")
        self.column("days", width=100, stretch=False, anchor="center")
        self.column("event", minwidth=500, width=500, stretch=True)

        self.heading("#0", text="")
        self.heading("minutes", text="Minutes")
        self.heading("days", text="Days (%)")
        self.heading("event", text="Event")

        self.insert("", tk.END, text="test", values=("test", "test"))
        self.visual_mode = False
        self.previously_selected = None
        self.old_selection = set()
        self.date = None
        self.bind("<<TreeviewSelect>>", lambda _: self.set_previously_selected())

        # Add some vim-like keybindings
        self.bind("<Double-g>", lambda _: self.go_to_top())
        self.bind("<G>", lambda _: self.go_to_bottom())
        # TODO: Add the ability to refold/delete folds/add to a fold.
        self.bind("h", lambda _: self.close_selected_node())
        self.bind("zc", lambda _: self.close_selected_node())
        self.bind("l", lambda _: self.open_selected_node())
        self.bind("zo", lambda _: self.open_selected_node())
        self.bind("i", lambda _: self.edit_selected_node())
        # TODO: Fix j and k to go into folds if they are open.
        self.bind("j", lambda _: self.select_next())
        self.bind("k", lambda _: self.select_previous())
        self.bind("v", lambda _: self.enter_visual_mode())
        self.bind("V", lambda _: self.enter_visual_mode())
        self.bind("<Double-z>", lambda _: self.center_selected())
        self.bind("<Double-d>", lambda _: self.remove_selected())
        self.bind("x", lambda _: self.remove_selected())
        self.bind("<Escape>", lambda _: self.leave_visual_mode())
        self.bind("zf", lambda _: self.group())

        self.bind("<Control-s>", lambda _: self.to_json())
        self.bind("<Control-Shift-R>", lambda _: self.load_json(self.to_json()))

    def event_to_values(self, event: aw_core.Event):
        return (
            event_to_minutes(event),
            event_to_day_pct_str(event),
            self.cleaner.format_event_text(event),
        )

    def node_to_json(self, node: str):
        return {
            "event": self.events_by_node_id[node].to_json_dict() if node in self.events_by_node_id else None,
            "node": self.item(node),
            "children": [self.node_to_json(child) for child in self.get_children(node)],
        }

    def to_json(self):
        """Create a JSON representation of the tree so we can save our work and come back later."""
        logger.debug("Converting tree to JSON.")
        nodes = [self.node_to_json(node) for node in self.get_children()]
        return {
            "nodes": nodes,
            "date": dt.datetime.now(tz=system_timezone).date().isoformat(),
        }

    def load_json(self, json_data: dict):
        """Load a JSON representation of the tree."""
        logger.debug("Loading tree from JSON.")
        self.delete(*self.get_children())
        self.events_by_node_id: dict[str, aw_core.Event] = {}
        for child in json_data["nodes"]:
            self.load_json_node(child, "")

    def load_json_node(self, json_data: dict, parent: str):
        """Load a JSON representation of the tree."""
        logger.debug(f"Loading node: {json_data}")

        node = self.insert(
            parent,
            tk.END,
            text=json_data["node"]["text"],
            values=json_data["node"]["values"],
        )
        if json_data["event"]:
            self.events_by_node_id[node] = aw_core.Event(**json_data["event"])
        for child in json_data["children"]:
            self.load_json_node(child, node)

    def edit_selected_node(self):
        selected = self.selection()
        if selected:
            # Use a dialog because Entry widgets are not supported inside of a Treeview.
            result = simpledialog.askstring(
                "Edit event",
                "Enter a new name for the event:",
                # Use the event column as the initial value
                initialvalue=self.item(selected[0], "values")[self.event_desc_index],
                parent=self,
            )
            if result:
                self.item(selected[0], values=(*self.item(selected[0], "values")[:-1], result))

    def open_selected_node(self):
        selected = self.selection()
        if selected:
            self.item(selected[0], open=True)

    def close_selected_node(self):
        selected = self.selection()
        if selected:
            is_open = self.item(selected[0], "open")
            has_children = self.get_children(selected[0])
            parent = self.parent(selected[0])
            if is_open and has_children:
                self.item(selected[0], open=False)
            elif parent:
                self.item(parent, open=False)
                self.selection_set(self.parent(selected[0]))

    def remove_selected(self):
        selected = self.selection()
        # Must select next before deleting...
        self.leave_visual_mode()
        self.select_next()  # TODO: Handle end of table case.
        if selected:
            for node in selected:
                self.delete(node)

    def set_previously_selected(self):
        # TODO: Handle case where you are selecting from the top in visual mode and trying to go back up.
        current_selections = set(self.selection())
        if new_selections := current_selections - self.old_selection:
            if self.old_selection and max(new_selections) == max(self.old_selection):
                self.previously_selected = min(new_selections)
            else:
                self.previously_selected = max(new_selections)
        elif removed_selections := self.old_selection - current_selections:
            if self.previously_selected in removed_selections:
                # This assumes that the node ids are ordered as you insert new nodes.
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

    def update(self, date: dt.date | None = None):
        self.delete(*self.get_children())
        self.date = date

        if date is None:
            now = dt.datetime.now(tz=system_timezone)
            start_time = now - dt.timedelta(days=1)
            end_time = None
        else:
            start_time = dt.datetime.combine(date, dt.time.min, tzinfo=system_timezone)
            end_time = dt.datetime.combine(date, dt.time.max, tzinfo=system_timezone)

        logger.debug(f"Getting events from {start_time} to {end_time}.")
        self.events_by_node_id: dict[str, aw_core.Event] = {}
        for event in self.cleaner.get_collapsed_events(start_time, end_time):
            node_id = self.insert(
                "",
                tk.END,
                text=event_to_time_str(event),
                values=self.event_to_values(event),
            )
            self.events_by_node_id[node_id] = event

        self.selection_set(self.get_children()[0])

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

        # Get the first selected nodes' event.
        logger.debug(f"Selected: {selected}")
        logger.debug(self.events_by_node_id)
        events = [self.events_by_node_id[node] for node in selected]
        pseudo_event = aw_core.Event(
            timestamp=events[0].timestamp,
            duration=events[-1].timestamp + events[-1].duration - events[0].timestamp,
            data=events[0].data,
        )

        new_node = self.insert(
            parent, index, text=event_to_time_str(pseudo_event), values=self.event_to_values(pseudo_event)
        )

        for node in selected:
            self.move(node, new_node, "end")
        self.selection_set(new_node)


# TODO: Add ability to rate activities.
# TODO: Add saving the group data so we can train something to automatically group events.
class MainWindow(tk.Frame):
    def __init__(self, root: tk.Tk, cleaner: ActivityWatchCleaner):
        self.root = root
        self.cleaner = cleaner
        super().__init__(self.root)

        self.root.title("ActivityWatch Daily Reviewer")

        # self.root.bind("<Shift-r>", lambda _: self.update())
        self.root.bind("<Control-r>", lambda _: self.update())

        self.create_widgets()

    def update(self):
        date = self.date_picker.get_date()
        self.review_table.update(date)

    def create_widgets(self):
        self.review_table = ReviewTable(self, self.cleaner)
        self.review_table.grid(column=0, row=0, sticky="nsew")
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.update_button = ttk.Button(self, text="Update", command=self.update)
        self.update_button.grid(column=1, row=0, sticky="nw")

        # Add a date picker
        self.date_picker = DateEntry(self, width=12, background="darkblue", foreground="white", borderwidth=2)
        self.date_picker.grid(column=2, row=0, sticky="nw")

        self.save_button = ttk.Button(self, text="Save", command=self.save)
        self.save_button.grid(column=1, row=0, sticky="sw")

        self.open_box = ttk.Combobox(self, values=self.get_saved_dates(), state="readonly")
        self.open_box.grid(column=2, row=0, sticky="sw")
        self.open_button = ttk.Button(self, text="Open", command=self.open)
        self.open_button.grid(column=3, row=0, sticky="sw")

    def get_days_dir(self):
        appdata_dir = Path(appdirs.user_data_dir("aw-daily-reviewer"))
        if not appdata_dir.exists():
            appdata_dir.mkdir(parents=True)
        days_dir = appdata_dir / "days"
        if not days_dir.exists():
            days_dir.mkdir()
        return days_dir

    def get_saved_dates(self):
        return [x.stem for x in self.get_days_dir().glob("*.json")]

    def open(self):
        """Open a saved review."""
        date = self.open_box.get()
        if date:
            file = self.get_days_dir() / f"{date}.json"
            logger.debug(f"Opening {file}")
            with file.open() as f:
                table_json = json.load(f)
            self.review_table.load_json(table_json)
            self.review_table.date = dt.datetime.fromisoformat(table_json["date"]).date()

    def save(self):
        """Save the current state of the tree."""
        table_json = self.review_table.to_json()

        assert self.review_table.date is not None
        file = self.get_days_dir() / f"{self.review_table.date.isoformat()}.json"
        logger.debug(f"Saving to {file}")
        with file.open("w") as f:
            json.dump(table_json, f, indent=4)
