"""Extractive summarization — zero-dependency, runs anywhere."""
import re
from collections import Counter

_STOP = set("""a an the and or but if then else of to in on for with as by at from is are was
were be been being it its this that these those i you he she we they them his her their our
your my me us do does did done can could should would will won't don't doesn't not no yes
about into over under out up down off than too very just also more most some such only own
same so than then there here when where why how all any both each few other s t don now m
re ve ll d o has have had having he'd he'll he's here's how's i'd i'll i'm i've isn't
it'd it'll it's let's mustn't she'd she'll she's shouldn't that's there's they'd they'll
they're they've we'd we'll we're we've weren't what's when's where's who's who's won't
wouldn't you'd you'll you're you've""".split())


def _sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text.replace("\n", " ")).strip()
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])", text)
    return [p.strip() for p in parts if 30 < len(p) < 400]


def keywords(text: str, n: int = 8) -> list[str]:
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9+#._-]{2,}", text.lower())
    words = [w.strip("._-") for w in words if w not in _STOP and not w.isdigit()]
    return [w for w, _ in Counter(words).most_common(n)]


def top_sentences(text: str, n: int = 6) -> list[str]:
    sents = _sentences(text)
    if not sents:
        trimmed = re.sub(r"\s+", " ", text).strip()
        return [trimmed[:400]] if trimmed else []
    freqs = Counter(w for w in re.findall(r"[a-z']+", text.lower()) if w not in _STOP)
    if not freqs:
        return sents[:n]
    scored = []
    for i, s in enumerate(sents):
        ws = [w for w in re.findall(r"[a-z']+", s.lower()) if w in freqs]
        if not ws:
            continue
        score = sum(freqs[w] for w in ws) / (len(ws) ** 0.8 + 1)
        if i < len(sents) * 0.25:
            score *= 1.15  # lead bias
        scored.append((score, i, s))
    scored.sort(reverse=True)
    picked = sorted(scored[:n], key=lambda x: x[1])
    return [s for _, _, s in picked]
