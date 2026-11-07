"""One opening attempt per observed new Anonchat match."""

import re
from .core import normalize
from .flow import deliver_parts


class OpeningGate:
    def __init__(self):
        self.armed = False
        self.waiting = False

    def waiting_screen(self):
        if not self.waiting:
            self.armed = True
        self.waiting = True

    def search_started(self):
        self.armed = True
        self.waiting = True

    def claim(self, platform):
        eligible = platform == "anonchat" and self.armed
        self.armed = False
        self.waiting = False
        return eligible


def extract_bio(text):
    """Use only labelled profile sections, never arbitrary conversation text."""
    lines = [normalize(line) for line in text.splitlines() if normalize(line)]
    result, active = [], False
    for line in lines:
        if re.search(r"^(about (?:partner|me)|bio(?:graphy)?|interests)\s*:?$", line, re.I):
            active = True
            result.append(line)
            continue
        if active:
            if re.search(r"^(chat starts|you\b|your partner\b|hii\b|write a message|send\b)|\b\d{1,2}:\d{2}\b", line, re.I):
                break
            result.append(line)
            if len(result) >= 12:
                break
    return "\n".join(result)[:800]


def open_match(session, driver, model):
    """The gate is consumed before this function, including on uncertain sends."""
    observed = driver.observe()
    if observed.identity != session.identity:
        raise ValueError("Conversation changed before the opening greeting.")
    if observed.incoming:
        session.prepare(observed, lambda _: "hii :3")
    else:
        session.prepare_greeting(observed, lambda _: "hii :3")
    result = deliver_parts(session, driver, observed, "hii :3")
    if session.uncertain:
        return result
    driver.check()
    bio = driver.read_bio(session.identity)
    observed = driver.observe()
    for _ in range(8):
        if observed.identity != session.identity:
            raise ValueError("Conversation changed before the bio opening.")
        reply = normalize(model.opening(session.history[-20:], bio, observed.incoming))
        if not reply or len(reply) > 1500:
            raise ValueError("The bio opening is empty or too long. Greeting was already sent.")
        driver.check()
        if session.paused:
            raise InterruptedError("Opening paused.")
        fresh = driver.observe()
        if fresh != observed:
            observed = fresh
            continue
        session.pending, session.draft = observed, reply
        return deliver_parts(session, driver, observed, reply)
    raise ValueError("Messages are still arriving. Greeting sent; opening stopped.")
