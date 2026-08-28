# Changelog

All notable changes to telegram-multi-device-monitor will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.3] - 2026-08-28: Release notes match the tags they are published under

Every section in this file was read against the tag it describes and corrected
where the code said something else. The corrections are listed below, each with
the file that settles it. No measured value, path or identifier was changed for
style; where a number moved, the tree it was counted against is named.

### Changed

- **Release titles and bodies now come from this file.** A new
  `.github/workflows/release.yml` cuts the section for the pushed tag out of
  `CHANGELOG.md`, reads the headline behind the date in the section heading, and
  publishes both as the GitHub release. Section headings therefore carry a
  headline from now on (`## [X.Y.Z] - YYYY-MM-DD: <headline>`). Until this
  release the titles were typed by hand at `gh release create` and existed only
  on GitHub, with no source in the repository.
- **Every entry now opens with what changes for the operator**, with the cause
  in the sentence that follows. The `[1.0.0]` section was a feature inventory
  without that split, so it reads differently than before; its content is the
  same except where a correction below says otherwise.
- **The interactive bot is described by the eight commands it answers.**
  `docs/API_REFERENCE.md` documents `/status`, `/services`, `/docker`,
  `/metrics`, `/logs`, `/restart`, `/start` and `/help`. The `[1.0.0]` section
  said "15+", which is the number of `CommandHandler` registrations in
  `interactive_bot.py`: seven of them are single-letter aliases onto the same
  handlers.
- **The `set -uo pipefail` claim now names the scripts it holds for.**
  `install.sh`, `src/simple_sender.sh` and `src/token_fetcher.sh` set it; the
  three sourced libraries under `src/lib/` deliberately do not, because a
  sourced file would impose it on its caller.
- **The type-hint claim now says what `1.0.0` shipped.** It claimed complete
  type coverage, and `mypy --strict src/*.py` reported 89 errors against that
  tree, four of them functions without a complete annotation. The gap was closed in
  `1.0.1`.
- **SSH connection pooling is no longer listed among the delivered
  capabilities.** `SSHConnectionPool` in `alert_bot.py` is constructed in
  `AlertBot.__init__` and its `get_connection()` is never called; `alert_bot.py`
  opens no SSH connection at all. `metrics_collector.py`, the component that
  does use SSH, runs `ssh` per call and does not touch the pool. The class stays
  in the tree; what changed is the claim about it.
- **The psutil entry counts the messages it names.** Installing `types-psutil`
  removes three `Library stubs not installed for "psutil"` errors, and with them
  two follow-on `no-any-return` errors: 89 errors before, 84 after. The `[1.0.1]`
  section called all five of them stub errors.
- **Config file permissions are described as the installation step they are.**
  `install.sh` sets `750` on `/etc/telegram-monitor`; the `600` on the YAML files
  is the step `docs/SETUP.md` and `config/README.md` ask the operator to run.
- **The production figures name the deployment they were measured on.** The
  25 MB footprint, the sub-second command latency and the 99.9 percent delivery
  rate come from the private deployment this project was extracted from, not
  from a benchmark that ships here. They stay because they are what the design
  was built against, and they now say so.
- **The `[1.0.0]` section carries the date of its tag.** It read `2026-02-04`,
  the day the code was finished; `v1.0.0` was tagged and published on
  `2026-02-18`.
- **Em dashes are gone from this file.** Two stood in the `[1.0.1]` section;
  a colon or the word behind them now does their work.

## [1.0.2] - 2026-08-12: Executable install and sender scripts

### Fixed

- **A fresh clone can run `./install.sh` and `./src/simple_sender.sh` as
  documented.** Both were tracked with mode `644`, so `README.md` and
  `docs/TROUBLESHOOTING.md` described a call that failed and `bash install.sh`
  was required instead. No script content changed. `src/token_fetcher.sh` stays
  `644` on purpose: it is only ever run from an installed tree, where
  `copy_files()` in `install.sh` sets the execute bit.

## [1.0.1] - 2026-08-09: Type-clean codebase and a lint pipeline that actually runs

