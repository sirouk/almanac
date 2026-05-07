# Vendored Terminal Emulator Assets

The Terminal dashboard plugin vendors these browser-side helper assets so the
plugin remains self-contained and does not depend on a CDN:

- `@xterm/xterm` 6.0.0, MIT license
- `@xterm/addon-fit` 0.11.0, MIT license

Only the runtime JavaScript and CSS files are included. Source maps and package
sources are intentionally omitted to keep the plugin bundle compact.
