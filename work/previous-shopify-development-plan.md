# AI Sales Assistant: Development Plan

Planning baseline: application v0.5.0. Next proposed release: v0.6.0.
This document is a roadmap, not an implementation or deployment record.
All application UI, logs, configuration, prompts and documentation remain English.

## Objective

Build an assistant that follows the owner's approved sales style, remembers customer
preferences, recommends products from one or more Shopify stores, generates approved
visuals, supports a Telegram handoff, verifies purchases, and improves through reviewed
training batches. Start with one manually supervised customer. Eventually support 100
concurrent conversations through supported integrations and a Linux-operated backend.

## Architectural decisions

- Separate channel adapters, conversation logic, customer memory, commerce, image
  generation and training. Reuse the same conversation core with desktop and API channels.
- Identify the assistant as a store assistant. Present generated images as generated
  previews; virtual-camera transport must not imply an authentic live photograph.
- Use the owner's permitted conversation examples for style training. Remove unnecessary
  customer identifiers from training exports and support retention/deletion controls.
- Store prices, inventory, payment status and customer memory outside model weights.
  Retrieve current commerce facts and relevant memories when generating a response.
- Treat incoming messages as untrusted content. A message cannot grant tool permissions,
  change another customer's records, override prices or mark an order as paid.
- Keep discounts, refunds, exceptional promises and ambiguous requests within explicit
  operator limits. Support pause, takeover and an auditable action history.

## Feasibility gates