The lint workflow had never produced a visible run. Before this release
`actions/runs` and `actions/workflows` both reported `total_count: 0`, neither
commit had a check run, and the badge URL answered with 404. Whether the
workflow was never registered or the runs had aged out could not be decided from
outside; pushing this tag settled it either way. Reproduced locally in a clean
virtualenv holding `black mypy types-PyYAML types-requests` plus
`requirements.txt`, which is what the workflow installs.

### Fixed

- **`mypy --strict src/*.py` no longer fails the pipeline.** It reported 89
  errors across 5 files. 67 of them had a single cause: `telegram.Update` types
  `message`, `effective_user` and `callback_query` as optional, because one
  Update object covers every kind of event. The remainder were six
  unparameterised generics, three functions missing a return annotation and one
  missing any annotation, two argument-type and two assignment mismatches, and a
  mistyped log handler list.
- **`shellcheck -S warning` no longer fails on `install.sh`.** It reported
  SC2034 for an unused `SCRIPT_NAME` constant, and a single warning is enough to
  fail the job.
- **The workflow installs `types-psutil`.** Three `Library stubs not installed
  for "psutil"` errors in `alert_bot.py`, `interactive_bot.py` and
  `metrics_collector.py` had no source-side fix, and two `no-any-return` errors
  followed from them: 89 errors before, 84 after.
- **The lint fixes from the previous commit are now in a release.** That commit,
  titled `fix: resolve lint failures in CI pipeline`, corrected YAML and Black
  formatting only and had never been published under a tag.

### Changed

- **An update without the field a handler expects now fails by name.**
  `require_message`, `require_user`, `require_query` and `require_updater` in
  both bot modules replace direct attribute access on optional Update fields.
  This is a behaviour change, not only a typing one: such an update previously
  died with an `AttributeError` somewhere inside a handler and now raises a
  named `RuntimeError`. No handler catches more or less than before.
- **The version is read from one file instead of being edited in eight
  places.** `VERSION` at the repository root is the single source;
  `readonly VERSION="1.0.0"` in `install.sh` and a `Version: 1.0.0` header line
  in seven files under `src/` (five Python docstrings, two Bash comments) are
  gone. None of them were part of any release procedure, so all seven header
  lines would have kept claiming 1.0.0. `install.sh` reads the file through
  `resolve_version()`, which handles both the repository layout and an installed
  tree and falls back to `unknown` instead of aborting when the file is missing
  or malformed. It also copies `VERSION` into the install directory, so a
  deployed tree can state its own version.
- **`.gitignore` covers `CLAUDE.md` and `.claude/`.**

## [1.0.0] - 2026-02-18: Multi-device Telegram monitoring that fits on a Pi Zero

First public release, extracted from a private homelab deployment running on a
Raspberry Pi 5 gateway, a NAS and a fleet of Pi Zeros. The figures quoted below
come from that deployment; no benchmark ships with this repository.

### Added

**Components:**

- **Full monitoring from a phone.** `interactive_bot.py` answers eight commands
  (`/status`, `/services`, `/docker`, `/metrics`, `/logs`, `/restart`, `/start`,
  `/help`), seven of them with a single-letter alias, and restricts `/restart`
  to the admin ids in `telegram_config.yml`.
- **A variant small enough for a device with 512 MB of RAM.**
  `alert_bot.py` drops the interactive surface and keeps alert processing,
  measured at roughly 25 MB in the original deployment.
- **Alertmanager can post straight into a chat.** `prometheus_webhook.py`
  accepts `POST /webhook` and `/api/v2/alerts`, deduplicates by fingerprint and
  renders through templates.
- **Any shell script can send a message without Python.** `simple_sender.sh`
  takes a message, a file or stdin and reads its configuration from YAML or the
  environment.
- **Tokens can come from a secret manager instead of a config file.**
  `token_fetcher.sh` writes them to a runtime environment file with mode `600`
  and is meant to run as `ExecStartPre=`.
- **Formatted status messages without a running bot.** `alert_sender.py`
  composes system status into a single message.
- **Remote hosts are monitored without an agent.** `metrics_collector.py`
  collects CPU, memory, disk, temperature, uptime and service state over SSH.

**Configuration:**

- **Every setting can be overridden from the environment.** `config_loader.py`
  validates and deep-merges YAML against defaults, so a container and a bare
  metal host can share one file.
