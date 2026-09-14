# Changelog

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
