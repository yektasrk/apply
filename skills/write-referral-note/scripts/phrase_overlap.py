#!/usr/bin/env python3
"""Print the word n-grams two texts share (default n=3).

Mechanical check only: it proves a referral note does not reuse the cover
letter's wording. It never writes or rewrites prose.

Usage: python3 phrase_overlap.py <cover_letter.md> <referral_note.md> [n]
Exit code 0 when nothing is shared, 1 otherwise.
"""
import re
import sys


def ngrams(path, n):
    words = re.findall(r"[a-z0-9']+", open(path, encoding="utf-8").read().lower())
    return {" ".join(words[i:i + n]) for i in range(len(words) - n + 1)}, len(words)


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 3
    letter, _ = ngrams(sys.argv[1], n)
    note, note_words = ngrams(sys.argv[2], n)
    shared = sorted(letter & note)
    print(f"referral note: {note_words} words")
    print(f"shared {n}-grams: {shared if shared else 'none'}")
    sys.exit(1 if shared else 0)


if __name__ == "__main__":
    main()
