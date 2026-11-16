---
name: gtk-guidelines
description: Write and edit GNOME Blueprint UI files (.blp) for GTK 4 and libadwaita apps. Use when creating, reviewing, or debugging Blueprint markup.
---

# GNOME Blueprint

Blueprint is a declarative markup language that compiles to GtkBuilder XML
(`blueprint-compiler`). Everything here is grounded in GTK 4 / libadwaita 1.10+.
A canonical set of runnable examples lives in the Workbench demos repo
(`src/<Demo Name>/main.blp`; directory names contain spaces). Mimic those
patterns.

## Additional documentation

- [GNOME Blueprint compiler](https://gitlab.gnome.org/GNOME/blueprint-compiler)
- [GNOME HIG Writing Style](https://developer.gnome.org/hig/guidelines/writing-style.html)
- [Adwaita's Style Classes](https://gnome.pages.gitlab.gnome.org/libadwaita/doc/1-latest/style-classes.html)
- [Adwaita icons set](https://gitlab.gnome.org/GNOME/adwaita-icon-theme/-/tree/master/Adwaita/symbolic/actions?ref_type=heads)
- [Adwaita's Named Colors](https://gnome.pages.gitlab.gnome.org/libadwaita/doc/1-latest/named-colors.html)
- [natorsc/py-gtk example app](https://github.com/natorsc/py-gtk)

You can find the GTK docs at this site: https://docs.gtk.org/gtk4/

You can search the docs with a query string like this: https://docs.gtk.org/gtk4/?q=%s


## File skeleton

```blp
using Gtk 4.0;
using Adw 1;

Adw.Window window {
  default-width: 800;
  default-height: 600;

  content: Adw.ToolbarView {
    [top]
    Adw.HeaderBar {}

    Adw.StatusPage {
      title: _("MD Split");
    };
  };
}
```

- Always start with `using Gtk 4.0;`; add `using Adw 1;` when using libadwaita
  (version is just `1`, never `1.x`). Other namespaces seen in practice:
  `using GtkSource 5;`, `using WebKit 6.0;`, `using Shumate 1.0;`, `using Pango 1.0;`.
- The first top-level object is the root widget. Auxiliary top-level objects go
  below it, unindented: `menu ... {}`, `Adw.Dialog {}`, `Adw.PreferencesDialog {}`,
  `Gtk.ShortcutsWindow {}`, `Popover {}`, `FileFilter {}`, `template $Name {}`,
  secondary `Adw.NavigationPage {}` / windows, shared objects (`ColorDialog {}`,
  `Shumate.Marker {}`).
- Only the `Gtk` namespace prefix may be omitted: `StringList` == `Gtk.StringList`.
  Unqualified names always resolve to `Gtk`, so other namespaces must be
  prefixed (`Adw.StatusPage`, not `StatusPage`).
- Blueprint properties are applied at construct time — configure widget
  appearance and state here rather than from code. Code wires behavior:
  signal handlers, dynamic state, and anything Blueprint can't express.
  The only properties worth setting in code are ones that change at runtime.

## Syntax essentials

```blp
Button button_next {
  label: _("Next");          // property: value; — one space after colon
  sensitive: false;          // booleans lowercase
  halign: center;            // enum members are bare snake_case, no namespace
  transition-type: slide_up; // also bare: content-fit: scale_down; wrap-mode: word;
  rgba: "#e01b24";           // colors are hex strings (ColorButton.rgba)
  accelerator: "<Control>Return"; // modifiers in angle brackets, then key
  action-target: "'content'";     // GVariant: string values need inner quotes

  layout {                   // Grid positioning (ints, not strings)
    row: 0;
    column: 1;
  }

  styles [                   // CSS classes — trailing comma is fine
    "pill",
    "suggested-action",
  ]

  accessibility {            // AT-SPI attributes
    labelled-by: title_label;
    described-by: hint_label;
  }
}
```

- Comments are `//` or `/* ... */` blocks. Use them sparingly, e.g. to link
  docs or to leave hints for translators.
- Translatable strings: `_("...")`. Context-qualified: `C_("Accuracy", "Exact")`.
  Mark every user-visible string; add hints with `/* Translators: ... */` on
  the line above.
- An object ID is written after the class: `Entry entry_url {}`. Reference it
  anywhere in the file by that ID (bindings, `group:`, `menu-model:`,
  `activatable-widget:`, `dialog:`, `stack:`, `view:`, `key-capture-widget:`,
  `extra-menu:`).
- Empty braces declare a placeholder that code fills in: `Label status_label {}`.

## Formatting rules

- 2-space indentation; one space after `:`; double-quoted strings.
- Keep child widget open-brace on the same line as the property:

  ```blp
  // OK
  child: Box { ... };
  // NOT OK
  child:
    Box { ... };
  ```

- Prefer `Box:spacing` over `margin-*` for layout; avoid hard-coded width/height
  except for fixed-geometry media; prefer Adwaita style classes and bundled
  Adwaita icons over custom ones.
- Object IDs: class name first, then purpose — `next_button` is wrong,
  `button_next` is right (`entry_url`, `toggle_orientation_horizontal`).
- Write user-visible strings using HIG terminology, not widget-class names:
  "Radio Group" and "Checkbox", not "CheckButton"; "Menu Button", not "MenuButton".

## Children and slots

- `Gtk.Box` and `Gtk.FlowBox` pack children directly in order — no `child:`
  keyword:

  ```blp
  Box {
    orientation: vertical;
    spacing: 12;
    Label { label: _("One"); }
    Button { label: _("Two"); }
  }
  ```

- Single-child containers (`Frame`, `Adw.Bin`, `Adw.BreakpointBin`, main child
  of `Overlay`) take exactly one direct child.
- Explicit `child:` is required when the container also sets other properties in
  some slots or you nest a property-assigned object: `child: Box { ... };` —
  note the trailing `;` after the closing brace on any object-valued property.
- Internal child slots use `[bracket]` markers:
  - `Adw.HeaderBar` / `ActionBar`: `[start]`, `[end]` (several `[start]` entries
    are allowed); `CenterBox`: `[start]`, `[center]`, `[end]`
  - `Adw.ToolbarView`: `[top]`, `[bottom]`, plus `content:`
  - `Adw.ActionRow`: `[prefix]`, `[suffix]`; `Adw.PreferencesGroup`: `[header-suffix]`
  - `Overlay`: main child is implicit, extras marked `[overlay]`
  - `Adw.Window` / `Gtk.Window`: `content:` / `titlebar:` respectively

## Bindings

```blp
Label label {
  label: bind entry.text;                                  // one-way
  wrap: bind wrap_row.selected as <bool>;                  // cast primitive
  direction: bind row.selected as <Gtk.ArrowType>;         // cast enum
  ellipsize: bind row.selected as <Pango.EllipsizeMode>;
  transition-duration: bind spin.value as <uint>;
}
Switch s {
  active: bind nav_view.animate-transitions bidirectional; // two-way
}
```

- Casts use `as <Type>` whenever the source type differs from the property type.
  Non-Gtk namespaces used in casts (e.g. `as <Pango.EllipsizeMode>`) need
  their own import: `using Pango 1.0;`.
- Simple bindings (object + property lookups) support flags: `bidirectional`,
  `inverted` (boolean inverse), `no-sync-create`. Flags don't apply to
  expression bindings (those with closures). `bind-property` is a lightweight
  alternative without expression overhead: `label: bind-property entry.text;`
- In list item factories, bind through the template:
  `label: bind template.item as <StringObject>.string;`
- `BuilderListItemFactory` full shape (`template ListItem` takes no trailing
  `;`):

  ```blp
  factory: BuilderListItemFactory {
    template ListItem {
      child: Label {
        label: bind template.item as <Gtk.StringObject>.string;
      };
    }
  };
  ```
- Self-references work: `label: bind linkbutton.uri;`
- Bound objects are referenced by ID and may be defined anywhere in the file,
  including below the root.

## Menus

Menus are top-level objects, referenced by `menu-model:` (MenuButton,
SplitButton, PopoverMenu) or `extra-menu:` (Label context menu):

```blp
menu demo_menu {
  item (_("New File"))                 // shorthand
  item {
    label: _("Open");
    action: "app.open_uri";            // action[:target] wiring
    target: "https://example.com";
  }
  section {
    label: _("Settings");
    submenu {
      label: _("Appearance");
      item { label: _("Dark"); action: "demo.theme"; target: "dark"; }
    }
  }
}
```

- Menu items without an action are inert until code connects `activate`.
- Radio-style action targets: three `ToggleButton`s sharing
  `action-name: "demo.scale"` with different `action-target: "'100%'"` etc.

## Dialog responses

`Adw.AlertDialog` / `Adw.MessageDialog` buttons come from the `responses`
extension block:

```blp
Adw.AlertDialog {
  heading: _("Delete File?");
  body: _("The file will be permanently lost.");

  responses [
    cancel: _("Cancel"),
    delete: _("Delete") destructive,
    save: _("Save") suggested,
  ]
}
```

- Response flags: `destructive`, `suggested`, `disabled`.
- Other extension blocks: `marks [...]` on `Gtk.Scale` (value, optional
  position, optional translatable label), `widgets [...]` on `Gtk.SizeGroup`,
  `offsets [...]` on `Gtk.LevelBar`, `items [...]` on `Gtk.ComboBoxText`
  (deprecated since GTK 4.10 — prefer `DropDown`).
- Type literals use `typeof<>`: `item-type: typeof<GObject.Object>;`. Flag
  values combine with `|`: `shortcuts: control_tab | control_shift_tab;`.

## Composite templates

```blp
template $AwesomeButton: Button {
  clicked => $onclicked();   // $ handler = method on the template class

  Image {
    halign: center;
    icon-name: "emoji-people-symbolic";
  }
}
```

- The `$` prefix registers the class name; code must register it, e.g. GJS:
  `GObject.registerClass({ GTypeName: "AwesomeButton", Template: workbench.template },
  class AwesomeButton extends Gtk.Button { onclicked() { ... } })`.
- Handlers declared as `signal => $method()` must exist on the class, not as
  globals.
- Signal flags: `after` connects after the default handler; `swapped` /
  `not-swapped` control argument order.

## Breakpoints

```blp
Adw.Window {
  Adw.Breakpoint {
    condition ("max-width: 550sp")   // sp units for scalable pixels

    setters {                        // dotted paths; null is allowed
      header_bar.title-widget: null;
      switcher_bar.reveal: true;
      split_view.collapsed: true;
    }
  }
}
```

- Setter dotted paths must reference IDs declared in the same file:
  `header_bar.title-widget: null;` needs `Adw.HeaderBar header_bar {}` somewhere
  in the file.

- `Adw.BreakpointBin` swaps its `child:` inside a layout when the condition
  matches (setters may point `breakpoint_bin.child: narrow_label;`).
- Pair `Adw.OverlaySplitView`/`Adw.NavigationSplitView` with a breakpoint that
  sets `collapsed: true` for narrow windows.

## Common scaffolds

Standard app window:

```blp
Adw.Window window {
  content: Adw.ToolbarView {
    [top]
    Adw.HeaderBar {
      [end]
      MenuButton button_menu {
        menu-model: menu_app;
        icon-name: "open-menu-symbolic";
        primary: true;
      }
    }
    content: Adw.StatusPage { title: _("My App"); };
  };
}
```

Boxed list (the ubiquitous settings list):

```blp
ListBox {
  selection-mode: none;
  styles [ "boxed-list" ]

  Adw.ActionRow {
    title: _("Row with a suffix");
    subtitle: _("Supporting text");
    activatable-widget: activatable_toggle;
    [suffix]
    ToggleButton activatable_toggle { valign: center; }
  }
  Adw.SwitchRow { title: _("Switch Row"); }
  Adw.SpinRow {
    title: _("Spin Row");
    adjustment: Adjustment { lower: 0; upper: 100; value: 50; step-increment: 1; };
  }
  Adw.ComboRow {
    title: _("Choose");
    enable-search: true;
    model: StringList { strings ["Cat", "Dog"] };
  }
  Adw.ExpanderRow {
    title: _("Expandable");
    show-enable-switch: true;
    Adw.ActionRow { title: _("Nested"); }
  }
}
```

Preferences dialog (auxiliary top-level; opened from code):

```blp
Adw.PreferencesDialog dialog {
  content-width: 800;
  content-height: 600;
  title: _("Preferences");

  Adw.PreferencesPage {
    title: _("Appearance");
    icon-name: "brush-monitor-symbolic";

    Adw.PreferencesGroup {
      title: _("Color Settings");
      [header-suffix]
      Button { icon-name: "settings-symbolic"; }

      Adw.SwitchRow { title: _("Use Dark Mode"); }
    }
  }
}
```

Other recurring shapes:

- Scrollable content: `Adw.Clamp { maximum-size: 480; Box { orientation: vertical; ... } }`
- Adaptive view switching: `Adw.ViewStack` + `Adw.ViewSwitcher` as
  `title-widget:` (policy: wide) + `Adw.ViewSwitcherBar` revealed via breakpoint;
  pages are `Adw.ViewStackPage` with `name`, `title`, `icon-name`,
  `badge-number`, `needs-attention`.
- Notifications: wrap the page in `Adw.ToastOverlay overlay {}` for toasts; put
  `Adw.Banner` as the first child of a vertical Box for banners.
- Inline key hints: `ShortcutsShortcut { accelerator: "<Control>Return"; }`
  works inside any layout, not just ShortcutsWindow.

## Widget cookbook

| Widget | Blueprint essentials |
| --- | --- |
| Entry | `placeholder-text`, `input-purpose: url/email/digits`, `input-hints: no_spellcheck`, primary/secondary icon props |
| PasswordEntry | `show-peek-icon: true`, `placeholder-text` |
| SearchEntry / SearchBar | `search-delay: 100`; SearchBar needs `key-capture-widget:` |
| TextView | inner margins are `top-margin`/`bottom-margin`/`left-margin`/`right-margin`; `wrap-mode: word/char`; `editable: false`; buffer via `buffer: Gtk.TextBuffer {}` |
| GtkSource.View | `auto-indent`, `indent-width`, `show-line-numbers`, `monospace`; `buffer: GtkSource.Buffer { highlight-syntax: true; }` |
| Picture | `can-shrink: true`, `content-fit: fill/contain/cover/scale_down` |
| Image | `icon-name` + `icon-size: normal/large` or `pixel-size: N`; classes `icon-dropshadow`, `lowres-icon` |
| Scale | requires `adjustment:`; `draw-value`, `show-fill-level`; vertical via `orientation: vertical` |
| SpinButton | requires `adjustment:`; `climb-rate`, `wrap: true`, vertical orientation OK |
| CheckButton | checkbox; radio via `group:` chain; `inconsistent: true` for mixed state |
| ToggleButton | `active: true`; `group:` makes members radio-like; combine with `"linked"` Box |
| Switch | `active`, `sensitive: false` for disabled |
| Stack / StackPage | `transition-type: crossfade/slide_left_right`; pages declare `name`, `title`, `child:` |
| Revealer | `transition-duration` (ms), `transition-type: slide_up/crossfade` |
| Overlay | base child + `[overlay]` children; toolbar overlay classes `"toolbar" "osd"` |
| ScrolledWindow | `has-frame: true`, `hscrollbar-policy: never`, `propagate-natural-height: true`, `max-content-height` |
| ListView / GridView / ColumnView | set `factory: SignalListItemFactory {}` or `BuilderListItemFactory { template ListItem { ... } }`; ColumnViewColumns also need factories; sections via `header-factory:` |
| DropDown | `model: StringList {}`, `enable-search: true` |
| Adw.Clamp | `maximum-size`, `tightening-threshold` |
| Adw.HeaderBar | `title-widget: Adw.WindowTitle {}` or `Adw.ViewSwitcher`; `[start]`/`[end]` slots |
| Adw.ToolbarView | `[top]`/`[bottom]` bars, `content:`, `top-bar-style: raised` |
| Adw.NavigationView | children are `Adw.NavigationPage { title, ... }` |
| Adw.NavigationSplitView | `sidebar:`/`content:` are tagged `Adw.NavigationPage`s |
| Adw.OverlaySplitView | `sidebar:`/`content:`, `show-sidebar: bind toggle.active` |
| Adw.TabView / TabBar / TabOverview | tie via `view: tab_view`; page is `Adw.TabPage { title, child: }` |
| Adw.Dialog | put `Adw.ToolbarView` + `Adw.HeaderBar` inside; `presentation-mode: bind combo_row.selected as <Adw.DialogPresentationMode>;` |
| Adw.AlertDialog / Adw.MessageDialog | `responses [...]` block with flags `destructive`/`suggested`/`disabled` |
| Adw.Avatar | `size`, `show-initials: true`, `text: _("Jay Doe")` |
| Adw.SplitButton | `label`/`icon-name` + `menu-model:` or `popover:` |
| Adw.ButtonContent | icon+label helper inside Button/MenuButton/ToggleButton |
| Adw.Banner | `title`, `button-label`, `revealed`, `use-markup` |
| Adw.BottomSheet | `bottom-bar:`, `content:`, `sheet:`; toggles for `open`, `can-open`, `can-close`, `full-width`, `modal`, `show-drag-handle` |
| Adw.Spinner | sized via `width-request`/`height-request`; always animating (Gtk.Spinner only if you need `spin()` start/stop) |
| MenuButton | `menu-model:` xor `popover:`; `label` or `icon-name`; `primary: true` for app menu; `direction` bindable |
| Popover / PopoverMenu | `has-arrow: false` for flat sheets; PopoverMenu needs `menu-model:` |
| ColorDialogButton / FontDialogButton | share one `dialog:` object; `rgba: "#e01b24"`; Font: `use-font`/`use-size` |
| FileFilter | top-level `mime-types ["image/png", ...]` list |
| LevelBar | `mode: continuous/discrete`, `min-value`, `max-value`, `value` |
| ProgressBar | `fraction: 0.2`, `show-text`, `pulse-step`, `inverted` |
| Video / MediaControls | `autoplay`, `loop` |
| Calendar | `show-day-names`, `show-week-numbers`, `show-heading`, `day` |
| ShortcutLabel | `accelerator: "<Super><Alt>s"` |
| Shumate.SimpleMap | `show-zoom-buttons: true`; markers as top-level `Shumate.Marker` |
| WebKit.WebView | `zoom-level: 0.8`; class `"view"` |
| Adw.Bin | `css-name: "button"` to reuse widget CSS for custom widgets; `accessible-role: toggle_button` |
| Adw.MultiLayoutView | layouts are `Adw.Layout { name: "x"; content: Widget { ... }; };`; shared children are `[slot-id]` blocks under the view; slots are `Adw.LayoutSlot { id: "slot-id"; }`; switch via breakpoint setter `view.layout-name: "x";` (since 1.8) |

## Gotchas

- Object-valued properties end with `;` after the closing brace:
  `content: Box { ... };`. Plain nested children get no semicolon.
- `template` blocks (`template ListItem { ... }`, `template $Name: Class { ... }`)
  close with `}` — no trailing `;`, same as bracket extension blocks
  (`strings [...]`, `marks [...]`, `responses [...]`). Only object-valued
  properties take the semicolon.
- Grid children **must** declare `layout { row: N; column: N; }` (integers) or
  they all pile up at 0,0.
- TextView/Text margin properties are `top-margin` etc., not the Widget margins.
- Every Scale, SpinButton and Adw.SpinRow needs an inline `Adjustment`.
- Radio groups: the first member keeps `active: true;`; every other member gets
  `group: first_id;`. Same pattern for CheckButton (radio look) and ToggleButton.
- `action-target` is a GVariant — strings need inner quotes: `"'content'"`.
- Breakpoint `setters` use dotted paths (`header_bar.title-widget: null;`) and
  conditions use `sp` units: `condition ("max-width: 550sp")`.
- Menus are declared top-level, never nested inside widgets.
- `styles [...]` is the idiomatic way to add CSS classes (there is no `class:`
  property; prefer it over the `css-classes` property). Never hand-style what
  an Adwaita class already covers
  (`"card"`, `"linked"`, `"toolbar"`, `"flat"`, `"osd"`, `"property"`, `"spacer"`,
  `"title-1"…"title-4"`, `"heading"`, `"body"`, `"caption"`, `"monospace"`,
  `"dim-label"`, `"boxed-list"`, `"boxed-list-separate"`, `"pill"`, `"circular"`,
  `"suggested-action"`, `"destructive-action"`, `"opaque"`, accent/success/warning/error).
- The `using Adw 1;` import has no minor version; `Gtk` is `4.0`.
- StringList items are plain values; mark translatable ones: `strings [_("Up"), _("Down")]`.
- Prefer `Adw.StatusPage` as a page root and `Adw.Clamp` around forms; the demos
  root almost everything in one of those two.
- Widgets referenced by bindings/groups/actions but populated by code can be
  declared as empty placeholders: `Label status_label {}`.
- Root choice matters: full-window demos root at `Adw.Window`/`Gtk.Window`;
  embeddable pages root at `Adw.StatusPage` or `Box`.
- Prefer high-level containers — `Adw.StatusPage` for page content, `Gtk.Stack`
  for switching views — over manual show/hide logic; hide implementation
  details behind widgets rather than code.

## Validation loop

1. Compile-check after every edit:
   `blueprint-compiler compile path/to/file.blp`
   (Python-only dependency; in Workbench projects: `make format` runs
   `workbench-cli format blueprint src/*/*.blp`).
2. Lint: `blueprint-compiler lint path/to/file.blp`.
3. Format: `blueprint-compiler format path/to/file.blp`.
4. Porting from GtkBuilder XML: `blueprint-compiler port` converts `.ui` files;
   `decompile` does the same non-interactively.
5. Re-check before finishing:
   - every referenced ID is defined exactly once (bindings, `group:`,
     `menu-model:`, `activatable-widget:`, `dialog:`),
   - radio `group:` chains point at the first member,
   - action names/targets match the handlers registered in code,
   - user-visible strings are wrapped in `_(...)`,
   - breakpoints reference real widget IDs declared in the same file.