**Snapchat:** the documented Messaging API covers brand/creator conversations and
requires allowlist access. It does not establish general private-chat automation support.
Creative Kit shares content to Snapchat's camera/preview workflow. Confirm the exact
account and channel capabilities before promising a headless implementation.
[Messaging API](https://developers.snap.com/marketing-api/Public-Profile-API/Messaging),
[Creative Kit](https://developers.snap.com/snap-kit/creative-kit/overview).

**Anonchat:** obtain the exact app/store URL and identify its supported integration
surface. API availability has not been verified. Keep a manual or permitted desktop
adapter until a supported headless interface is established. Do not make production
capacity depend on an undocumented private API or bypassing platform controls.

**Telegram:** an ordinary bot needs the user to start the interaction. A deep link with
an opaque, expiring referral token can connect the invited conversation to the Telegram
session. Do not merge identities by display-name similarity.
[Bot introduction](https://core.telegram.org/bots),
[Deep linking](https://core.telegram.org/bots/features#deep-linking).

**Payments:** decide the payment flow after identifying the product category, store,
merchant account and supported integration. In-bot digital goods have Telegram-specific
payment requirements; do not assume every product can use the same PayPal flow.
[Telegram payment overview](https://core.telegram.org/bots#receive-payments).

**OBS:** OBS can expose a scene as a webcam source. That alone does not prove an Android
emulator or target application's photo workflow can consume it. Test the entire route
before automating it. Use an ordinary image attachment when supported.
[OBS virtual camera](https://obsproject.com/kb/virtual-camera-guide).

## Release roadmap

| Release | Outcome | Exit gate |
|---|---|---|
| 0.5.0 | Current English desktop prototype | Preserve as a recoverable baseline; full sales flow is not yet validated |
| 0.6.0 | One-store, one-customer supervised sales copilot | Complete a reviewed conversation, optional manual visual, checkout handoff and operator-verified outcome |
| 0.7.0 | Telegram handoff, commerce integration and verified payment events | Match a test order to a customer; reject invalid events; handle duplicates and refunds |
| 0.8.0 | Image generation service and optional OBS bridge | Request-to-preview-to-approved-send works; camera compatibility explicitly demonstrated |
| 0.9.0 | First owner-data text LoRA and separate image LoRA | Beat the baseline on held-out evaluation without identity, price or store leakage |
| 0.10.0 | Multiple stores and a 10-20-conversation pilot | Store isolation, human takeover, routing and recovery pass testing |
| 1.0.0 | Linux-operated service with 100 concurrent sessions | Pass specified sustained and burst load tests on supported channels |
| 1.1.0 | Reviewed continual improvement pipeline | Candidate training, evaluation, approval, canary rollout and rollback operate reliably |

Version numbers describe planned increments, not delivery dates. Platform access and
evaluation results determine whether a release gate can be passed.

## First release: v0.6.0 implementation sequence

### 1. Freeze the baseline and select the pilot

Back up v0.5.0 and current settings. Select one store, one channel, one operator and
one consenting test customer/account. Write a short product sheet: descriptions,
variants, price/currency, delivery, refund terms, checkout URL and allowed discounts.
Identify the exact Anonchat application and review available integration options.

Deliverable: pilot configuration and a written acceptance checklist.

### 2. Separate the current script into reusable components

Extract capture/OCR, reply generation, desktop actions, sessions, memory and logging.
Define a channel interface for receiving messages and sending text/media. Include a
manual paste/copy adapter so the sales workflow remains testable if OCR or UI matching
fails. Keep existing Windows key polling and preserve the user's model/Tesseract settings.

Deliverable: the same business flow works with desktop OCR and manual message input.

### 3. Make input selection explicit

Allow selection of the message region and reference images. Show the screenshot crop
and OCR result before generation. Permit correction of OCR text. Assign a session ID
and distinguish incoming customer text from outgoing assistant text and UI labels.
Do not assume the bottom OCR line is always the latest customer message.

Deliverable: the operator can identify and correct exactly what the model will read.

### 4. Add review before sending

Change F9 to capture and draft, not immediate sending. Provide English controls:
`Generate`, `Edit`, `Approve & Send`, `Reject`, `Pause`, and `Take Over`.
Recheck the selected target before sending; stop when the target is ambiguous or changed.
Persist a send-attempt record. If delivery is uncertain, ask for reconciliation rather
than retrying blindly. Block repeated processing of the same event/capture within a
session without treating every repeated word as a duplicate message forever.

Deliverable: no outgoing message without operator approval in this release.

### 5. Configure the owner's voice and sales rules

Start with an English style guide and 20-50 selected, permitted example responses:
greetings, product questions, objections, budget discussions, invitations and follow-up.
This is a pilot starting point, not a sufficient-data claim for LoRA training.
Keep approved product facts in a structured file, separate from writing-style examples.
Use examples and retrieval first so the pipeline works before training a custom adapter.

Deliverable: draft responses follow the intended tone and use approved product facts.

### 6. Persist customer context

Use SQLite for the one-user local pilot, behind a repository interface. Store customer
and conversation IDs, platform, store ID, messages, a concise summary, explicitly stated
preferences, product interests, objections and prior offers. Record source and timestamp
for memories, permit correction/deletion, and avoid presenting inferred personality
traits as facts. Never mix customers merely because their visible names match.

Deliverable: restarting the program preserves the selected customer's context.

### 7. Support the first manual sales handoff

Keep conversation stage and payment state separate. Suggested conversation stages:
`new`, `engaged`, `qualified`, `offered`, `handed_off`, `closed`, `needs_review`.
Suggested order states: `not_created`, `pending`, `paid`, `refunded`, `disputed`.
Offer a Telegram link when appropriate and accepted. In v0.6.0, the operator may perform
the actual cross-channel handoff and link identities after confirmation.

Use a store checkout/order reference to link the conversation and purchase. The
operator verifies payment in the merchant dashboard before selecting `Paid` and records
the external order/transaction ID. A customer saying "I paid" is not payment evidence.

Deliverable: a complete manual end-to-end sale or labelled non-sale outcome.

### 8. Add a manual visual branch

Record the visual request, attach an operator-provided or manually generated preview,
and approve it before sending. Record the image source and model version if known.
If virtual-camera delivery is essential to the pilot, first test a static image in OBS
with a controlled account: OBS scene -> virtual camera -> emulator/app preview -> photo.
If that route fails, use a supported attachment or manual transfer without blocking the
text pilot. Describe synthetic previews accurately.

Deliverable: one reviewed visual reaches the intended test customer; automated image
generation and custom image training remain later release work.

### 9. Capture feedback for future training

Save the original incoming message, relevant context, model draft, operator edit,
final sent response, model/prompt version and outcome separately. Label failures with
reasons such as price mismatch, no response, wrong product or poor reply. A no-response
conversation is not automatically a bad example, and a sale is not proof every reply
was good. Export approved, redacted JSONL records; exclude secrets and payment details.

Deliverable: a usable reviewed dataset grows during normal pilot operation.

### 10. Run acceptance tests and release

Proposed pilot targets:

- Complete at least 20 varied test exchanges, including objections and unclear requests.
- Zero observed unapproved sends, wrong-recipient sends or duplicate sends in these tests.
- Pause and human takeover work; timeout/failure does not trigger a blind resend.
- Restart and resume the same customer without mixing another customer's records.
- Unknown price/stock questions ask for confirmation instead of inventing facts.
- Complete one test checkout and manually verify its external reference.
- Export the corresponding conversation, correction and outcome records.
- All app-authored messages and controls are English; `--version` reports 0.6.0.

These gates validate the pilot, not production reliability. Measure response time and
operator correction rate to establish a baseline before choosing a larger model or GPU.

## Production architecture

Channel adapters -> normalized events -> per-conversation queue -> conversation service
-> memory/catalog retrieval -> text model -> action validation -> approval or bounded
automatic execution -> channel delivery -> audit/event records.

Use a separate image-job queue and GPU worker. Keep the conversation responsive while
images are generated, and discard/cancel stale jobs after takeover or conversation closure.

Suggested implementation progression: Python service and SQLite first; PostgreSQL,
optional pgvector retrieval, a durable queue and an object store when moving to multiple
users. Keep store IDs on customer, conversation, product, order and retrieval records.
Store secrets outside logs and datasets. Protect administrative and model endpoints.

Use a stable CPU service for routing, durable state and payment webhooks; Runpod GPU
workers serve models or run training jobs. Operate via Linux/SSH, containers and a CLI.
Keep databases, checkpoints and backups outside disposable worker filesystems. A
headless backend does not make an unsupported chat platform headless.

## Payment verification in v0.7.0

For Shopify checkout, use the store order/payment integration as the order source of
truth. If using direct PayPal checkout, associate the provider order/capture ID with the
conversation and store. Do not assume Shopify-managed payments appear in a separately
created PayPal developer application's webhooks.

Verify webhook authenticity, deduplicate event IDs, validate merchant/store, order,
amount and currency, and reconcile delayed/out-of-order events with provider records.
Only verified payment transitions set `paid`. Handle refunds/disputes as later state
changes; do not permanently label a refunded order as a successful sale.
[PayPal verification](https://developer.paypal.com/api/rest/webhooks/rest/),
[Shopify verification](https://shopify.dev/docs/apps/build/webhooks/verify-deliveries),
[Shopify event topics](https://shopify.dev/docs/api/webhooks/unstable).

## Custom models and learning

Use separate text and image models/adapters. A text LoRA learns response style and sales
dialogue patterns; an image LoRA learns approved visual subjects/styles. The adapter
training data can be entirely the owner's dataset, but the underlying pretrained base
model was trained separately. This is not training a whole foundation model from scratch.
[PEFT documentation](https://huggingface.co/docs/transformers/main/peft).

Split data by customer/conversation, not random message rows. Keep an untouched test set,
remove duplicates, version dataset snapshots and evaluate against the untuned baseline.
Exclude OCR mistakes, prompt injections, contradictory facts and sensitive identifiers.
Use corrected responses for supervised training; rejected drafts can become reviewed
preference pairs later. Keep current product facts in retrieval rather than the adapter.

Continual improvement means: collect -> review -> build a versioned dataset -> train a
candidate -> evaluate -> approve -> limited rollout -> monitor -> promote or roll back.
Never let live sales outcomes immediately rewrite the serving model without evaluation.
Track correctness, owner-style agreement, correction rate, complaints, refunds, response
latency and cost alongside conversion. Preserve old model and adapter versions.

## Capacity planning for 100 chats

One hundred open conversations is not the same workload as 100 simultaneous generations.
As an illustrative workload, 100 customers each sending one message per minute means
about 1.67 generation requests/second. At 120 output tokens per reply, that is roughly
200 output tokens/second, before input processing, context length and burst headroom.
Actual GPU requirements must be benchmarked; no hardware or budget guarantee is implied.

Use batching and bounded concurrency for text inference; queue image generation
separately. Runpod supports a vLLM serving path that can be evaluated for the selected
model and adapter combination.
[Runpod vLLM](https://docs.runpod.io/serverless/vllm/overview).

Define the 1.0.0 benchmark before buying capacity: 100 persistent sessions, specified
message rate and context length, a simultaneous-message burst, image request mix,
target p95 latency, maximum queue delay, retry/restart recovery and cost ceiling.
Measure per-store/customer isolation and zero duplicate side effects. Scale from
1 to 5 to 20 to 100; do not infer capacity from a single fast response.

## Inputs needed to begin v0.6.0

1. The pilot store and product category (physical goods, digital goods or services).
2. The exact Anonchat application URL and preferred first channel.
3. Available conversation data: format, approximate count and permission to use it.
4. The intended visual content and whether virtual-camera transport is mandatory.
5. Merchant/payment setup and an initial infrastructure budget when deployment starts.

The immediate build target is a supervised sales copilot with persistent context and
reviewed data collection. No model training, account messaging or deployment is
authorized by this planning document alone.
