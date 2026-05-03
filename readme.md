# Warband-trade-assessment-injector

A simple warband trade assessment menus injector that augment it to generate an additional report for items sold across the markets of the world. Chinese support is built in the script.

Input for test:

- Warband Native 1.174
- Home-modified version of Prophecy of Pendor

Quick start (injector):

1) Prepare a compiled menus.txt (and matching quick_strings.txt in the same folder).
2) Use Python 3.
3) Run the injector:

Note: all arguments are optional, the script has default values for the four items, which are jousting lance, plate armor, charger and velvet.

```
python script/inject_rare_item_scout.py <absolute_path_to_menus.txt> --item1 <id> --item2 <id> --item3 <id> --item4 <id>
```

Additional examples:

```
python script/inject_rare_item_scout.py <absolute_path_to_menus.txt> --item1 469 --item2 272 --item3 150 --item4 101 --dry-run
python script/inject_rare_item_scout.py <absolute_path_to_menus.txt> --restore
python script/inject_rare_item_scout.py <absolute_path_to_menus.txt> --lang zh-CN --with-diag
```

Inputs and outputs:

- Inputs: compiled menus.txt and (optionally four item ids). The injector also updates quick_strings.txt alongside menus.txt.
- Outputs: modified menus.txt and quick_strings.txt with an injection signature for idempotency.
- Backups: created before write; use --restore to revert.

Safety checklist:

- Run with --dry-run before a live injection.
- Confirm backups exist before overwriting menus.txt.
- Validate menus.txt and quick_strings.txt after the write.

Diagnostics:

- Use --with-diag for detailed logs.
- Use --dry-run to validate block balance and injection placement.

Troubleshooting:

- Injector issues: run with --dry-run and --with-diag, then consult the script itself.
- There're Chinese in the script, just use AI to swap them or troubleshoot for you.

Author: VOX CORDIS
