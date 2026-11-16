#!/usr/bin/env python3
"""Initialize this scaffold with a new application identity.

Run this from a copy of the template repository. It rewrites the application
ID, human-readable name, Python/gettext slug, author metadata, resource path,
GType prefix, and every filename derived from the application ID.
"""

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_APP_ID = "com.example.Hello"
DEFAULT_NAME = "Hello"
DEFAULT_SLUG = "hello"
DEFAULT_AUTHOR = "James Doyle"
DEFAULT_EMAIL = "james2doyle@gmail.com"
DEFAULT_URL = "https://example.com/hello"

SKIP_DIRS = {
    ".git",
    ".dex",
    "build",
    "build-install",
    ".flatpak-builder",
    ".venv",
    "__pycache__",
}
SKIP_FILES = {Path("scripts/init.py")}
TEMPLATE_START = "<!-- template:start -->"
TEMPLATE_END = "<!-- template:end -->"


def fail(message):
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def ask(label, default):
    value = input(f"{label} [{default}]: ").strip()
    return value or default


def slugify(name):
    value = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    if not value:
        fail("the application name must contain at least one letter or digit")
    if value[0].isdigit():
        value = "_" + value
    return value


def validate_app_id(app_id):
    # Reverse-DNS D-Bus name with at least three components, e.g. com.example.App.
    pattern = r"[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*){2,}"
    if not re.fullmatch(pattern, app_id):
        fail(
            "application ID must be a reverse-DNS D-Bus name with at least "
            "three components (for example com.example.MyApp)"
        )


def validate_slug(slug):
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", slug):
        fail("slug must be a lowercase Python identifier (letters, digits, underscore)")


def gtype_prefix(slug):
    return "".join(part.capitalize() for part in slug.split("_") if part)


def strip_template_readme():
    """Remove the template-only README block from the initialized project."""
    readme = ROOT / "README.md"
    text = readme.read_text(encoding="utf-8")
    start = text.find(TEMPLATE_START)
    end = text.find(TEMPLATE_END)
    if start == -1 or end == -1 or end < start:
        return
    text = text[:start] + text[end + len(TEMPLATE_END):]
    text = re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"
    readme.write_text(text, encoding="utf-8")


def replace_in_file(path, replacements):
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return
    updated = text
    for old, new in replacements:
        if isinstance(old, re.Pattern):
            updated = old.sub(new, updated)
        else:
            updated = updated.replace(old, new)
    if updated != text:
        path.write_text(updated, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(
        description="Rename the GTK Adwaita scaffold for a new application."
    )
    parser.add_argument("--app-id", help="reverse-DNS app ID, e.g. com.example.MyApp")
    parser.add_argument("--name", help="human-readable application name")
    parser.add_argument("--slug", help="lowercase Python/gettext slug (default: derived from --name)")
    parser.add_argument("--author", help="author name")
    parser.add_argument("--author-email", help="author email")
    parser.add_argument("--repo-url", help="project homepage or repository URL")
    parser.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    args = parser.parse_args()

    main_py = ROOT / "src" / "main.py"
    if DEFAULT_APP_ID not in main_py.read_text(encoding="utf-8"):
        fail("this tree is already initialized (could not find the template app ID)")

    app_id = args.app_id or ask("Application ID", DEFAULT_APP_ID)
    validate_app_id(app_id)

    name = args.name or ask("Application name", DEFAULT_NAME)
    slug = args.slug or slugify(name)
    validate_slug(slug)

    author = args.author or ask("Author name", DEFAULT_AUTHOR)
    email = args.author_email or ask("Author email", DEFAULT_EMAIL)
    repo_url = (args.repo_url or ask("Repository URL", DEFAULT_URL)).rstrip("/")

    gtype = gtype_prefix(slug)
    app_id_path = "/" + app_id.replace(".", "/")
    developer_id = app_id.rsplit(".", 1)[0]

    replacements = [
        (DEFAULT_URL, repo_url),
        (DEFAULT_APP_ID, app_id),
        ("/com/example/Hello", app_id_path),
        ('<developer id="com.example">', f'<developer id="{developer_id}">'),
        # GType identifiers: HelloApplication, HelloWindow, HelloFoo, ...
        (re.compile(r"\bHello(?=[A-Z])"), gtype),
        (DEFAULT_SLUG, slug),
        (DEFAULT_NAME, name),
        (DEFAULT_AUTHOR, author),
        (DEFAULT_EMAIL, email),
    ]

    renames = {
        Path("src/hello.in"): Path(f"src/{slug}.in"),
        Path("src/hello.gresource.xml"): Path(f"src/{slug}.gresource.xml"),
        Path("data/com.example.Hello.desktop.in"): Path(f"data/{app_id}.desktop.in"),
        Path("data/com.example.Hello.metainfo.xml.in"): Path(f"data/{app_id}.metainfo.xml.in"),
        Path("data/com.example.Hello.gschema.xml"): Path(f"data/{app_id}.gschema.xml"),
        Path("data/com.example.Hello.service.in"): Path(f"data/{app_id}.service.in"),
        Path("data/icons/hicolor/scalable/apps/com.example.Hello.svg"):
            Path(f"data/icons/hicolor/scalable/apps/{app_id}.svg"),
        Path("data/icons/hicolor/symbolic/apps/com.example.Hello-symbolic.svg"):
            Path(f"data/icons/hicolor/symbolic/apps/{app_id}-symbolic.svg"),
        Path("com.example.Hello.json"): Path(f"{app_id}.json"),
    }

    print(f"Initializing {name}")
    print(f"  application ID: {app_id}")
    print(f"  slug:           {slug}")
    print(f"  GType prefix:   {gtype}")
    print(f"  author:         {author} <{email}>")
    print(f"  repository:     {repo_url}")
    print("Renaming:")
    for old, new in renames.items():
        print(f"  {old} -> {new}")

    if not args.yes:
        answer = input("Proceed? [y/N]: ").strip().lower()
        if answer not in {"y", "yes"}:
            print("aborted")
            return 1

    for path in sorted(ROOT.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        if any(part in SKIP_DIRS for part in relative.parts):
            continue
        if relative in SKIP_FILES:
            continue
        replace_in_file(path, replacements)

    for old, new in renames.items():
        source = ROOT / old
        if not source.exists():
            fail(f"expected source file is missing: {old}")
        source.rename(ROOT / new)

    strip_template_readme()

    print(f"Done: {name} is ready. Run: meson setup build --prefix=\"$PWD/build-install\"")
    return 0


if __name__ == "__main__":
    sys.exit(main())
