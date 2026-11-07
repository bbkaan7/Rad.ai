# Modular Chatbot: Revised Development Plan

Application baseline: v0.5.0. First functional product target: v1.0.0.
This roadmap supersedes the Shopify-oriented plan. No application changes or deployment
are performed by this document. All application text, documentation and identifiers remain English.

## Product definition

Build a reusable, text-first chatbot platform with replaceable channel adapters,
domain policies, model adapters, memory and tools. The first workflow discovers a
suitable conversation partner on Anonchat, conducts small talk, offers a Telegram
handoff, continues an approved commercial conversation on Telegram, and recognizes a
verified PayPal payment. Shopify, stores and product catalogs are not dependencies.

Future domain modules may support customer service or customs-document drafting.
Those modules will need their own data, rules, tools and validation. They are not
implemented or promised by v1.0.0. Video calls and character design are out of scope.

## v1.0.0 end-to-end behavior

1. Open or focus the configured Anonchat application and identify its current screen.
2. Locate and activate `Search for partner` using the desktop adapter.
3. Read the new partner's visible bio and the start of the conversation.
4. Evaluate suitability using the operator's explicit, versioned eligibility rules.
5. If unsuitable, use `Next partner` within configured search limits.
6. If eligible, conduct text-only small talk in the configured English persona.
7. When the conversation is receptive, offer a Telegram invitation without repeatedly
   pressuring someone who declines. End or hand over stalled/ambiguous conversations.
8. After the user starts the Telegram interaction, link the referral session to that
   Telegram identity and let the Telegram bot take responsibility for the conversation.
9. Follow a configured commercial playbook and offer a server-created PayPal checkout
   when appropriate. Keep the offering configurable rather than hard-coded to a store.
10. Receive and authenticate the payment event, reconcile its transaction details,
    and identify the correct customer and pending transaction.
11. Mark the verified transaction successful, set the customer payment status, and
    promote selected temporary context into durable customer memory.
12. Use the durable memory on later visits, subject to correction, retention and deletion.

The payment milestone means verified funds captured/completed for the intended order,
not a payment screenshot, approval event, checkout-page return or customer claim.
Webhook delivery can be delayed: process it promptly on receipt, but do not promise
zero delay between the payer's click and the application's confirmation.

## Core architecture

Channel adapters -> normalized events -> session/workflow controller -> policy and
memory retrieval -> model -> validated actions -> channel adapter -> event history.

### Modules

- **Channel adapters:** desktop Anonchat and official Telegram Bot API first. Keep
  screenshots, OCR, matching and clicks out of the conversation business logic.
- **Workflow controller:** owns conversation state, search, qualification, takeover,
  retries, timeouts and handoff. The model proposes language and structured decisions;
  the controller authorizes actions.
- **Persona and dialogue:** system instructions, operator examples, optional/versioned
  text LoRA and a replaceable inference endpoint. Do not claim the bot is the human
  operator; its role is a disclosed assistant using an approved style.
- **Policy modules:** eligibility criteria, conversational objectives, offer rules,
  allowed tools and escalation conditions. Commercial rules are one module, not the core.
- **Memory service:** short-lived prospect context, durable customer context, identity
  links and provenance. Financial records and opt-out records have separate lifecycles.
- **Payment adapter:** PayPal order creation, event verification, reconciliation and
  payment-state transitions. Keep payment credentials outside the model context.
- **Operator controls:** preview, approve, pause, override, take over, correct memory,
  inspect status and export reviewed examples. All controls and logs use English.
- **Evaluation/data pipeline:** record model drafts, final responses, corrections,
  state transitions, outcome labels and model/prompt/policy versions.

Expose future media through a generic attachment/action interface. Do not build video,
OBS integration or image-generation workers in the first release.

## Identity, eligibility and contact rules

Obtain the exact Anonchat app URL/version and check supported use before automation.
No headless API availability is assumed. The desktop/emulator route is acceptable for
v1.0.0, but repeated partner search needs platform-compatible limits and a kill switch.
No evasion of platform restrictions is part of this plan.

Define eligibility as a configurable set of observable requirements: for example,
supported language, explicitly expressed interests and current conversational intent.
Do not invent demographic or sensitive traits from names, avatars or vague bios.
Use `eligible`, `ineligible` and `uncertain` with reasons. Missing/unreadable bios are
`uncertain`; the operator chooses a clarification or skip policy before autonomous use.
Age-restricted offerings require a separate appropriate eligibility process; a model's
guess from a profile is not age verification.

Use application/session IDs whenever available. In anonymous channels, do not assume a
returning visible name is the same person. Offer the Telegram link only in an appropriate
conversation, respect declines and persist an opt-out marker when identity is available.

