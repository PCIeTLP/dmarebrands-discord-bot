# dmarebrands Discord bot

**Built for partners of [dmarebrands.st](https://dmarebrands.st).** If you resell dmarebrands
keys, this lets you run the whole operation from your own Discord server: buy keys, refund
unsold stock, reset a customer's hardware lock and read your balance without opening the
partner panel.

You need a partner account and an API key to use it. Everything it does goes through the
[Partner API](https://partners.dmarebrands.st/partners/api/docs), so it can only ever touch
keys you issued and the customers who redeemed them.

Two complete implementations, same commands, same permission model. Pick whichever stack you
already run:

| | |
|---|---|
| [`node/`](node) | Node.js 20+, [discord.js](https://discord.js.org) v14 |
| [`python/`](python) | Python 3.10+, [discord.py](https://discordpy.readthedocs.io) v2 |

Both talk to the [dmarebrands Partner API](https://partners.dmarebrands.st/partners/api/docs).

## Commands

| Command | What it does | Scope needed |
|---|---|---|
| `/account` | Partner account, brand and headline numbers | `account.read` |
| `/plans` | Every plan with your discounted price | `account.read` |
| `/stats` | Keys issued, active, expired, customers | `account.read` |
| `/balance` | Available balance and how to top up | `billing.read` |
| `/ledger [limit]` | Recent movements on the balance | `billing.read` |
| `/keys list [filter] [search] [limit]` | Keys you have issued | `keys.read` |
| `/keys buy <plan> [count]` | Mint new keys against your balance | `keys.buy` |
| `/keys info <code>` | One key, including who redeemed it | `keys.read` |
| `/keys refund <code>` | Destroy an unsold key, money back | `keys.refund` |
| `/customers list [search] [limit]` | Everyone who redeemed your keys | `customers.read` |
| `/customers info <id>` | One customer and their machines | `customers.read` |
| `/hwid key <code>` | Clear their hardware lock, by key | `hwid.reset` |
| `/hwid customer <id>` | Clear their hardware lock, by id | `hwid.reset` |
| `/domains` | Your white-label domains and DNS state | `domains.read` |
| `/whoami` | What the bot will let *you* do | none |

Anything that spends or destroys money asks for confirmation first, and shows you the exact
amount before you commit.

## Permissions

Roles map to scopes through five environment variables. A member gets the **union** of every
group their roles appear in, so you can stack them.

```dotenv
ROLES_ADMIN=111111111111111111
ROLES_KEYS=222222222222222222
ROLES_HWID=333333333333333333,444444444444444444
ROLES_BILLING=555555555555555555
ROLES_READ=666666666666666666
```

| Group | Grants |
|---|---|
| `ROLES_ADMIN` | everything |
| `ROLES_KEYS` | buy, refund, read keys and customers |
| `ROLES_HWID` | reset hardware locks, read keys and customers |
| `ROLES_BILLING` | balance and ledger |
| `ROLES_READ` | read-only across the board |

**To give a role nothing but HWID resets, put it in `ROLES_HWID` and nowhere else.** That role
can look up a key or customer to find who they are resetting, and clear the lock. It cannot see
your balance, cannot buy, cannot refund.

Every command is checked before it runs. A role that is not listed in any group gets nothing,
so a leaked role never turns into spending power. `/whoami` shows a member exactly what they
have, which saves a lot of "why can't I use this".

## Setting up the Discord application

1. Go to the [Developer Portal](https://discord.com/developers/applications) and create an
   application. The **Application ID** on the General Information page is `DISCORD_APP_ID`.
2. Open **Bot**, click *Reset Token*, copy it into `DISCORD_TOKEN`. Never commit this.
3. No privileged intents are needed. Leave Message Content off.
4. Open **OAuth2 → URL Generator**, tick `bot` and `applications.commands`, no permissions
   required, and use the generated URL to invite it to your server.
5. In Discord, turn on Developer Mode (User Settings → Advanced), then right-click your server
   → *Copy Server ID* for `DISCORD_GUILD_ID`, and right-click each role → *Copy Role ID*.

Commands register per-guild, so they appear the moment you publish them. No waiting an hour for
global propagation.

Registering is a deliberate step in both bots (`npm run register` / `python scripts/register.py`),
not something that happens on every boot. That way a crash-looping bot never hammers Discord's
command endpoint, and you get a `--clear` to pull commands back off a server.

## Getting an API key

You need a dmarebrands partner account. In the partner panel go to
[API](https://partners.dmarebrands.st/partners/api), create a key, and copy it into
`DMAREBRANDS_API_KEY`. It is shown once and never again.

Not a partner yet? Ask in the [dmarebrands](https://dmarebrands.st) store.

An API key is your whole partner account and **it can spend your balance**. Treat the `.env`
like a password file. If it leaks, revoke it in the panel — that takes effect on the next
request.

## Security notes

- The bot only responds inside `DISCORD_GUILD_ID`. Dragging it into another server does nothing.
- Replies are ephemeral by default, so key codes are visible only to the person who ran the
  command. Set `EPHEMERAL=false` if you would rather everyone in the channel see them.
- Set `LOG_CHANNEL_ID` to have every purchase, refund and reset posted to a channel. Useful
  when several staff share one partner account.
- Confirmation buttons only accept a press from the person who ran the command.

## Licence

MIT. See [LICENSE](LICENSE).
