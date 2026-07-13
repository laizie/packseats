"""Fetch and parse NC State's public class search. Request/response format: NOTES.md."""

import re
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

SEARCH_URL = "https://webappprd.acs.ncsu.edu/php/coursecat/search.php"
TIMEOUT = 15

# open/total, optionally followed by the waitlist count, e.g. "1/45" or "0/20 (2)"
_SEATS_RE = re.compile(r"(\d+)/(\d+)(?:\s*\((\d+)\))?")


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
            out.append(
                ClassSection(
                    course=course,
                    section=cells[0].get_text(strip=True),
                    component=cells[1].get_text(strip=True),
                    class_number=cells[2].get_text(strip=True),
                    status=status_span.get_text(strip=True),
                    open_seats=int(seats.group(1)),
                    total_seats=int(seats.group(2)),
                    waitlist=int(seats.group(3)) if seats.group(3) else None,
                )
            )
    return out