- **Four templates cover the deployment.** `telegram_config.yml.example`,
  `service_monitoring.yml.example`, `ssh_targets.yml.example` and
  `network_config.yml.example`, with timeouts, memory limits and alert
  thresholds among the keys.

**systemd:**

- **Four hardened unit templates.** Each sets `ProtectSystem=strict`,
  `NoNewPrivileges` and `PrivateTmp`, and each carries a `MemoryMax` sized for
  its component: 50M for the alert bot and the metrics collector, 75M for the
  webhook, 100M for the interactive bot.
- **Alert state survives a restart.** The webhook unit declares
  `StateDirectory=telegram-monitor` with mode `0750`, which is where the
  deduplication state is kept.

**Bash libraries:**

- **Structured logging with selectable targets.** `src/lib/logging.sh`.
- **Alert deduplication and rate limiting.** `src/lib/alerts.sh`, which also
  sanitises the alert id before it reaches `sed` and `grep`.
- **Atomic writes and safe path handling.** `src/lib/file_utils.sh`.

**Installation:**

- **One script sets up dependencies, configuration and units.** `install.sh`
  checks prerequisites, copies `src/`, `VERSION` and the config templates,
  creates `/etc/telegram-monitor` with mode `750`, and offers `--check` and
  `--uninstall`.

**Documentation:**

- **Setup, architecture, API reference and troubleshooting** under `docs/`,
  plus `CONTRIBUTING.md` and `SECURITY.md`.

**CI:**

- **Three lint jobs on pushes to `main` and `develop` and on pull requests
  against them.** `black` and `mypy --strict` over a 3.10/3.11/3.12 matrix,
  `shellcheck -S warning` over every `*.sh` outside the dot directories, and
  `yamllint` over `config/` and `.github/`.

### Security

- **Privileged commands are limited to named Telegram user IDs**, and service
  restarts additionally to a configured `allowed_restart` list, so a compromised
  chat cannot restart anything the operator did not list.
- **SSH uses key authentication and `StrictHostKeyChecking=accept-new`**, which
  pins a host on first contact instead of accepting any key on every contact.
- **Credential status is logged without the credential.**
- **Service names reaching `systemctl` are quoted** with `shlex.quote()` in
  `metrics_collector.py`, and alert ids reaching `sed` and `grep` are sanitised
  in `src/lib/alerts.sh`.
- **No credential is stored in the repository**, and the unit templates warn
  against putting a token into them.

### Performance

- **Alerts are deduplicated before they are sent**, so a flapping service
  produces one message instead of a stream.
- **Collection runs concurrently.** The bots use asyncio, and partial results
  are returned when a single source fails instead of dropping the whole report.
- **Measured in the original deployment:** roughly 25 MB resident for the alert
  bot, command responses under a second, and 99.9 percent of more than 10,000
  alerts delivered. These figures describe that deployment, not a benchmark in
  this repository.

### Quality

- **Type hints throughout the Python sources.** They were not yet complete:
  `mypy --strict` reported 89 errors against this tree, four of them functions
  without a complete annotation. `1.0.1` closed that.
- **`set -uo pipefail` in the three scripts that are run rather than sourced:**
  `install.sh`, `src/simple_sender.sh` and `src/token_fetcher.sh`. The three
  libraries under `src/lib/` omit it so they do not impose it on their caller.
- **Retry logic with exponential backoff** around the SSH calls in
  `metrics_collector.py`, driven by `RETRY_BASE_DELAY`.
- **No real address, device name or private path in the tree.** The examples
  use private ranges (`192.168.1.0/24`, `10.0.0.0/24`) with generic host names,
  not the addresses of the deployment this was extracted from.

### Compatibility

- **Python 3.10 or newer and Bash 5.0 or newer.**
- **Tested on Ubuntu 20.04 and newer, Debian 11 and newer, and Raspberry Pi
  OS**, on devices with at least 512 MB of RAM.

## Version History

[1.0.3]: https://github.com/fidpa/telegram-multi-device-monitor/releases/tag/v1.0.3
[1.0.2]: https://github.com/fidpa/telegram-multi-device-monitor/releases/tag/v1.0.2
[1.0.1]: https://github.com/fidpa/telegram-multi-device-monitor/releases/tag/v1.0.1
[1.0.0]: https://github.com/fidpa/telegram-multi-device-monitor/releases/tag/v1.0.0
