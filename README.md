# Lowlands League Liquipedia publisher

Cloud publisher for Lowlands League Season 2. Google Apps Script generates the
wikicode and starts a GitHub Actions workflow. The workflow publishes through
Liquipedia's bot API with a descriptive user agent and a 15-second request
interval.

## Initial safety scope

The workflow initially accepts exactly one page:

```text
User:DialloBOT/test
```

Production tournament pages must only be added after the test page succeeds.

## Repository secrets

In **Settings → Secrets and variables → Actions**, create these repository
secrets:

| Secret | Value |
| --- | --- |
| `LIQUIPEDIA_BOT_USERNAME` | Bot-password login, for example `DialloBOT@DialloBOT` |
| `LIQUIPEDIA_BOT_PASSWORD` | Generated bot password only |
| `LIQUIPEDIA_CONTACT` | Contact email address or Liquipedia profile URL |

Never commit these values to the repository.

## Google Apps Script properties

Create these Script Properties in the Admin spreadsheet project:

| Property | Value |
| --- | --- |
| `GITHUB_REPOSITORY` | `Versebelt/lowlands-liquipedia-bot` |
| `GITHUB_WORKFLOW_FILE` | `publish-liquipedia.yml` |
| `GITHUB_WORKFLOW_REF` | `main` |
| `GITHUB_ACTIONS_TOKEN` | Fine-grained GitHub token with Actions: write access to this repository |

The GitHub token belongs in Apps Script properties, never in spreadsheet cells
or source code.

## First test

1. Add the repository files and secrets.
2. Update the Admin spreadsheet's `Code.gs`.
3. Reload the spreadsheet.
4. Choose **Lowlands League → Queue overview test via GitHub**.
5. Open the repository's **Actions** tab and inspect the run.
6. Verify the result at `https://liquipedia.net/geoguessr/User:DialloBOT/test`.

The workflow does not retry HTTP 429 responses and does not publish unchanged
content. Every run uploads a short-lived result artifact. Apps Script correlates
that artifact with its `Liquipedia Log` sheet and records the final result,
revision id, failed step, or error message.

## Discord seed reminders

`.github/workflows/discord-reminders.yml` posts scheduled seed reminders to a
single Discord channel through a webhook:

- Monday 09:00 Europe/Amsterdam: the new week is open.
- Friday 20:00: reminder mentioning the generic league role.
- Sunday 10:00: final reminder mentioning every configured player role.

Configure these GitHub Actions repository secrets:

- `DISCORD_WEBHOOK_URL`: incoming webhook for the announcements channel.
- `DISCORD_GENERIC_ROLE_ID`: numeric ID of the general reminder role.
- `DISCORD_PLAYER_ROLE_IDS`: comma-separated numeric player-role IDs.

Discord's `allowed_mentions` is restricted to the exact configured role IDs;
arbitrary mentions and `@everyone` are never enabled. A manual workflow run is
a dry run by default and prints the message without sending it.
