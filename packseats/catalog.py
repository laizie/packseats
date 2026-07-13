"""Fetch and parse NC State's public class search. Request/response format: NOTES.md."""

import re
from dataclasses import dataclass, field

import requests
from bs4 import BeautifulSoup

SEARCH_URL = "https://webappprd.acs.ncsu.edu/php/coursecat/search.php"
TIMEOUT = 15

# open/total, optionally followed by the waitlist count, e.g. "1/45" or "0/20 (2)"
_SEATS_RE = re.compile(r"(\d+)/(\d+)(?:\s*\((\d+)\))?")
_TIME_RE = re.compile(r"(\d{1,2}):(\d{2})\s*(AM|PM)\s*-\s*(\d{1,2}):(\d{2})\s*(AM|PM)")

_DAY_CODES = {
    "Monday": "M", "Tuesday": "T", "Wednesday": "W",
    "Thursday": "R", "Friday": "F", "Saturday": "S", "Sunday": "U",
}


@dataclass
class ClassSection:
    course: str  # "HESF 101"
    section: str  # "001"
    component: str  # Lec / Phy / Lab / ...
    class_number: str
    status: str  # Open / Closed / Waitlist / Reserved
    open_seats: int
    total_seats: int
    waitlist: int | None  # None when the section has no waitlist
    days: list[str] = field(default_factory=list)  # e.g. ["M", "W"]; R=Thu, U=Sun
    start: int | None = None  # minutes since midnight; None for TBD/online
    end: int | None = None
    time_text: str = "TBD"
    location: str = ""
    instructor: str = ""

    def conflicts_with(self, other: "ClassSection") -> bool:
        if self.start is None or other.start is None:
            return False  # TBD/online never conflicts
        if not set(self.days) & set(other.days):
            return False
        return self.start < other.end and other.start < self.end


def _minutes(hour: str, minute: str, ampm: str) -> int:
    h = int(hour) % 12 + (12 if ampm == "PM" else 0)
    return h * 60 + int(minute)


def search(term: str, subject: str, course_number: str) -> list[ClassSection]:
    """One catalog query: all sections of one course."""
    resp = requests.post(
        SEARCH_URL,
        data={
            "term": term,
            "subject": subject,
            "course-inequality": "=",
            "course-number": course_number,
        },
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return parse_sections(resp.json()["html"])


def parse_sections(html: str) -> list[ClassSection]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[ClassSection] = []
    for course_el in soup.select("section.course"):
        course = course_el.get("id", "").replace("-", " ")
        for row in course_el.select("tr"):
            cells = row.find_all("td")
            if len(cells) < 4:
                continue  # header row
            avail = cells[3]
            status_span = avail.find("span")
            seats = _SEATS_RE.search(avail.get_text(" ", strip=True))
            if status_span is None or seats is None:
                continue  # not an availability row
            sec = ClassSection(
                course=course,
                section=cells[0].get_text(strip=True),
                component=cells[1].get_text(strip=True),
                class_number=cells[2].get_text(strip=True),
                status=status_span.get_text(strip=True),
                open_seats=int(seats.group(1)),
                total_seats=int(seats.group(2)),
                waitlist=int(seats.group(3)) if seats.group(3) else None,
            )
            if len(cells) > 4:
                _parse_meeting(cells[4], sec)
            if len(cells) > 5:
                sec.location = cells[5].get_text(" ", strip=True)
            if len(cells) > 6:
                sec.instructor = cells[6].get_text(" ", strip=True)
            out.append(sec)
    return out


def _parse_meeting(cell, sec: ClassSection) -> None:
    for li in cell.select("li.meet abbr"):
        day_name = li.get("title", "").split(" ")[0]
        if day_name in _DAY_CODES:
            sec.days.append(_DAY_CODES[day_name])
    m = _TIME_RE.search(cell.get_text(" ", strip=True))
    if m:
        sec.start = _minutes(m.group(1), m.group(2), m.group(3))
        sec.end = _minutes(m.group(4), m.group(5), m.group(6))
        sec.time_text = f"{m.group(1)}:{m.group(2)} {m.group(3)} - {m.group(4)}:{m.group(5)} {m.group(6)}"
