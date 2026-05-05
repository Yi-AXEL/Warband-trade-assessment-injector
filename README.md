# Warband Trade Assessment Injector (Or Rare Item Scout)

This repo includes a Python 3 injector, `script/inject_rare_item_scout.py`, that patches compiled Warband files (`menus.txt` + `quick_strings.txt`) to extend the vanilla **Town Trade Assessment** report.

The injection adds a “rare item scout” section that can report where certain items are currently sold across the world, and (at higher Trade skill) the quality prefix of those items.

## What changes in-game

The injector augments the vanilla output (it does not replace it):

- **Trade skill < 3**: the assessment will show a short “not enough trade expertise” message.
- **Trade skill ≥ 3**: the assessment appends lines like `Velvet in Uxhal` for tracked items that exist in any town market.
- **Trade skill ≥ 6**: the report can also include the item’s quality prefix (e.g. `Masterwork`, `Cracked`) when applicable.
- A small hint message may also be injected into `menu_town_trade_assessment_begin`.

## Compatibility and assumptions

Tested inputs:

- Warband Native 1.174
- A home-modified Prophecy of Pendor 3.9.5 (whose trade assessment menu is similar to the Native's)

The injector assumes your compiled `menus.txt` contains these menu ids:

- `menu_town_trade_assessment`
- `menu_town_trade_assessment_begin`

If your mod renames or significantly rewrites these menus, the script will stop with errors like “can't find menu_town_trade_assessment”.

## Requirements

- Python 3 (no Module System / Python 2.7 compiler required)
- A compiled `menus.txt`
- The matching `quick_strings.txt` in the same folder as `menus.txt` (or provide a path via `--qstr-file`)

## Quick start

1) Locate your mod’s compiled files (usually in `Mount&Blade Warband/Modules/<YourMod>/`):
    - `menus.txt`
    - `quick_strings.txt`

2) Run a **dry run** first (no files are modified):

    ```bash
    python script/inject_rare_item_scout.py "C:/.../Modules/YourMod/menus.txt" --dry-run
    ```

3) Inject with defaults values (the four default values correspond to jousting lance, plate armor, charger and velvet in Native):

    ```bash
    python script/inject_rare_item_scout.py "C:/.../Modules/YourMod/menus.txt"
    ```

4) Launch the game and use **Assess local prices** to confirm the report contains the new section.

## CLI usage

Basic form:

```bash
python script/inject_rare_item_scout.py <path/to/menus.txt> [options]
```

Notes:

- `<path/to/menus.txt>` is required (even for `--restore`).
- Item arguments are optional.
- Item values are **item indices**, not the large encoded `OM_ITM|index` values you see in compiled numeric streams.

### Examples

Dry run with explicit item ids:

```bash
python script/inject_rare_item_scout.py <menus.txt> --item1 469 --item2 272 --item3 150 --item4 101 --dry-run
```

Inject Simplified Chinese strings and add in-game diagnostic markers:

```bash
python script/inject_rare_item_scout.py <menus.txt> --lang zh-CN --with-diag
```

Restore from backups:

```bash
python script/inject_rare_item_scout.py <menus.txt> --restore
```

### Option reference

- `--item1/--item2/--item3/--item4 <int>`: Tracked item indices.
  - Defaults: `469, 272, 150, 101` (commented in-script as Native 1.174 defaults; `101` is `itm_velvet`).
- `--lang {en,zh-CN}`: Language of injected quick strings and prefix table.
- `--with-diag`: Injects extra **in-game** `[RARE]` marker messages to help confirm which branch executed.
- `--dry-run`: Preview mode. Does not write any files; also enables extra console diagnostics and runs static checks.
- `--restore`: Restores `menus.txt` and `quick_strings.txt` from their `.bak` backups (if present).
- `--qstr-file <path>`: Override where `quick_strings.txt` is located.
- `--output <path>`: Write the modified `menus.txt` to a different path.
  - Note: `quick_strings.txt` is still updated in-place (at `--qstr-file` / alongside `<menus.txt>`).
- `--skl-trade <int>`: Manually specify the compiled `skl_trade` value if auto-extraction fails.
- `--no-verify`: Skip post-inject verification. Not recommended unless you know what you’re doing.
- `--force`:
  - Allows heuristic cleanup when an old injection has no signature.
  - Overwrites existing `.bak` backups.

## Files modified (and backups)

The injector updates:

- `menus.txt` (or the file specified by `--output`)
- `quick_strings.txt`

Before writing, it creates backups (unless they already exist):

- `menus.txt.bak`
- `quick_strings.txt.bak`

You can revert by running `--restore`.

If a `game_menus.csv` exists next to `menus.txt`, the injector may append comment lines describing the injected configuration (purely informational; does not affect the game).

## Idempotency and re-running

The injection includes a start/end signature inside `menu_town_trade_assessment`. On subsequent runs:

- If a signature is found, the script removes the old injected block and re-injects (safe to change item ids and re-run).
- If no signature is found but the tail of the menu looks like a previous injection, the script will only clean it when `--force` is provided.

## Diagnostics and troubleshooting

Recommended workflow:

1) Start with `--dry-run` to confirm the script can parse your `menus.txt`, locate the target menus, and pass static verification.
2) If the injected logic runs but output is unexpected, retry with `--with-diag` to add `[RARE]` in-game markers.

Common failure modes:

- **Missing `quick_strings.txt`**: place it next to `menus.txt` or pass `--qstr-file`.
- **Target menus not found**: your mod changed the vanilla menu ids; this injector won’t work without adapting the script.
- **Verification errors after write**: the script can auto-roll back using `.bak` backups.

## References and notes

- Deeper technical notes (design constraints, opcode pitfalls, idempotency markers): `Note/AI_note/rare_item_scout_notes.md`

## Credits

Author: Yi-AXEL

LLM used for this script: Deepseek V4 Flash and Pro

Post-hoc note:
LLMs (Deepseek V4, GPT 5.3, GPT 5.2 Codex and Claude Sonnet 4.6) I consulted do have some basic understanding of Mount and Blade module system, but they hallucinate in terms of specific opcodes.
For example, they do not know the compiled code for le, lt and neq. I have to establish a table of opcode>compiled code to reduce the hallucination. You should definitely establish a skill doc for them if you want to work with them to generate code for M&B.
