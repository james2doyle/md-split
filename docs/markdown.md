# Markdown support

The preview uses the composite GFM plugin from `mdit-py-plugins`:

- CommonMark blocks and inline syntax
- Tables with per-column alignment
- Strikethrough with `~~` (and single tildes)
- GFM autolinks for bare `http://`, `https://`, `www.` and email addresses
- Task lists with disabled check boxes in the preview
- GitHub alerts (`> [!NOTE]`, `[!TIP]`, `[!IMPORTANT]`, `[!WARNING]`,
  `[!CAUTION]`)
- Footnotes and block quotes
- Fenced code blocks with language labels and copy buttons
- Local and remote images
- Underline with `<u>...</u>` (the only inline raw HTML tag interpreted)

Pressing Return inside a bullet, ordered, task, or nested list continues the
list with the next marker; pressing Return on an empty item exits the list.

Relative links and images are resolved against the open document's directory.
Local images are decoded asynchronously with size and pixel limits. Remote
images are disabled by default: enable **Load Remote Images** in the main menu
or Preferences to fetch public HTTP(S) images, subject to byte, pixel, timeout,
and cache limits.

See [architecture.md](architecture.md#preview-rendering) for the parser and
renderer implementation, and [security.md](security.md) for link and image
policy.
