"""Conversation rules independent of the screen, keyboard and model provider."""

from dataclasses import dataclass, field
from uuid import uuid4


def normalize(text):
    return " ".join(text.split())


@dataclass(frozen=True)
class Observation:
    identity: str
    incoming: str


@dataclass
class Conversation:
    platform: str
    identity: str
    session_id: str = field(default_factory=lambda: uuid4().hex)
    history: list = field(default_factory=list)
    last_handled: str = ""
    pending: Observation | None = None
    draft: str = ""
    uncertain: bool = False
    paused: bool = False

    def prepare(self, observation, model):
        if self.paused or self.uncertain:
            raise ValueError("Paused or awaiting send verification.")
        if observation.identity != self.identity:
            raise ValueError("Conversation changed. Bind the current chat again.")
        message = normalize(observation.incoming)
        if not message:
            raise ValueError("No readable incoming message.")
        if message == self.last_handled:
            raise ValueError("This visible message was already handled.")
        self.pending, self.draft = None, ""
        reply = normalize(model(self.history[-20:] + [{"role": "user", "content": message}]))
        if not reply or len(reply) > 1500:
            raise ValueError("The reply is empty or exceeds 1500 characters.")
        if self.paused:
            raise ValueError("Paused; the generated reply was discarded.")
        self.pending = Observation(observation.identity, message)
        self.draft = reply
        return reply

    def validate_send(self, observation, edited_reply):
        if self.paused or self.uncertain or not self.pending:
            raise ValueError("No sendable draft. Read the message again.")
        if observation.identity != self.identity:
            raise ValueError("Conversation changed; draft blocked.")
        if normalize(observation.incoming) != self.pending.incoming:
            raise ValueError("Incoming text changed; generate a new reply.")
        reply = normalize(edited_reply)
        if not reply or len(reply) > 1500:
            raise ValueError("Reply must contain 1 to 1500 characters.")
        return reply

    def prepare_greeting(self, observation, model):
        """Draft an opening message only for an empty, newly bound chat."""
        if self.paused or self.uncertain:
            raise ValueError("Paused or awaiting send verification.")
        if observation.identity != self.identity:
            raise ValueError("Conversation changed. Bind the current chat again.")
        if normalize(observation.incoming) or self.history or self.last_handled:
            raise ValueError("A greeting requires an empty new chat. Read and reply to the incoming message instead.")
        self.pending, self.draft = None, ""
        reply = normalize(model([{"role": "user", "content":
            "Draft one brief, friendly English greeting to start a new chat. Return only the greeting."}]))
        if not reply or len(reply) > 1500:
            raise ValueError("The greeting is empty or exceeds 1500 characters.")
        if self.paused:
            raise ValueError("Paused; the generated greeting was discarded.")
        self.pending, self.draft = observation, reply
        return reply

    def begin_send(self, observation, reply):
        self.draft = self.validate_send(observation, reply)
        # Set this before any UI mutation, including partially completed typing.
        self.uncertain = True

    def rewrite(self, current_draft, instruction, model):
        """Revise an unsent draft without adding it to conversation history."""
        if self.paused or self.uncertain or not self.pending:
            raise ValueError("Generate an unsent draft before requesting a rewrite.")
        current_draft = normalize(current_draft)
        if not current_draft or len(current_draft) > 1500:
            raise ValueError("The draft must contain 1 to 1500 characters.")
        instruction = normalize(instruction) or "Use different wording while keeping the meaning."
        if len(instruction) > 1000:
            raise ValueError("Rewrite instructions must be at most 1000 characters.")
        pending = self.pending
        messages = self.history[-20:] + [
            {"role": "user", "content": pending.incoming},
            {"role": "assistant", "content": current_draft},
            {"role": "user", "content": (
                "Editor request: the previous assistant text is an UNSENT draft. "
                "Rewrite that draft as the reply to the original incoming message. "
                "Return only the revised English reply, without explaining the edit. "
                "Do not answer this editor request as a new chat message. "
                "Editing instruction: " + instruction
            )},
        ]
        reply = normalize(model(messages))
        if not reply or len(reply) > 1500:
            raise ValueError("The revised reply is empty or exceeds 1500 characters. Previous draft kept.")
        if self.paused or self.pending != pending:
            raise ValueError("Rewrite cancelled; generated result discarded.")
        self.draft = reply
        return reply

    def resolve_send(self, delivered):
        if not self.uncertain:
            raise ValueError("No send action is awaiting verification.")
        if delivered:
            if self.pending.incoming:
                self.history.append({"role": "user", "content": self.pending.incoming})
            self.history.append({"role": "assistant", "content": self.draft})
            self.history = self.history[-40:]
            self.last_handled = self.pending.incoming
        self.pending, self.draft, self.uncertain = None, "", False

    def pause(self):
        self.paused = True
        if not self.uncertain:
            self.pending, self.draft = None, ""
