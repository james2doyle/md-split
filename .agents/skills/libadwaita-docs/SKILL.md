---
name: libadwaita-docs
description: Use when answering questions about building GNOME applications with Libadwaita, GTK 4 widgets, adaptive layouts, or searching Libadwaita API documentation.
---

# Libadwaita Documentation Skill

Use this skill when answering questions about building modern GNOME applications with Libadwaita, including widget usage, GTK 4 integration, adaptive design patterns, and C/GObject API specifications.

## Version Scope

MD Split supports libadwaita 1.9+; the Flatpak runtime currently provides 1.10.
The `1-latest` documentation can describe newer APIs, so check the `since:`
annotation before using one. APIs newer than 1.9 need a runtime version guard or
a fallback. Check `deprecated:` annotations and prefer the replacement API.

## Direct URL Access & Documentation Search

You can access Libadwaita documentation pages directly by construct URLs based on entity type and name, or via search queries:

- **Direct Entity URLs (`<type>.<Name>.html`):**
  - **Enums:** `https://gnome.pages.gitlab.gnome.org/libadwaita/doc/1-latest/enum.<Name>.html`
    *Example:* [Adw.ToolbarStyle](https://gnome.pages.gitlab.gnome.org/libadwaita/doc/1-latest/enum.ToolbarStyle.html)
  - **Classes:** `https://gnome.pages.gitlab.gnome.org/libadwaita/doc/1-latest/class.<Name>.html`
    *Example:* `https://gnome.pages.gitlab.gnome.org/libadwaita/doc/1-latest/class.ToolbarView.html`
  - **Structs / Interfaces:** `https://gnome.pages.gitlab.gnome.org/libadwaita/doc/1-latest/struct.<Name>.html` or `iface.<Name>.html`

- **Search Query Format:**
  - **URL Structure:** `https://gnome.pages.gitlab.gnome.org/libadwaita/doc/1-latest/index.html?q=<term>`
    *Example:* `https://gnome.pages.gitlab.gnome.org/libadwaita/doc/1-latest/index.html?q=ToolbarStyle`

You can find the docs and details for the stylesheet at https://github.com/GNOME/libadwaita/tree/1.10.0/src/stylesheet

## Key Reference Sections

- **Initialization & Setup:**
  - [Compiling with Libadwaita](https://gnome.pages.gitlab.gnome.org/libadwaita/doc/1-latest/compiling-libadwaita.html)
  - [Initialization](https://gnome.pages.gitlab.gnome.org/libadwaita/doc/1-latest/initialization.html)
- **UI & Layout Patterns:**
  - [Adaptive Layouts](https://gnome.pages.gitlab.gnome.org/libadwaita/doc/1-latest/adaptive-layouts.html)
  - [Boxed Lists](https://gnome.pages.gitlab.gnome.org/libadwaita/doc/1-latest/boxed-lists.html)
  - [Widget Gallery](https://gnome.pages.gitlab.gnome.org/libadwaita/doc/1-latest/widget-gallery.html)
- **Styling & Appearance:**
  - [Styles & Appearance](https://gnome.pages.gitlab.gnome.org/libadwaita/doc/1-latest/style-classes.html)
  - [CSS Variables](https://gnome.pages.gitlab.gnome.org/libadwaita/doc/1-latest/css-variables.html)
  - [Style Classes](https://gnome.pages.gitlab.gnome.org/libadwaita/doc/1-latest/style-classes.html)

## Migration Guides

- [Migrating to Breakpoints](https://gnome.pages.gitlab.gnome.org/libadwaita/doc/1-latest/migrating-to-breakpoints.html)
- [Migrating to Adaptive Dialogs](https://gnome.pages.gitlab.gnome.org/libadwaita/doc/1-latest/migrating-to-adaptive-dialogs.html)
- [Migrating from Libhandy 1.4](https://gnome.pages.gitlab.gnome.org/libadwaita/doc/1-latest/migrating-libhandy-1-4-to-libadwaita.html)

Prefer the current stable API over deprecated widgets. In particular:

- `AdwMessageDialog` (deprecated 1.6) → `AdwAlertDialog`
- `AdwLeaflet` / `AdwFlap` → `AdwOverlaySplitView` / `AdwNavigationSplitView` with `AdwBreakpoint`
- `GtkComboBoxText` (deprecated 4.10) → `GtkDropDown`
- `GtkDialog` / `GtkMessageDialog` (deprecated 4.10) → `AdwAlertDialog`, `AdwDialog`, or a window-specific dialog

## Common Query Workflows

### 1. Finding Widgets & Components
1. Construct the direct class URL using `class.<Name>.html` or `enum.<Name>.html`, or use the search parameter `?q=<query>`.
2. Key classes include:
   - `AdwApplicationWindow` / `AdwWindow`: Window containers with Adwaita styling built-in.
   - `AdwHeaderBar`: Adaptive title bar component.
   - `AdwToolbarView` / `AdwToolbarStyle`: Header/footer toolbar container and style enums (`ADW_TOOLBAR_FLAT`, `ADW_TOOLBAR_RAISED`, `ADW_TOOLBAR_RAISED_BORDER`).
   - `AdwActionRow` / `AdwPreferencesRow` / `AdwPreferencesGroup`: Standard list row structures.
   - `AdwBreakpoint`: Utility for dynamic responsive layouts.
   - `AdwOverlaySplitView` / `AdwNavigationSplitView`: Sidebar + content split layouts (`sidebar:`/`content:`, `show-sidebar`, `collapsed`).
   - `AdwDialog` / `AdwPreferencesDialog`: Adaptive modal dialogs.

### 2. Adaptive Layout Implementation
- Check `AdwBreakpoint` for window size triggers.
- Refer to [Migrating to Breakpoints](https://gnome.pages.gitlab.gnome.org/libadwaita/doc/1-latest/migrating-to-breakpoints.html) when updating legacy `AdwLeaflet` or `AdwFlap` implementations.

### 3. Styling & Customization
- Prefer built-in Adwaita CSS variables (`--window-bg-color`, `--accent-bg-color`, etc.) over hardcoded colors.
- Use established style classes (`.suggested-action`, `.destructive-action`, `.title-1`) defined in the [Style Classes](https://gnome.pages.gitlab.gnome.org/libadwaita/doc/1-latest/style-classes.html) reference.

## Response Guidelines
- **Language Scope:** Provide C, Python, or Vala code snippets depending on user preference, defaulting to C/GObject or GTK Blueprint/UI XML files when illustrating layout structures.
- **Dependency Assumptions:** Always target GTK 4 (`pkg-config files: libadwaita-1`, headers `#include <adwaita.h>`).

## Gotchas

- **Initialization:** C/GObject programs using Libadwaita must call `adw_init()` or subclass `AdwApplication` instead of pure `GtkApplication`.
- **GTK 4 Requirement:** Libadwaita 1.x is strictly compatible with GTK 4; do not use GTK 3 widgets or APIs.