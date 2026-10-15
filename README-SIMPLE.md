# storager — the simple version

## What is it?

storager is a free tool that helps you **clean up your computer's disk space**.

It looks at your files, figures out what is taking up the most room, and tells you **in plain words** what each thing is — so you can decide what to throw away.

---

## Why do I need it?

Your disk fills up over time. You forget about old downloads, apps leave behind caches you never see, and suddenly your computer says "disk almost full."

storager finds all of that stuff and explains it to you, so you can get your space back **without guessing**.

---

## How do I install it?

You need Python installed (most computers have it). Then open a terminal and type:

```bash
pip install git+https://github.com/Aghosh-mv/storager-agent.git
```

That's it. One command.

---

## How do I use it?

Type:

```bash
storager
```

storager will:

1. **Ask you** how much space you want to free (for example "5G" for 5 gigabytes)
2. **Look at your files** and figure out what is big
3. **Explain each thing** in normal words — for example:
   - *"App cache — safe to clear. Caches are regenerated automatically by apps."*
   - *"node_modules — reinstall with npm install. JS dependencies for your project."*
   - *"Downloaded files — you may not need them anymore."*
4. **Tell you what is inside each folder** — for example: *"847 images, 12 videos, last touched 2 years ago"*
5. **Warn you about connections** — for example: *"deleting this folder affects your project at /Users/you/myproject"*
6. **Ask you to confirm before deleting anything** — it never deletes without your permission
7. **Move things to your Trash** (not permanently delete) — so you can get them back if you change your mind

---

## What if I make a mistake?

Nothing is permanently deleted by default. Everything goes to your **Trash**. Just open the Trash and put it back.

---

## Is it safe?

- It **never deletes without asking you first**
- It **never sends your data anywhere** — no internet, no cloud
- It does **not use AI** — it follows a set of clear rules you can read yourself
- It is **open source** — anyone can look at the code

---

## What can I type?

| What you type | What happens |
|---|---|
| `storager` | Clean your current folder |
| `storager ~` | Clean your home folder (everything) |
| `storager scan ~` | Just look — no deleting |
| `storager clean ~ --dry-run` | Preview what would be deleted — delete nothing |
| `storager undo` | Bring back what you just deleted |
| `storager auto ~ --threshold 85` | Clean automatically when disk gets too full |
| `storager doctor ~` | Full health check — score, problems, top space hogs |
| `storager profile developer` | Tell storager you're a developer (smarter detection) |
| `storager export ~ --out report.json` | Save a report of what was found |
| `storager rules` | See your saved rules |

---

## Quick example

```bash
$ storager ~

storager v0.2.0

How much disk space do you want to free?
  > 5G

Scanning your files...

storager noticed:
  ! disk is 87% full — worth cleaning soon

Biggest items:
  [1]   2.3 GB  App cache — safe to clear
       inside: 12,403 files, 312 folders · mostly .tmp (8,201) · last touched 3 months ago
       /Users/you/Library/Caches/some-app

  [2]   1.5 GB  Downloaded files (installers, zips, images…)
       also affects: came from the internet — usually re-downloadable
       /Users/you/Downloads/old-installer.dmg

Select items to delete.
  > 1

About to move to Trash 1 item(s), 2.3 GB:
  -   2.3 GB  /Users/you/Library/Caches/some-app

Type 'yes' to confirm: yes

Freed approximately 2.3 GB this session.
Target was 5.0 GB — 46% achieved.
```

---

## Need help?

Open an issue on GitHub: https://github.com/Aghosh-mv/storager-agent/issues
