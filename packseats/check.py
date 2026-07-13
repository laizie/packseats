"""Phase 1 one-shot: print current seat availability for a course (optionally one section).

Usage: python -m packseats.check 2268 HESF 101 --section 001
"""

import argparse

from .catalog import search


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("term", help="term code, e.g. 2268 = Fall 2026")
    ap.add_argument("subject", help="subject code, e.g. HESF")
    ap.add_argument("course", help="course number, e.g. 101")
    ap.add_argument("--section", help="only show this section, e.g. 001")
    args = ap.parse_args()

    rows = search(args.term, args.subject, args.course)
    if not rows:
        raise SystemExit(f"no sections found for {args.subject} {args.course} in term {args.term}")
    if args.section:
        rows = [s for s in rows if s.section == args.section]
        if not rows:
            raise SystemExit(f"section {args.section} not found")

    for s in rows:
        wl = f" (waitlist {s.waitlist})" if s.waitlist is not None else ""
        print(
            f"{s.course} {s.section} {s.component:<4} #{s.class_number:<6} "
            f"{s.status:<9} {s.open_seats}/{s.total_seats}{wl}"
        )


if __name__ == "__main__":
    main()