## Anonchat-to-Telegram handoff

Create a random, expiring referral token that maps to the temporary session on the
server. Send `https://t.me/<bot>?start=<token>`. Put no bio, payment details or raw
personal data inside the link. The user starts the bot; the server processes the token
and binds the handoff to that Telegram identity. Links can be forwarded, so avoid copying
sensitive history without confirming the link; reject reuse by a different account.

Transfer a bounded summary, known preferences, conversation stage and pending objective.
Mark the Anonchat session `handed_off` to prevent two bots replying in parallel. Until a
valid Telegram start event arrives, the handoff remains pending. Support expired tokens,
duplicate start events, declined invitations and a restart during the handoff.

Telegram's ordinary Bot API requires the user to initiate contact and supports start
parameters for linking sessions. [Bot introduction](https://core.telegram.org/bots),
[Deep linking](https://core.telegram.org/bots/features#deep-linking).

## Memory and payment lifecycle

Keep dialogue and payment states separate.

Dialogue: `idle -> searching -> evaluating -> chatting -> invitation_sent -> handed_off`.
Alternate outcomes: `skipped`, `declined`, `expired`, `paused`, `needs_review`, `closed`.

Payment: `not_created -> pending -> paid`, with possible `failed`, `cancelled`,
`partially_refunded`, `refunded` or `disputed` transitions and transaction history.

Temporary memory stores the anonymous session, visible bio, recent messages, summary,
qualification decision and referral token. Use a configurable expiry instead of retaining
every skipped person's profile indefinitely.

After a verified payment, atomically record the processed event, transaction and customer
status, and create one durable-memory promotion job. The promotion stores useful approved
preferences, a compact conversation summary and transaction references, not a blind copy
of every private detail. Retrying an event or job must not duplicate the sale or memory.

Durable customer identity normally uses the verified handoff's Telegram user ID plus
internal customer ID. Avoid linking by payment email or display name alone. Customer
memory remains outside the LoRA weights. Refunds and disputes update status without
erasing audit history or incorrectly preserving an unqualified "successful sale" label.

Successful-payment customers and good training examples are different concepts.
Temporary-memory expiry must not remove legally/operationally required financial records
or the minimal records needed to honor opt-outs. Define retention rules before production.

## PayPal boundary

Build a configurable offering/playbook interface now; choose the actual offering,
amount, currency, merchant account and fulfillment rules before enabling real charging.
Without these inputs, the integration can be tested in a sandbox but is not ready for
live commercial use. No Shopify integration is planned.

Create checkout/order records server-side, link them to the customer/session, and verify
event authenticity. Match merchant, order/capture ID, amount and currency. Handle duplicate,
delayed and out-of-order notifications; reconcile provider status after uncertain events.
The model must not set `paid`, invent a price or change payment destinations.
[PayPal webhook integration](https://developer.paypal.com/api/rest/webhooks/rest/).

Check the chosen offering against the channel's payment requirements. In particular,
Telegram has specific payment requirements for digital goods sold inside bots; do not
assume a PayPal checkout is valid for every future offering.
[Telegram payment overview](https://core.telegram.org/bots#receive-payments).

## Milestones to v1.0.0

| Release | Scope | Exit criteria |
|---|---|---|
| 0.5.0 | Existing English desktop prototype | Preserve working settings and a recoverable baseline |
| 0.6.0 | Supervised Anonchat search, bio reading and partner selection | Correctly detect screens, expose decisions, search/skip only on approval |
| 0.7.0 | Stateful small talk and owner-style text model | Maintain context, handle declines, pass dialogue evaluation; validate a first text LoRA if the dataset is ready |
| 0.8.0 | Telegram bot and controlled handoff | Link one session correctly, transfer context, stop duplicate ownership |
| 0.9.0 | Configurable commercial playbook and PayPal sandbox | Verify payment events and promote the right customer's memory exactly once |
| 1.0.0 | Integrated text-first Anonchat -> Telegram -> PayPal workflow | Pass end-to-end tests, then enable bounded automation and explicitly configured live payments |

Use a stable base model plus examples during development. If custom text LoRA is a
v1.0.0 launch requirement, insufficient permitted training data blocks that gate; do not
call prompt configuration "training". Payment revenue is a business outcome, not a
software acceptance guarantee.

## Immediate implementation: v0.6.0

1. Back up v0.5.0 and extract channel, model, memory and controller interfaces without
   introducing store/product dependencies.
2. Confirm the exact app and controlled test accounts. Capture examples of its home,
   searching, connected, bio, disconnected and error states.
3. Add configurable references for `Search for partner`, `Next partner`, textbox and
   send controls. Define bio and message capture regions separately.
4. Implement an explicit screen-state detector. Use confidence thresholds, bounded waits,
   retry limits and a stopped/manual state when the UI cannot be identified.
5. Display the extracted bio and permit correction before evaluating it.
6. Add a versioned eligibility configuration and structured result with reason and evidence.
   Default uncertainty handling must be configured; no silent guessing.
7. Add operator actions `Search`, `Read Bio`, `Approve Partner`, `Next Partner`, `Pause`
   and `Take Over`. Keep partner skipping and sending supervised at this stage.
8. Create an isolated temporary session for each new partner. Clear the previous active
   context on a partner change; do not leak one person's bio into another conversation.
9. Add a simple approved greeting/draft path and record input, draft, final text and
   operator edits. No Telegram invitation automation or payment processing yet.
10. Test at least 20 controlled UI/state cases, including missing bios, slow matching,
    disconnection, wrong window, low confidence, repeated trigger and application restart.

v0.6.0 passes when the operator can search, inspect/evaluate a bio, accept or skip the
partner, start the correct isolated conversation and stop the workflow reliably.
Unexpected state must stop the action, not click blindly or repeat indefinitely.

## Dialogue, training and evaluation

Start from the owner's approved example conversations and a persona specification.
Separate generic style from domain rules. A LoRA may learn phrasing and dialogue style;
payment status, customer memory and changing business facts remain external.

Collect datasets throughout the milestones. Record corrections and label why a
conversation ended. Split evaluation by customer/conversation, remove identifying data
not required for training, and retain a held-out set. LoRA training uses the owner's
permitted dataset on top of an independently pretrained base model.

Measure English-only adherence, conversational coherence, style agreement, unsupported
claims, appropriate invitation timing, rejection handling and operator correction rate.
Use successful payments as one outcome signal, never as proof that every preceding
message should be imitated. Train candidates offline, compare them, approve release and
retain rollback. Live conversations do not directly mutate the deployed model.

## v1.0.0 acceptance gates

- Demonstrate the entire flow with controlled accounts: search -> bio -> decision ->
  small talk -> accepted invitation -> Telegram start -> offer -> sandbox payment ->
  verified status -> durable memory -> returning-customer recognition.
- Demonstrate unsuitable/uncertain bio, declined invitation, expired/forwarded link,
  disconnect, model timeout, restart and operator takeover paths.
- Invalid signatures, wrong amounts, wrong customers and uncompleted payments cannot
  mark a customer paid. Replayed events cannot duplicate payment or memory promotion.
- No cross-customer context leakage, duplicate ownership or blind resend after an
  uncertain desktop action in the acceptance suite.
- All outgoing actions are auditable; autonomous mode is bounded by approved policy,
  search/contact limits, platform support and a working stop mechanism.
- Model version, prompt version, policy version and payment references are traceable.
- Scope for v1.0.0: one Anonchat acquisition session plus linked Telegram conversations.
  Do not claim 100-session production capacity without a separate measured load test.

## Capabilities after v1.0.0

- **v2.0.0 proposal:** choose and send approved existing images/attachments. No image
  generation required. Commercial performance is measured independently of this feature.
- **v3.0.0 proposal:** generate and send images through a separate image model and,
  where appropriate, a separate owner-data image LoRA.
- **Later independent modules:** customer-service workflows, customs drafting,
  additional channels and evaluated training improvements. Each has its own release gate.

No character-design or video-call roadmap is included. Keep the event/action interface
extensible so future media features do not require replacing the text core.

## Deployment and long-term capacity

Keep the controller and persistent state separate from GPU inference. Use local storage
for the initial pilot, then a durable server database, per-conversation queue and object
storage when moving to multiple users. Linux/SSH and Runpod can host the text inference
and backend while the Anonchat desktop adapter remains local if no supported API exists.

One desktop focus cannot safely serve 100 simultaneous UI conversations. The long-term
100-chat goal needs supported API channels, scheduling, isolation, rate limits and measured
inference capacity. Load-test gradually, with specified message rates, context lengths,
burst behavior, response latency and a budget. Open sessions do not equal simultaneous
model generations. This is a separate scaling track, not an unstated v1.0.0 promise.

## Inputs required next

For v0.6.0: exact Anonchat app URL/version, observable eligibility/rejection criteria,
and a few representative bios/screens from controlled testing.

For dialogue/LoRA: permitted conversation exports, desired persona/style, invitation
criteria and how refusals/endings should be handled.

For Telegram/payment milestones: bot credentials provided securely, configured offering,
merchant/payment setup and sandbox accounts. Store/product design is intentionally
deferred, but a concrete commercial configuration is required before live charging.
