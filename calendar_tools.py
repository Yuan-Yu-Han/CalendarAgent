"""
calendar_tools.py - AppleScript-based tools for macOS Calendar and Reminders.
Both apps sync to iOS via iCloud automatically.
"""

import subprocess
from datetime import datetime
from typing import Optional


def run_applescript(script: str) -> str:
    """Execute an AppleScript and return stdout."""
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"AppleScript error: {result.stderr.strip()}")
    return result.stdout.strip()


def _escape(s: str) -> str:
    """Escape a string for safe embedding in AppleScript."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _as_date_code(varname: str, dt: datetime) -> str:
    """Return AppleScript snippet that assigns a date to `varname`."""
    time_secs = dt.hour * 3600 + dt.minute * 60 + dt.second
    return (
        f'set {varname} to current date\n'
        f'    set year of {varname} to {dt.year}\n'
        f'    set month of {varname} to {dt.month}\n'
        f'    set day of {varname} to {dt.day}\n'
        f'    set time of {varname} to {time_secs}'
    )


def list_calendars() -> list[str]:
    """Return list of calendar names available in Calendar.app."""
    script = '''
    tell application "Calendar"
        set calNames to {}
        repeat with cal in calendars
            set end of calNames to name of cal
        end repeat
        return calNames
    end tell
    '''
    raw = run_applescript(script)
    if not raw:
        return []
    return [c.strip() for c in raw.split(",") if c.strip()]


def list_reminder_lists() -> list[str]:
    """Return list of reminder list names available in Reminders.app."""
    script = '''
    tell application "Reminders"
        set listNames to {}
        repeat with rl in lists
            set end of listNames to name of rl
        end repeat
        return listNames
    end tell
    '''
    raw = run_applescript(script)
    if not raw:
        return []
    return [r.strip() for r in raw.split(",") if r.strip()]


def create_calendar_event(
    title: str,
    start_date: str,
    end_date: str,
    calendar_name: Optional[str] = None,
    notes: Optional[str] = None,
    location: Optional[str] = None,
) -> dict:
    """
    Create a calendar event in Calendar.app (syncs to iOS via iCloud).

    Args:
        title:         Event title.
        start_date:    ISO 8601 string, e.g. "2026-02-20T10:00:00".
        end_date:      ISO 8601 string.
        calendar_name: Target calendar name. Falls back to first writable calendar.
        notes:         Optional event notes/description.
        location:      Optional event location.
    """
    start_dt = datetime.fromisoformat(start_date)
    end_dt = datetime.fromisoformat(end_date)

    title_esc = _escape(title)
    extra_props = ""
    if notes:
        extra_props += f', description:"{_escape(notes)}"'
    if location:
        extra_props += f', location:"{_escape(location)}"'

    start_code = _as_date_code("startDate", start_dt)
    end_code = _as_date_code("endDate", end_dt)

    if calendar_name:
        cal_block = f'tell calendar "{_escape(calendar_name)}"'
    else:
        cal_block = 'tell (first calendar whose writable is true)'

    script = f'''
    tell application "Calendar"
        {start_code}
        {end_code}
        {cal_block}
            make new event at end with properties {{summary:"{title_esc}", start date:startDate, end date:endDate{extra_props}}}
        end tell
    end tell
    '''
    run_applescript(script)
    return {
        "status": "success",
        "type": "calendar_event",
        "title": title,
        "start": start_date,
        "end": end_date,
        "calendar": calendar_name or "default",
    }


def create_reminder(
    title: str,
    due_date: Optional[str] = None,
    list_name: Optional[str] = None,
    notes: Optional[str] = None,
    priority: int = 0,
) -> dict:
    """
    Create a reminder in Reminders.app (syncs to iOS via iCloud).

    Args:
        title:     Reminder title.
        due_date:  ISO 8601 string, e.g. "2026-02-20T10:00:00". Optional.
        list_name: Target list name. Falls back to first list.
        notes:     Optional additional notes.
        priority:  0=none, 1=high, 5=medium, 9=low.
    """
    title_esc = _escape(title)
    extra_props = ""

    due_code = ""
    if due_date:
        due_dt = datetime.fromisoformat(due_date)
        due_code = _as_date_code("dueDate", due_dt)
        extra_props += ", due date:dueDate"

    if notes:
        extra_props += f', body:"{_escape(notes)}"'
    if priority:
        extra_props += f", priority:{priority}"

    if list_name:
        list_block = f'tell list "{_escape(list_name)}"'
    else:
        list_block = "tell list 1"

    script = f'''
    tell application "Reminders"
        {due_code}
        {list_block}
            make new reminder with properties {{name:"{title_esc}"{extra_props}}}
        end tell
    end tell
    '''
    run_applescript(script)
    return {
        "status": "success",
        "type": "reminder",
        "title": title,
        "due_date": due_date,
        "list": list_name or "default",
    }
