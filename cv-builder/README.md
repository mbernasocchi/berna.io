# CV builder

Edit the files in `content/` and run `python3 build.py`. The PDFs are written to `../download/`; temporary HTML files are removed after each successful build.

## Format of a content file

```
---
file: CV_Marco_Bernasocchi_short      output filename (without .pdf)
title: Marco Bernasocchi
tag: one line under the name
links:
  - one contact line per item
---

# Sidebar
## Section label
### Optional sub-heading
Text. End a line with two spaces for a line break.  
Next line.

# Main
## Section heading
A paragraph.

- a bullet
- another

## Experience
### Organisation
*Role · dates*            italic line right after ### = the meta line
Description paragraph.
- bullet
```

Inline formatting: `**bold**` and `*italic*`. Nothing else is interpreted.

## Shared blocks

`content/_shared.md` holds text that several CVs use (contact lines, languages, education, qualifications). A block starts with `::: name` and runs to the next `:::`. Put `{{name}}` on its own line in a CV file to insert it, in the front matter or in the body. Edit the block once, every CV picks it up on the next build.

## Requirements

- Python 3 and a Chromium binary (`apt install chromium` or set `CHROMIUM=/path/to/chrome`)
- Inter installed as a system font; Fraunces is bundled in `fonts/`
