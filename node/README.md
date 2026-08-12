# dmarebrands Discord bot — Node.js

discord.js v14 on Node 20 or newer. See the [main README](../README.md) for the command list
and the permission model.

## Install

```bash
cd node
npm install
cp .env.example .env
```

Fill in `.env`, then:

```bash
npm run doctor     # checks your token, API key, roles and registration
npm run register   # publishes the slash commands to your guild
npm start          # runs the bot
```

`npm run doctor` is the fastest way to find a setup mistake. It verifies the Discord token
against the application ID, calls the partner API with your key, and warns about any command
that no configured role can reach.

## Scripts

| | |
|---|---|
| `npm start` | Run the bot |
| `npm run register` | Publish slash commands to `DISCORD_GUILD_ID` |
| `npm run unregister` | Remove every command from the guild |
| `npm run doctor` | Check the whole setup and report problems |
| `npm run typecheck` | Resolve every module and check syntax |

Re-run `npm run register` whenever you change or add a command. Restarting alone will not
update what Discord shows.

## Running it for real

Keep it alive with pm2, systemd or Docker. With pm2:

```bash
npm install -g pm2
pm2 start src/index.js --name dmarebrands-discord-bot
pm2 save
```

## Layout

```
src/
  index.js          gateway client, routing, error handling
  config.js         .env parsing and validation, role to scope mapping
  api.js            partner API client, retries, rate limits
  permissions.js    scope resolution from a member's roles
  format.js         embeds, money, timestamps
  confirm.js        confirmation buttons for anything that costs money
  commands/         one module per command group
scripts/
  register.js       publish or clear slash commands
  doctor.js         setup checks
```

## Adding a command

Add a module in `src/commands/` exporting `{ data, scopes, run }`, list it in
`src/commands/index.js`, and run `npm run register`.

`scopes` is either a single scope string for the whole command, or an object keyed by
subcommand name when different subcommands need different permissions — that is how
`/keys list` needs only `keys.read` while `/keys buy` needs `keys.buy`.
