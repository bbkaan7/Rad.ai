# Rad.ai 0.2.8 — Vidogram validation

- 51 unit/regression tests passed; pip check passed; version reports 0.2.8.
- Vidogram package and launcher alias were queried from the installed Android package.
- Live authenticated XML: conversation header, incoming text, outgoing accessibility
  metadata, message composer and Send control inspected in the test conversation.
- User-approved test message sent once and confirmed in outgoing XML. The first
  center tap hit the overlapping editor; the draft was verified unsent before a
  corrected exposed-area tap completed the approved send. No duplicate was sent.
- Vidogram current-conversation polling passed twice without sending messages.
- Live AnonChat -> Vidogram -> AnonChat switches validated by package-scoped XML.
  A subsequent Vidogram dump encountered a transient idle-state failure; bounded
  read-only retry was added and regression-tested, then live polling passed.
- Vidogram's current home layout does not expose named chat rows. Current-conversation
  mode is enabled. Switch conversations manually in Vidogram; automatic multi-chat
  discovery is not claimed for this layout. The list search field is not a composer.
- Reply/delete/friend actions were not live-tested in this turn.
- No account credentials or private XML are distributed. The local model is unchanged.
