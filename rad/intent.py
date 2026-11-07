"""Small English question-intent grammar; no extra model round trip is needed."""
import re


def is_question(text):
    words=re.findall(r"[a-z]+(?:'[a-z]+)?",text.casefold())
    if not words:return False
    sentence=' '.join(words)
    if '?' in text:return True
    if sentence in {'wyd','wya','wbu','hbu','asl','age','your age','your name',
                    'and you','you too','how about you','what about you'}:return True
    # Informal WH questions omit auxiliaries: "where u from", "how old r u".
    if words[0] in {'where','when','why','who','whose','which','how'}:return True
    if words[0] in {'what','whats',"what's"}:
        return len(words)>1 and words[1] not in {'a','an'}
    if re.match(r"^(can|could|would|will|do|does|did|are|is|am|was|were|have|has|had|should|may|must) (you|u|i|we|they|he|she|it|there|this|that|your)\b",sentence):return True
    if re.match(r"^(tell me|let me know|any idea|do you know|i wonder)\b",sentence):return True
    if re.match(r"^(you|u) (from|live where|got any|have any|wanna|want to)\b",sentence):return True
    if re.search(r"\b(right|isn't it|aren't you|don't you)$",sentence):return True
    return False


def first_question_pair(messages, incoming_numbers, handled):
    """Return the older message in the first adjacent, unanswered question pair."""
    previous=None
    for message in messages:
        pending=message.role=='user' and incoming_numbers.get(message.id,0)>handled
        if pending and is_question(message.text):
            if previous is not None:return previous
            previous=message
        else:previous=None
    return None
