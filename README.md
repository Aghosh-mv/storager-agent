# storager

**Pure-algorithm disk space analyser.** No AI, no network, no telemetry.

`storager` walks your filesystem, measures what is eating your disk, names every big item in plain language, and lets you pick what to delete — once, or as a standing rule.

---

## Install

From a clone:

```bash
git clone https://github.com/<you>/storager.git
cd storager
pip install .
```

Or without installing (run straight from the repo):

```bash
python -m storager scan ~
```

After `pip install .` the `storager` command is available globally:

```bash
storager --version
```

---

## Commands

| Command | What it does |
|---|---|
| `storager scan [path]` | Lists the biggest items under `path`, each labelled in plain English. |
| `storager clean [path]` | Interactive session: pick what to delete, choose *this time* or *always*. |
| `storager rules` | List, add, or remove persistent "always delete / always ignore" rules. |
| `storager version` | Print version. |

### Scan

```bash
storager scan ~            # scan your home directory
storager scan ~ --top 50   # show more items
storager scan ~ --all      # include risky items in the listing
```

Every item is classified into a **category** and a **risk level**:

| Risk | Meaning |
|---|---|
| `safe` | Caches, logs, trash — regenerable or already discarded. |
| `probably-safe` | Downloads, build output, `node_modules` — usually reinstallable. |
| `risky` | Personal media, project code, VMs, databases — review before deleting. |
| `unknown` | storager could not identify it. |

### Clean

```bash
storager clean ~
```

1. Applies any saved *always delete* rules automatically (asks for confirmation).
2. Shows the remaining items, grouped by risk.
3. Lets you select with `1,3-5`, `all`, or `none`.
4. Asks **this time** or **always**.
5. Moves selections to the system Trash (macOS Finder Trash, Linux FreeDesktop Trash, Windows Recycle Bin). Use `--hard` to permanently delete.

### Rules

```bash
storager rules                              # list saved rules
storager rules --remove 0                   # delete rule at index 0
```

Rules live in `~/.config/storager/rules.json` and are matched by path glob + category on every future `clean` run.

---

## Safety

- **Trash by default.** Nothing is permanently deleted unless you pass `--hard`.
- **Confirmation before auto-deletes.** Saved rules still ask before acting.
- **No network.** storager never phones home.
- **No AI / no models.** Classification is a deterministic, ordered rule list — inspectable in `storager/classifier.py`.

---

## How the algorithm works

1. **Measure** — `scanner.py` uses `os.scandir` + recursive `stat` to sum directory sizes without following symlinks.
2. **Classify** — `classifier.py` runs an ordered list of `(category, risk, label, predicate)` rules against each entry. First match wins.
3. **Select** — `interactive.py` renders a colour-coded table and parses range selections (`1-4,7`).
4. **Persist** — `rules.py` stores standing decisions as JSON globs under `~/.config/storager/`.
5. **Delete** — `deleter.py` moves to the OS Trash (or hard-deletes on request), reporting freed bytes.

---

## License

MIT
