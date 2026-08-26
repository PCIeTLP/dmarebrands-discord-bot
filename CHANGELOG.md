# Changelog

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
