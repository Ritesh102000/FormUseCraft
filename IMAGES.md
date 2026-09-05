<!--
Formcraft by catapultaiwork — https://catapultaiwork.com
Source-available with required attribution; see LICENSE.
Personal and commercial use is allowed. Every hosted form must retain the small
"Powered by catapultaiwork" link. There is no builder setting to hide it.
People controlling the source can edit it, but the license requires this credit.
This is a custom attribution license, not standard MIT or OSI-approved open source.
-->

# Optional images

The public edition ships without bundled raster art, customer portraits, or
logos whose redistribution rights have not been established. Forms and the
builder work without images. Empty image slots are omitted from normal pages;
`/admin/media` shows their names and suggested dimensions.

You may add images you own or have permission to distribute under
`web/static/img/`:

| Filename stem | Purpose | Suggested dimensions |
| --- | --- | --- |
| `login-panel` | Local sign-in illustration | 1200×1600 |
| `responses-empty` | Empty responses illustration | 800×600 |
| `form-success` | Submission confirmation illustration | 600×600 |
| `og-default` | Generic form link preview | 1200×630 |

Supported extensions: `.webp`, `.png`, `.jpg`, `.jpeg`, `.svg`, `.avif`.
Redeploy after changing assets. Keep personal response data out of link-preview
art. Add the appropriate attribution/license notices for any third-party art.
Your organization images do not replace the provider credit required by LICENSE.
