> Historical source snapshot from [infoedutechos/ODEI-Multi-Ecosystem/docs/ecosystem/ODEI_SHARED_DROPDOWN_NAV.md](https://github.com/infoedutechos/ODEI-Multi-Ecosystem/blob/b9878e8dcc34942ec10fa5fddea34028a5456b42/docs/ecosystem/ODEI_SHARED_DROPDOWN_NAV.md). Imported from source commit `b9878e8dcc34942ec10fa5fddea34028a5456b42`. Credentials and private-key material, if present, have been redacted. This is historical reference material, not evidence of target implementation.

---

# ODEI Shared Dropdown Navigation

The reusable ODEI dropdown navigation lives at
`apps/_shared/odei-nav/`. It provides the behavior and accessible structure
for product marketing headers while letting each product retain its own visual
brand and its own links.

## Syncing

```powershell
npm run sync:nav
```

The command copies `odei-nav.css` and `odei-nav.js` to each product's
`/odei-nav/` directory and loads them on marketing home pages. It is
idempotent. Run it after changing the shared kit.

## Product hook API

The kit enhances `nav.odei-nav` / `[data-odei-nav]` and exposes:

```js
window.ODEINav.render(navElement, {
  label: "Product primary navigation",
  mobile: "drawer",
  items: [
    { label: "Home", href: "/" },
    {
      label: "Product",
      groups: [{
        label: "Explore",
        links: [{ label: "Overview", href: "/product.html" }]
      }]
    }
  ]
});
```

An item with `links` creates a one-column dropdown; `groups` creates a
multi-column panel. `data-odei-nav="auto"` safely groups existing top-level
header links for product sites that have not supplied a custom hook.

## Interaction and ARIA

- Fine-pointer desktop navigation supports hover and keyboard focus.
- Click/tap toggles every dropdown; Escape closes it and restores focus.
- Outside pointer presses close it.
- The panel is nested in its dropdown wrapper, preserving the pointer bridge
  between trigger and panel.
- On narrow screens, use `mobile: "drawer"` for stacked tap targets.
- Buttons expose `aria-haspopup`, `aria-expanded`, and `aria-controls`;
  panels and their links use `menu` and `menuitem` roles.

## Theming and ownership

The kit inherits existing product variables (`--bg`, `--fg`, `--muted`,
`--accent`, `--line`) and can be overridden with `--odei-nav-*` variables.
It deliberately does not claim every product has the same destinations:
Wallet, Academy, Exchange, Studio, and every other product own their link
labels and URLs. The shared layer only standardizes behavior and semantics.

## Current adoption

Custom product hooks: Academy, Wallet, Exchange, Studio, and the
Multi-Ecosystem master site. The sync layer enables automatic grouping for
other marketing homes, including AI, Chain, Foundation, Pay, Communications,
Core, DeFi, DEX, and additional product shells.
