# NOTES: class-search request (Phase 0, verified 2026-07-13)

Findings from reverse-engineering the public class search. Every claim below was
verified with live requests from a terminal — no browser, no cookies.

## The request

```
POST https://webappprd.acs.ncsu.edu/php/coursecat/search.php
Content-Type: application/x-www-form-urlencoded; charset=UTF-8
```

**No authentication, no cookies, no browser headers required.** The cookies the
browser sends (`_ga*` = Google Analytics, `PS_DEVICEFEATURES` = PeopleSoft UI
sniffing, `_opensaml_req_ss*` = leftover Shibboleth artifact from another app on
the domain) are all ignored by this endpoint. `X-Requested-With` is not needed.

Minimal working form body — only these four fields are required:

| field               | value                | notes                                        |
|---------------------|----------------------|----------------------------------------------|
| `term`              | e.g. `2268`          | see term-code scheme below                   |
| `subject`           | e.g. `HESF`          | bare code works; full display string ("HESF - Health Exercise Studies Fitness") returns identical content |
| `course-inequality` | `=`, `<=`, or `>=`   | use `=` to fetch exactly one course          |
| `course-number`     | e.g. `101`           |                                              |

The browser also sends `course-career`, `session`, `start-time-inequality`,
`start-time`, `end-time-inequality`, `end-time`, `instructor-name`, and
`current_strm` (duplicate of `term`) — all can be omitted; response is
byte-identical.

Example (one course, all sections):

```bash
curl -s 'https://webappprd.acs.ncsu.edu/php/coursecat/search.php' \
  -H 'Content-Type: application/x-www-form-urlencoded; charset=UTF-8' \
  --data 'term=2268&subject=HESF&course-inequality=%3D&course-number=101'
```

## Term codes

PeopleSoft scheme: `2` + two-digit year + semester digit.

- `1` = Spring, `6` = Summer 1, `7` = Summer 2, `8` = Fall
- `2268` = Fall 2026, `2261` = Spring 2026, `2267` = Summer 2 2026, etc.

Valid terms come from the `<option>` values on `…/php/coursecat/` (the form page).

## The response

JSON wrapper around an HTML payload:

```json
{ "html": "<section class=\"course\" ...>…all the markup…</section>…",
  "json": { "inputs": { …echo of what you sent… } } }
```

So: parse JSON first, then parse the `html` string with an HTML parser.

Structure inside `html`:

- One `<section class="course" id="HESF-101">` block per course.
- Inside each, a table with one `<tr>` per class section. Header:
  `Section | Component | Class # | Avail. | Day/Time | Location | Instructor | Begin/End Dates | Topic | Notes`
- The **Avail. cell** (4th `<td>`) is what the watcher cares about:

| status     | markup                             | seat text        | meaning                        |
|------------|------------------------------------|------------------|--------------------------------|
| Open       | `<span class="text-success">Open</span>`     | `1/45`      | 1 open of 45 total             |
| Closed     | `<span class="text-danger">Closed</span>`    | `0/32`      | full                           |
| Waitlist   | `<span class="text-info">Waitlist</span>`    | `0/20 (2)`  | full; `(2)` = waitlist count   |
| Reserved   | `<span class="text-success">Reserved</span>` | `N/M`       | open seats exist but reserved  |

- Seat text pattern: `open/total` optionally followed by `(waitlist)`.
- **Reserved-seat detail** lives in a popover anchor per section:
  `id="reserve-HESF-101-071" data-content="<p>1 seat - AGI Students Only"`.
  Useful later if reserved-seat noise becomes a problem (PRD open question).
- Row cells: `td[0]`=section, `td[1]`=component (Lec/Phy/Lab), `td[2]`=class
  number, `td[3]`=availability.

## Design implications

- **No section parameter exists.** The watcher fetches per *course* and picks
  out the watched section(s) from the rows. Multiple watched sections of the
  same course cost one request.
- Responses are chunky (47 KB for one course, ~300 KB for a big subject sweep).
  Always query with `course-inequality==` and keep the poll interval polite.
- Notify on transition into `Open` (and optionally `Waitlist` opening); track
  last-seen status + open count per section.
- HTML-inside-JSON means we need an HTML parser → strengthens the Python
  (requests + BeautifulSoup) option for Phase 0's language decision.
