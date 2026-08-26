# dmarebrands Discord bot for Python

discord.py v2 on Python 3.10 or newer. See the [main README](../README.md) for the command list
and the permission model.

## Install

```bash
cd python
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Fill in `.env`, then:

```bash
python scripts/doctor.py         # checks your token, API key, roles and registration
python scripts/register.py       # publishes the slash commands to your guild
python -m dmarebrandsbot         # runs the bot
```

`scripts/doctor.py` is the fastest way to find a setup mistake. It verifies the Discord token
against the application ID, calls the partner API with your key, and warns about any scope no
configured role grants.

## Scripts

| | |
|---|---|
| `python -m dmarebrandsbot` | Run the bot |
| `python scripts/register.py` | Publish slash commands to `DISCORD_GUILD_ID` |
| `python scripts/register.py --clear` | Remove every command from the guild |
| `python scripts/doctor.py` | Check the whole setup and report problems |

Re-run `register.py` whenever you change or add a command. Restarting the bot alone will not
update what Discord shows. That is deliberate, so a crash-looping bot never hammers Discord's
command endpoint. The bot logs a warning on start if nothing is registered.

## Running it for real

With systemd:

```ini
[Unit]
Description=dmarebrands Discord bot
After=network-online.target

[Service]
WorkingDirectory=/opt/dmarebrands-discord-bot/python
ExecStart=/opt/dmarebrands-discord-bot/python/.venv/bin/python -m dmarebrandsbot
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

## Layout

```
dmarebrandsbot/
  __main__.py       entrypoint, python -m dmarebrandsbot
  bot.py            client, command tree, error handling
  config.py         .env parsing and validation, role to scope mapping
  api.py            partner API client, retries, rate limits
  permissions.py    the requires() check decorator
  formatting.py     embeds, money, timestamps
  confirm.py        confirmation buttons for anything that costs money
  cogs/             one cog per command group
scripts/
  register.py       publish or clear slash commands
  doctor.py         setup checks
```

## Adding a command

Add a method to a cog in `dmarebrandsbot/cogs/`, decorate it with `@app_commands.command()` and
`@requires("some.scope")`, then run `python scripts/register.py` and restart. New cogs go in
the `COGS` tuple in `bot.py`.

Every command runs behind a command tree that already deferred the response, so reply with
`interaction.edit_original_response(...)` rather than `interaction.response.send_message(...)`.
The `@requires` decorator raises before your callback runs, so a command body never has to
think about permissions.
