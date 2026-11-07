"""Refresh drafts when new messages arrive during model generation."""

SEPARATOR = "[NEXT_MESSAGE]"


def reply_parts(reply):
    parts = [part.strip() for part in reply.split(SEPARATOR)]
    if not 1 <= len(parts) <= 4 or any(not part for part in parts):
        raise ValueError("Use one to four nonempty outgoing messages.")
    return parts


def deliver_parts(session, driver, observed, reply):
    parts = reply_parts(reply)
    session.validate_send(observed, reply)
    for index, part in enumerate(parts):
        if index:
            observed = driver.observe()
            if observed.identity != session.identity:
                raise ValueError("Conversation changed; remaining messages cancelled.")
            if observed.incoming:
                return "New incoming messages received. Remaining unsent parts cancelled; preparing a fresh reply."
            session.pending, session.draft = observed, part
        session.begin_send(observed, part)
        if not driver.send(observed, part):
            return "Submission uncertain. Inspect the pending message before continuing."
        session.resolve_send(True)
    return "All reply parts observed in the conversation."


def prepare_current(session, observation, model, observe, check, notify=lambda _: None):
    # No draft is sent by this helper. Recipient and pause guards remain active.
    for _ in range(8):
        check()
        reply = session.prepare(observation, model)
        check()
        fresh = observe()
        if fresh.identity != session.identity:
            raise ValueError("Conversation changed; draft blocked.")
        if fresh.incoming == observation.incoming:
            return fresh, reply
        session.pending, session.draft = None, ""
        observation = fresh
        notify("New messages received. Updating the reply to the complete message group.")
    raise ValueError("Messages are still arriving. Wait for a pause and generate again.")
