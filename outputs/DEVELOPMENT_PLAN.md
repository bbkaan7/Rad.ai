# Modular Chatbot: Revised Development Plan

Application baseline: v0.1.0 (the owner's current version).
First revenue-capable workflow target: v0.6.0. Stable text-first release: v1.0.0.
Start with a lightweight local test LLM. Migrate to Runpod when the workflow passes
the field-readiness and unattended-operation gates below, potentially at v0.6.0 or
v0.7.0. Version numbers alone neither trigger nor guarantee a migration.
This roadmap supersedes the Shopify-oriented plan. No application changes or deployment
are performed by this document. All application text, documentation and identifiers remain English.

## Product definition

The primary objective is to reduce the owner's workload across their activities,
including marketing and customer support, and progressively minimize routine human
intervention through tested automation. Build a reusable, text-first personal work
assistant with replaceable channel adapters, domain policies, model adapters, memory
and tools. Anonchat/Telegram is the first workflow, not the product's permanent boundary.
The first workflow discovers a
suitable conversation partner on Anonchat, conducts small talk, offers a Telegram
handoff into the owner's normal Telegram account private chat, continues an approved
commercial conversation there, and recognizes a
verified PayPal payment. Shopify, stores and product catalogs are not dependencies.

Future domain modules may support customer service or customs-document drafting.
Those modules will need their own data, rules, tools and validation. They are not
implemented or promised by v1.0.0. Video calls and character design are out of scope.

Measure success through operator minutes saved, intervention/correction rate, successful
task completion, error rate and recovery time, alongside commercial outcomes where
relevant. Begin with baseline measurements of the owner's manual process. Increase
autonomy per tested task, not by enabling unrestricted access to every application.
Routine supported actions should eventually execute without repeated approval;
uncertain or exceptional cases should escalate with enough context to resolve quickly.
Keep task-specific permissions, manual override and an emergency stop at every level.

Telegram constraint: use the owner's ordinary Telegram account and the normal application
interface for private chats. Telegram Business, Secretary Mode and Bot API integrations
are explicitly excluded. Do not introduce them as fallback or later default routes.
Natural, owner-style dialogue is a quality objective, not a claim that a human personally
typed every message. No concealment or platform-restriction evasion feature is planned.

## v0.6.0 revenue-capable end-to-end behavior

1. Open or focus the configured Anonchat application and identify its current screen.
2. Locate and activate `Search for partner` using the desktop adapter.
3. Read the new partner's visible bio and the start of the conversation.
4. Evaluate suitability using the operator's explicit, versioned eligibility rules.
5. If unsuitable, use `Next partner` within configured search limits.
6. If eligible, conduct text-only small talk in the configured English persona.
7. When the conversation is receptive, offer a Telegram invitation without repeatedly
   pressuring someone who declines. End or hand over stalled/ambiguous conversations.
8. After the user sends a private message to the owner's normal Telegram username,
   confirm the referral, link that identity and let the desktop account assistant
   take responsibility for the conversation. No customer-facing bot start command is required.
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

- **Channel adapters:** desktop Anonchat and desktop Telegram screen adapters in v0.2.0.
  Customers chat with the owner's normal Telegram account username. Operate the normal
  Telegram application through screen reading and controlled keyboard/mouse actions;
  do not use Business or Bot API integration. Keep
  screenshots, OCR, matching and clicks out of the conversation business logic.
- **Workflow controller:** owns conversation state, search, qualification, takeover,
  retries, timeouts and handoff. The model proposes language and structured decisions;
  the controller authorizes actions.
- **Persona and dialogue:** system instructions, operator examples, a versioned text LoRA
  trained in v0.3.0 and a replaceable inference endpoint. Do not claim the bot is the human
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

## Identity, eligibility and contact rules (v0.4.0 onward)

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

## Anonchat-to-Telegram handoff (v0.4.0 onward)

v0.2.0 operates both applications independently. It does not decide whom to invite,
send invitations autonomously or infer cross-platform identity. The operator chooses
the active chat and any manual identity link. The following handoff policy starts in v0.4.0.

Customer-facing destination: `https://t.me/<account_username>`, opening an ordinary
private chat with the owner's account. The customer must not be sent to a standalone
bot profile or required to press a bot's Start button. Ordinary private chat is the
requirement; this plan does not add a separate Telegram Secret Chat implementation.

Use the ordinary Telegram application's logged-in interface. Read the selected private
chat, generate a reply with the local model, verify the target again and type/send using
the desktop adapter. Restrict operation to operator-selected chats. Handle unread markers,
scroll position, incoming/outgoing bubbles, app focus, disconnects and manual takeover.
Login and any authentication challenges remain operator-controlled. No bot token,
business connection or Bot API reply window is part of this implementation.

Create a random, expiring referral code mapped to the temporary Anonchat session. For
the pilot, ask the arriving user to include the code in their first message, or have the
operator confirm the identity match. Use an ordinary account link and a separately
communicated code. Do not use bot-only `?start=` semantics on a normal account URL.
Keep private context out of the link/code. Codes can be forwarded, so avoid transferring
sensitive history without confirmation; reject reuse by another account. Without a
confirmed match, treat the visitor as a new session rather than guessing by username.

Transfer a bounded summary, known preferences, conversation stage and pending objective.
Mark the Anonchat session `handed_off` to prevent two bots replying in parallel. Until a
valid, matched incoming Telegram message arrives, the handoff remains pending. Support
expired codes, duplicate message events, declined invitations and restart during handoff.

This screen-based private-chat design replaces the earlier standalone-bot and
account-connected Business integration proposals.

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

Before live use, verify the chosen offering and checkout against the applicable payment
provider and channel requirements. A normal-account UI adapter does not establish
eligibility for every offering. Do not assume PayPal works for every future workflow.

## Milestones to v1.0.0

| Release | Scope | Exit criteria |
|---|---|---|
| 0.1.0 | Existing English desktop prototype, local LLM | Preserve the owner's current working version and settings |
| 0.2.0 | Use Anonchat and Telegram screens; match and converse | Start an Anonchat match, exchange multiple text turns on both apps, isolate contexts and operate the correct active chat |
| 0.3.0 | Train and serve the owner's conversational persona | Build a dataset from the owner's chats, train a local text LoRA, load it and evaluate style on held-out conversations |
| 0.4.0 | Decisions, Telegram invitation/handoff and manual photo escalation | Apply configured bio/friend-request/invitation rules; detect photo requests, alert the operator, pause and resume only after operator handling |
| 0.5.0 | Configurable commercial playbook and PayPal sandbox | Verify test payments, match the right customer and promote memory exactly once |
| 0.6.0 | First integrated, revenue-capable workflow | Pass end-to-end tests and a controlled live-payment verification with a configured offering; supervised operation remains acceptable |
| 0.7.0 | Reliability and bounded automation | Recover from disconnects/restarts, prevent duplicate actions, retain human takeover |
| 0.8.0 | Improve the existing dataset and evaluation pipeline | Add reviewed corrections and reproducible model/policy comparisons |
| 0.9.0 | Refine the existing local text LoRA and policies | Improve measured quality and efficiency without regressing payment, memory or operator takeover |
| 1.0.0 | Stable local text-first chatbot | Regression, payment, memory, recovery and operational tests pass for the declared pilot capacity |

Use a lightweight local base model for v0.2.0. Actual owner-data text-LoRA training is
now a v0.3.0 requirement, not a v0.9.0 task. Collect reviewed examples from v0.2.0 onward.
Measure available RAM/VRAM, choose a compatible trainable local base model and training
configuration, and test the serving path before committing to the training run. The
current quantized Ollama artifact is not assumed to be a trainable checkpoint.
If hardware or dataset limits prevent a validated adapter, mark v0.3.0 incomplete or
explicitly agree on a revised scope; do not silently switch to Runpod or substitute a
persona prompt for actual training. Carry the validated adapter into subsequent releases.

Revenue-capable means the configured workflow can receive and verify a legitimate live
payment and recognize the paying customer. Sandbox-only payments do not satisfy v0.6.0.
Actual revenue depends on the offering, customers and conversion; it is not guaranteed
by a version number. No Shopify or fixed product/store dependency is introduced.

## Intermediate releases: supporting improvements

The owner's major/minor milestone scopes above remain unchanged. The releases below
add the review recommendations between those milestones. They do not move persona
training out of v0.3.0, photo-request understanding out of v0.4.0, or commercial readiness
out of v0.6.0. Existing basic stop, isolation and confidence checks remain part of the
base releases; these patches deepen and validate those controls.

Sequence: 0.2.0 -> 0.2.1 -> 0.2.2 -> 0.2.3 -> 0.3.0 -> 0.3.1 -> 0.3.2 ->
0.4.0 -> 0.4.1 -> 0.4.2 -> 0.5.0 -> 0.5.1 -> 0.5.2 -> 0.6.0.

| Release | Supporting improvement | Acceptance criteria |
|---|---|---|
| 0.2.1 | Target verification and stale-reply cancellation | Recheck platform, conversation and incoming-message revision before sending; cancel a draft if the partner/chat changed; uncertain delivery never triggers a blind resend |
| 0.2.2 | Message grouping and stronger manual takeover | Group short bursts using a bounded, configurable wait; re-evaluate drafts after new input; explicit takeover stops queued desktop actions and only explicit resume restarts them |
| 0.2.3 | Replay tests, structured feedback and local training feasibility | Save input/context, model draft, operator correction and sent reply separately; replay without real sends; complete a small local training/serving feasibility test and record resource use |
| 0.3.1 | Persona evaluation and factual separation | Compare the already-trained v0.3.0 adapter against the base on held-out conversations; measure style and coherence, and detect memorized private details or invented personal facts |
| 0.3.2 | Dataset eligibility and model lineage | Record allowed data uses, source and dataset/model versions; reject training-ineligible records; verify deletion handling and rollback to a prior local adapter |
| 0.4.1 | Durable temporary memory and identity reconciliation | Restore unexpired prospect sessions after restart, expire them as configured, support confirmed cross-channel linking, and correct/delete memories without merging similar display names |
| 0.4.2 | Escalation lifecycle and constrained model actions | Deduplicate photo alerts, cancel stale requests and prevent automatic resume; attempts to change rules, expose another person's history or mark payments via chat cannot execute tools |
| 0.5.1 | Payment reconciliation and atomic customer promotion | Process duplicate/out-of-order events and restarts without duplicate sales; handle refunds/disputes; update transaction, customer status and memory-promotion jobs consistently |
| 0.5.2 | Commercial configuration and pilot release rehearsal | Confirm the actual offering/payment method, test the configured end-to-end flow, rehearse backup/restore and rollback, and verify operator monitoring before v0.6.0 live readiness |

These are scoped release checkpoints, not promises about elapsed development time.
Do not introduce unrelated features to fill a patch release. Foundational checks needed
to avoid known wrong-recipient sends must not be disabled just because their expanded
test suite has a later patch number.

### 0.2.1: validate the target immediately before sending

Bind every draft to its platform, session and input revision. Recheck the visible chat
and partner before typing and before sending. An Anonchat partner change invalidates
the draft. A changed Telegram chat cannot receive a queued reply for the previous one.
Persist attempted/sent/uncertain states. If a click may have succeeded but confirmation
is missing, require reconciliation instead of sending again. Recognize outgoing messages
so the bot cannot answer itself. Include tests for switching windows during generation.

### 0.2.2: handle bursts and operator input

Use a short configurable message-grouping delay with a maximum wait, so several quick
customer messages can be answered together without waiting indefinitely. A new incoming
message invalidates or reopens the pending draft before delivery. Keep actual message
events distinct: repeated words are not always duplicates.

Build on v0.2.0's existing Pause/Take Over controls. Cancel queued actions, invalidate
outdated drafts and release the global desktop input lock during takeover. Where manual
input detection is used, distinguish it from the bot's own synthetic input. Require an
explicit resume and reread the chat before replying. Semantic photo-request detection
remains a v0.4.0 feature.

### 0.2.3: make development observable and repeatable

Store the corrected OCR input, relevant context, original draft, operator edit, sent
reply, timestamps and configuration versions separately. A replay runner consumes saved
screens/messages with a disabled send adapter; it must never touch a real conversation.
Use the same fixtures after later screen, prompt or model changes.

Benchmark the current local inference latency and emulator resource use. Run a tiny
local adapter-training/serving compatibility experiment on permitted or authored test
data. This is a feasibility check, not completion of the owner's persona training, which
stays in v0.3.0. Record RAM/VRAM limits and choose a feasible model configuration without
adding a cloud fallback.

### 0.3.1 and 0.3.2: improve an existing persona model

v0.3.0 still performs real dataset preparation, training and evaluation. These patches
strengthen repeatability, regression coverage and data provenance after the first adapter
works. Evaluate observable style traits such as length, vocabulary, humor and question
patterns; do not treat an exact copy of a personality as a measurable guarantee.

Keep transient personal statements and customer facts outside the style adapter. Test
that a past message such as "I am outside now" does not become an unsupported present-tense
claim in unrelated chats. Keep untouched conversation-level test splits.

Track separate permissions/eligibility for operational processing, memory retention
and training use. A chat being accessible to the owner's account does not automatically
make it training-eligible. Baseline permitted-data handling applies from the first data
collection; v0.3.2 adds the explicit tracking and audit mechanism, not delayed permission.
Review each dataset's source, permissions and applicable terms before export. Reading a
conversation through the ordinary application UI does not automatically authorize its
reuse for model training. No Business-derived dataset is assumed by this plan.

### 0.4.1 and 0.4.2: persistence and escalation hardening

Temporary means time-limited, not RAM-only. Persist prospect sessions with expiration
and recover them after restart. Paying-customer promotion changes retention and selected
memory content rather than blindly copying the entire transcript. Keep financial and
minimal opt-out records on their own retention lifecycle. Preserve source/time for a
memory and let the operator correct it.

Extend v0.4.0's photo handoff with repeated-request, operator-away, partner-change and
restart tests. Never automatically resume because an alert timed out. Model outputs are
proposals, not authority: validate actions against configured permissions and state.
Incoming messages cannot override eligibility rules, access other conversations or
authorize refunds/payment status changes. Keep these tests in the replay suite.

### 0.5.1 and 0.5.2: make the existing payment integration reliable

v0.5.0 still implements payment verification and memory promotion in the sandbox.
These patches extend fault handling and operational readiness. Use durable event IDs,
transaction references and an atomic/outbox-style promotion flow so interrupted processing
can recover. Maintain payment and refund/dispute states rather than one success Boolean.

Before v0.6.0, select a concrete offering, currency, merchant setup and fulfillment rule.
Keep the payment adapter replaceable: the appropriate provider depends on the offering
and applicable platform rules; do not assume every future offering can use PayPal.
Keep this decision independent of the normal-account desktop messaging adapter.

Measure draft latency, operator correction rate, wrong-target prevention, duplicate
suppression and payment reconciliation. Rehearse a local database restore and application
rollback. v0.6.0 remains the release gate for controlled real-payment validation and the
integrated revenue-capable workflow. No extra media features are added. Runpod
migration is conditional on the separate field-readiness gate.

## Immediate implementation: v0.2.0

1. Back up v0.1.0 and extract channel, model, memory and controller interfaces without
   introducing store/product dependencies.
2. Confirm the exact Anonchat app/version and Telegram client, using controlled accounts.
   Capture Anonchat home/searching/connected/disconnected states and Telegram's chat list,
   active private chat, message area, textbox and error states.
3. Build separate screen profiles and references for each app. Include Anonchat
   `Search for partner`, operator-requested `Next partner`, textboxes and send controls.
   Use the normal Telegram account's private-chat screen, not a standalone bot profile.
4. Implement screen recognition with confidence thresholds, bounded waits and retries.
   Opening/focusing apps and choosing the operator-selected chat are supported actions.
   Unknown screens stop the action instead of causing blind clicks.
5. Read the conversation area, distinguish incoming/outgoing messages and detect new
   incoming text. Show the extracted text and permit manual correction or pasted input.
6. Create isolated per-platform, per-conversation temporary context. Clear Anonchat's
   active context when a new partner is matched; never reuse another chat's history.
7. Connect the local LLM to a multi-turn text reply loop on both platforms. The operator
   can initiate Anonchat search and enable text replies for the selected conversation.
   Include draft/approval mode and a bounded automatic text-reply mode for controlled tests.
8. Prevent repeated replies to the same message event, responding to the bot's own
   messages, cross-window sends and blind retries after uncertain delivery. Serialize
   desktop actions: one keyboard/mouse focus at a time, even when both apps are open.
9. Provide `Start Search`, `Next Partner`, `Select Chat`, `Draft Mode`, `Auto Reply`,
   `Pause` and `Take Over`. Record inputs, drafts, sent text and operator edits for v0.3.0.
10. Test at least 20 controlled cases across both apps: new match, multi-turn conversation,
    switching apps, disconnect, missing controls, OCR errors, repeated text, model timeout,
    restart and emergency stop. Include an actual send/receive test on each platform.

v0.2.0 passes when it starts an Anonchat match and sustains a text exchange, then operates
an operator-selected Telegram private chat with the correct independent context. It may
search for another partner on operator command or the configured disconnected-state rule.
It does not decide partner suitability, friend requests, Telegram invitations, cross-channel
handoff, payment or photo-request escalation. Bio classification is not a release gate.
Basic UI confidence checks and stop conditions remain necessary technical safeguards;
these are distinct from the conversational/business decisions deferred to v0.4.0.

## v0.3.0: actual persona training

1. Prepare the owner's permitted conversation exports with explicit speaker roles.
2. Use the owner's replies as training targets, with preceding dialogue as context.
   Remove unnecessary identifiers, secrets, duplicates and corrupted OCR samples.
3. Split by conversation/customer into training, validation and untouched test sets.
4. Define observable persona traits: wording, sentence length, humor, emotional tone,
   question style, boundaries and English-language behavior. Keep personal facts and
   customer-specific memories separate from general style examples.
5. Benchmark local resources and select a compatible small base model and LoRA setup.
   Train on local hardware and save the adapter, tokenizer/base references and dataset version.
6. Load the trained model/adapter into the local serving path used by both chat adapters.
7. Compare the base model and trained version on held-out prompts and controlled chats.
   Check style, coherence, memorized private details, unsupported personal claims and latency.
8. Promote only an evaluated adapter and preserve rollback to the base model.

The objective is to reproduce the owner's approved writing style/persona, not to promise
an exact copy of their personality or fabricate personal experiences. Prompt-only persona
configuration is useful during development but does not complete the training milestone.

## v0.4.0: decisions and operator-assisted photo requests

Add configurable decisions for bio suitability, next-partner selection, friend-request
handling, Telegram invitation timing and cross-platform handoff. Each decision records
its reason and relevant evidence; uncertain cases can request operator input.

Photo requests use this state flow:
`chatting -> photo_request_detected -> awaiting_operator -> operator_done -> chatting`.

- Recognize direct and indirect photo requests in context; uncertain requests can be
  clarified or flagged rather than triggering repeated alerts.
- Notify the operator through an English desktop alert/sound and a visible task containing
  the platform, conversation, original request and short context. The operator-alert
  mechanism is independent of messages sent to the customer.
- Pause automatic replies for that conversation and release desktop input control during
  manual takeover. Do not claim a photo has been sent or promise immediate fulfillment.
- The operator chooses, sends or declines the photo directly in the application. The bot
  neither selects an attachment nor clicks send for the image in this release.
- Resume only after an explicit `Photo Sent`, `Declined` or `Resume` action. Record the
  outcome, include relevant intervening messages, and cancel stale requests if the session ends.
- Deduplicate repeated alerts for the same pending request. Verify that automation cannot
  interrupt manual typing, switch the active window or resume after a timeout on its own.

No image generation, automatic photo sending, OBS or video-call capability is included.

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

## v0.6.0 commercial acceptance gates

- Demonstrate the entire flow with controlled accounts: search -> bio -> decision ->
  small talk -> accepted invitation -> normal-account private message and verified handoff -> offer -> sandbox payment ->
  verified status -> durable memory -> returning-customer recognition.
- Demonstrate unsuitable/uncertain bio, declined invitation, expired/forwarded link,
  disconnect, model timeout, restart and operator takeover paths.
- Demonstrate photo-request detection, operator notification, paused input, manual
  completion/decline and explicit resume without an automatic image send.
- Verify Telegram chat isolation, focus/scroll changes, disconnect recovery and takeover.
  Customers use the normal account private chat throughout; Business and Bot API
  adapters must not be installed as an alternative route.
- Invalid signatures, wrong amounts, wrong customers and uncompleted payments cannot
  mark a customer paid. Replayed events cannot duplicate payment or memory promotion.
- No cross-customer context leakage, duplicate ownership or blind resend after an
  uncertain desktop action in the acceptance suite.
- All outgoing actions are auditable; autonomous mode is bounded by approved policy,
  search/contact limits, platform support and a working stop mechanism.
- Model version, prompt version, policy version and payment references are traceable.
- After sandbox validation, demonstrate a controlled, authorized live transaction for
  the configured offering. Confirm the correct paid-customer record and durable memory.
- Scope for v0.6.0: one Anonchat acquisition session plus linked Telegram conversations.
  The operator may supervise search, replies and exceptional actions; full autonomy is
  not required for the first commercial workflow.

## v1.0.0 stability acceptance gates

Preserve the working v0.6.0 commercial flow while adding tested recovery, bounded
automation, repeatable evaluation and the agreed text-LoRA milestone. Validate local
latency and resource use on the actual machine. Document supported pilot capacity,
known limits and rollback steps. Do not claim 100-session production capacity without
a separate measured load test. Heavy models, media and Runpod are not release gates.

## Capabilities after v1.0.0

- **v2.0.0 proposal:** choose and send approved existing images/attachments. No image
  generation required. Commercial performance is measured independently of this feature.
- **v3.0.0 proposal:** generate and send images through a separate image model and,
  where appropriate, a separate owner-data image LoRA.
- **Later independent modules:** customer-service workflows, customs drafting,
  additional channels and evaluated training improvements. Each has its own release gate.

No character-design or video-call roadmap is included. Keep the event/action interface
extensible so future media features do not require replacing the text core.

## Local-first development and readiness-based Runpod deployment

Run the controller, temporary/durable memory and lightweight text inference locally
during development. Retain the existing Ollama model initially and measure it on the actual
machine before selecting another locally affordable model. The model endpoint stays
configurable so future migration does not change channel or workflow logic.

Bound context length, summarize older messages, limit concurrent generations and log
latency plus memory use. Reserve resources for the emulator and desktop. Use a local
database with backups for the pilot. Do not rent Runpod instances or introduce
an automatic cloud-model fallback before the migration gate and an explicit budget decision.

Local inference does not mean offline operation: Anonchat, Telegram and PayPal still
require connectivity. Telegram uses its normal-account desktop screen adapter throughout
the current roadmap. PayPal webhooks need
a reachable HTTPS receiver, such as a secured tunnel to the local service or a small
independent webhook relay. This is payment connectivity, not a Runpod/model migration.
Reconcile missed events after downtime and never expose local admin/model ports openly.

Runpod may be introduced at v0.6.0 or v0.7.0 if field tests justify it; there is no
requirement to wait until after v1.0.0. Conversely, reaching v1.0.0 does not prove
that unattended operation is ready. Complete a deployment compatibility experiment
before moving production: the current Windows screen adapter and BlueStacks setup
cannot be assumed to transfer unchanged to a Linux/SSH environment. Prove that the
required normal application interfaces can run on the chosen worker architecture.
Do not substitute Telegram Business or Bot API to make deployment easier.

Before migration, demonstrate all of the following in controlled pilots:

- Several full-day runs at intended pilot volume, with measured response quality,
  no wrong-recipient sends, no duplicate sends after restart and tracked interventions.
- Recovery tests for model timeout, network loss, app restart, worker restart and
  payment-event replay. Restore state and backups; never blindly repeat a send.
- A clear unattended policy for unsupported requests, login challenges and account
  restrictions. Defer, decline or stop the affected workflow safely. Automatic
  completion of every possible situation is not a realistic release promise.
- The v0.4.0 manual-photo flow must not block other sessions indefinitely. In unattended
  mode, acknowledge the limitation and queue it for later or decline according to policy;
  do not claim a photo was sent or secretly add image generation.
- Remote pause, health monitoring, a bounded daily spend, per-session limits,
  retained session state and secure recovery access. Model and admin ports stay private.

The migration target is unattended handling of supported routine work, not zero
maintenance forever. If the gate fails, continue locally and fix the measured gaps.
Moving to a remote GPU does not itself remove an operator dependency.

One desktop focus cannot safely execute simultaneous UI actions in 100 conversations.
The long-term 100-chat goal is unresolved under the normal-application constraint:
it requires measured scheduling of serialized UI actions or separately isolated desktop
workers, plus sufficient inference capacity. Do not promise that 100 windows or a larger
model solves it. Do not replace the requested Telegram interface with a banned integration
to meet the target. Load-test gradually, with message rates, context lengths,
burst behavior, response latency and a budget. Open sessions do not equal simultaneous
model generations. This is a separate scaling track, not an unstated v1.0.0 promise.

## Inputs required next

For v0.2.0: exact Anonchat app URL/version, Telegram client, and representative search,
match and private-chat screens from controlled testing. Eligibility criteria are not
required to begin this release.

For v0.3.0: permitted conversation exports, desired persona/style, and local RAM/GPU/VRAM
information so actual training fits the user's machine.

For v0.4.0: eligibility, friend-request and invitation rules, plus preferred operator
notification behavior for photo requests and other uncertain cases.

For Telegram/payment milestones: the owner's normal account and logged-in application,
selected allowed chats, configured offering,
merchant/payment setup and sandbox accounts. Store/product design is intentionally
deferred, but a concrete commercial configuration is required before live charging.
