# Changelog

## 2026-10-15

Top-ups, account info for chargebacks, release notes and webhooks, and every change is now
safe to retry.

- `/topup start` opens a crypto payment for your balance and shows the exact amount to send,
  the address, any memo or tag the coin needs and a link to the checkout page. `/topup status`
  and `/topup list` follow it until the money lands. Starting one needs the new
  `billing.topup` scope, which `ROLES_BILLING` now includes.
- `/accountinfo request` asks for the account history of whoever redeemed a key, for a
  chargeback or a dispute. `/accountinfo status` shows where it stands and attaches the zip
  once it is approved, and `/accountinfo list` shows your recent requests. They need the new
  `accountinfo.request` and `accountinfo.read` scopes, both part of `ROLES_SUPPORT`.
- `/changelog` shows what changed in the loader and each product, in English, Russian or
  Chinese.
- `/webhooks` lists your Discord webhooks and can send a test post, pause one or turn it
  back on.
- `/redemptions` lists the latest keys your customers redeemed, `/online` shows who is online
  right now and `/customers keys` lists every key you sold one customer.
- `/stats` adds live customers, who is online, unread tickets and a line for the last 7 days.
- `/tickets read` marks the thread read, the same as opening it in the partner panel.
- Refunds, resets, tickets, replies, branding changes, top-ups and account info requests send
  an `Idempotency-Key` built from the interaction. A retry after a dropped connection gets the
  first result back instead of doing the work twice, and a request that is still running is
  waited out for up to a minute, the way `/keys buy` already was.
- A `429` with a `Retry-After` longer than 30 seconds, such as the limit on opening tickets,
  is reported straight away instead of being retried into the same limit.

## 2026-10-13

A purchase that is still going through stays reported that way when the network acts up.

- Once the API has answered a `/keys buy` with `in_progress`, a later timeout, dropped
  connection, 5xx, 429 or unreadable error page no longer reads as "try again". The bot
  says the purchase is still going through and to check `/keys list` before buying again.
  A definite answer such as `insufficient_balance` still comes through as itself.
- The wait for an in-progress purchase stops at its minute instead of sleeping past it.
- `Retry-After` is read once per response, and values like `1.5` or an HTTP date no longer
  break it. Python gave up on them, and Node retried a rate-limited API without waiting.
- A key code, customer ref or ticket ref of `.` or `..` no longer reaches a different
  endpoint. The bot answers "Nothing matched that." without calling the API. The Python
  client also keeps `;`, `&` and similar characters encoded, the way Node sends them.
- Plan autocomplete and the commands share one permission check, so the two cannot drift
  apart again.

## 2026-09-24

Buying waits out slow purchases, and plan autocomplete respects roles.

- `/keys buy` now waits out a purchase that is still running. The API answers a retry that
  arrives before the first request finishes with `409 in_progress`, and the bot resends the
  same `reference` after the `Retry-After` it gets (up to a minute) instead of reporting a
  failure. If it is still unresolved after that, the bot says so and points at `/keys list`
  rather than inviting a second purchase.
- Plan autocomplete on `/keys buy` checks the same server and role scopes as the command.
  Before, a member without the keys role, or another server entirely, could list your plan
  ids and prices through it.
- The Python client URL-encodes key codes, customer refs and ticket refs in request paths,
  so a customer named `a?b` or `../stats` reaches the right endpoint. Node already did.
- A machine reset by customer logged the wrong variable afterwards: Node threw after the
  reset had gone through, and Python printed a builtin in place of the customer id.

## 2026-09-14

Buying is now safe to retry.

- `/keys buy` sends the interaction id as the `reference` on `POST /keys`, which the API
  now treats as an idempotency key. If the connection drops after the batch was minted,
  the bot retries and gets the same keys back instead of a second batch and a second
  charge. You will see `idempotent-replayed: true` on those responses if you look.
- Because of that, the client retries `POST /keys` on 5xx and network errors the same way
  it already retried GETs. Nothing else changed for other commands.

## 2026-09-13

Wardogs is public, so the bot stops assuming every game is Rust.

- `/updates [product]` takes a game, `rust` or `wardogs`, and says which one it is showing.
- `/plans` prefixes every row with its product, so the Rust and Wardogs month plans no
  longer look identical.
- `/customers` and `/customer` now carry a `products` list from the API, one entry per
  product you sold that customer, alongside the summary fields.

## 2026-08-26

Caught the bot up with the six endpoint groups the Partner API just gained.

### New commands

- `/status [product]` shows whether a product is up, updating or detected, and whether
  customer keys are frozen. While a product is frozen nobody loses time, which is the
  question support gets asked most, so it is called out on its own line.
- `/updates` shows the current Rust build, roughly how often builds land, and the last few
  patch notes.
- `/brand show` and `/brand set` read and change your name, colours, store link and the two
  public page toggles. `set` only touches the options you actually fill in.
- `/tickets list | read | open | reply | close` covers support threads end to end, so you can
  answer us without leaving Discord.
- `/activity [limit]` is the same event feed as the Activity page, handy pointed at a log
  channel.

### Changed

- `/customers info` and `/hwid customer` take an id, a username, or any key code you sold
  them. Prefix with `id:`, `username:` or `key:` if a name could be read as something else.
  Looking someone up by key works even after that key expired.

### Permissions

Six new scopes: `status.read`, `brand.read`, `brand.write`, `tickets.read`, `tickets.write`,
`activity.read`. There is a new `ROLES_SUPPORT` group for people who answer tickets and need
to see product status, but have no business near your balance. Existing groups keep what they
had and pick up `status.read`.

Nothing here changes an existing command's behaviour, so upgrading is just a pull and a
re-register.
