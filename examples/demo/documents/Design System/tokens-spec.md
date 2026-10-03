# Design tokens — naming spec

Tokens are named `category.role.state`, for example `color.surface.hover` or
`space.inset.large`. Raw values (hex codes, pixel sizes) live only in the base layer; every
component references a semantic token, never a raw value.

Accessibility rule: every text/background token pair ships with its contrast ratio, and a pair
below 4.5:1 fails the build.
