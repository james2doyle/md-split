# Vendored Markdown parser

MD Split uses [markdown-it-py](https://github.com/executablebooks/markdown-it-py)
plus the composite GFM plugin from
[mdit-py-plugins](https://github.com/executablebooks/mdit-py-plugins). They are
pure Python and are vendored here so the installed application has no runtime
Python package dependencies beyond PyGObject.

Versions copied from their upstream releases on 2026-11-16:

| Package | Version | Files |
| --- | --- | --- |
| markdown-it-py | 4.3.0 | complete `markdown_it/` package |
| mdit-py-plugins | 0.7.0 | `__init__.py`, `utils.py`, and the `gfm`, `gfm_autolink`, `footnote`, `dollarmath` and `front_matter` plugins |
| mdurl | 0.1.2 | complete `mdurl/` package |

The subset of `mdit_py_plugins` is intentional: the composite GFM plugin
imports only those subpackages, and unused plugins are omitted.

`markdown-it-py` 4.3.0 contains the upstream fixes for quadratic inline
parsing. The 0.7.0 GFM autolink plugin still has two independent quadratic
paths, for which no upstream release exists yet. The local linearization is
tracked explicitly and must be applied after copying 0.7.0:

```sh
cd src/vendor
patch -p1 < patches/mdit-py-plugins-0.7.0-gfm-autolink-linear.patch
```

The patch only changes `gfm_autolink/index.py` and `_match.py`; it preserves
autolink output while removing repeated full-suffix searches and copies.

These packages are MIT licensed. License texts are in `LICENSES/`:

- `markdown-it-py.LICENSE` — markdown-it-py
- `markdown-it.LICENSE` — the upstream markdown-it implementation
- `mdit-py-plugins.LICENSE` — mdit-py-plugins
- `mdurl.LICENSE` — mdurl

Do not patch vendored code. To update, replace the packages from a matching
release and re-run `meson test -C build`. `src/renderer.py` adds this directory
to `sys.path` before importing `markdown_it`.
