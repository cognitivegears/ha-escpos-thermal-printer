# Calibration Wizard

A guided, print-and-answer wizard that measures four per-printer settings
and saves them to the entry's options — no manual trial-and-error with the
options form required.

**Start it from:** Settings → Devices & Services → your printer entry →
Configure → **"Calibrate printer (prints test pages)"**.

> **Not the same as `calibration_print`.** The `escpos_printer.calibration_print`
> service prints a one-off dither/threshold test sheet for tuning image
> options like `dither` and `threshold`. This wizard is a different,
> multi-step flow that measures and saves connection-level settings. See
> [Calibration print](images.md#calibration-print) in the Images guide for
> the service.

## What it measures

| Setting | Options-form equivalent | What it controls |
|---------|--------------------------|-------------------|
| Image implementation | "Image printing implementation" | Which ESC/POS image command is used (raster / column / graphics) |
| Paper width (pixels) | "Paper width in pixels" | Target width images are scaled to |
| Characters per line | "Characters per line" | Text wrap width in the printer's built-in font |
| Codepage | "Character encoding" | Character encoding used for text |

Every setting the wizard measures, you can also set by hand in the
options form — the wizard just automates the trial-and-error and writes
the result for you. Nothing is saved until you reach the final step and
choose **Save calibration**; running the wizard and closing it early, or
choosing **Discard**, changes nothing.

Budget roughly 15–20 cm of paper for a full run through all five steps.

Before printing anything, the wizard shows a confirmation screen
restating that paper cost and asking you to make sure paper is loaded —
choose "Start calibration" to proceed or "Cancel" to back out untouched.

## The five steps

### 1. Image implementation

The printer prints three numbered test patterns (a small checkerboard),
one per candidate implementation: raster, column, and graphics. A pattern
that printed cleanly looks like a crisp checkerboard; a failing one prints
stray letters, a blank gap, or nothing at all.

Check every pattern that printed cleanly, then **Continue**. If a pattern
looks wrong, use **Reprint the test page** to try again before deciding.

If **none** of the patterns printed cleanly, leave every box unchecked and
continue anyway — the width step is skipped, since it needs a working
image mode to print its bars with. The wizard moves straight to the
characters-per-line step.

### 2. Paper width (skipped if no pattern printed cleanly in step 1)

The printer prints five numbered bars at 384, 512, 576, 640, and 832
pixels wide, each labeled at its left edge. Bars wider than your printer's
true printable width get clipped to the same length as the widest bar
that fits — so several bars at the bottom of the page will look
identical. If the bars look like staircases rather than clean solid
blocks, your printer wraps rather than clips — choose "Not sure" instead.

Counting from the top, pick the **first bar that's the same length as the
bottom bar**. That bar's labeled width is your printer's true printable
width. If you can't tell, choose "Not sure / bars unclear" to leave the
paper width unmeasured.

### 3. Characters per line

The printer prints a short instruction line, then a 96-column ruler of
dots with the numbers `10`, `20`, `30`... embedded in it. The ruler is
longer than most printers are wide, so the leftover columns wrap onto one
or two extra lines — **ignore those; only the first ruler line matters**.

On that first line, find the **last complete number**, then **add 1 for
every dot printed after it**. For example, if the line ends with `40..`,
enter `42`. Enter `0` if you're not sure — that leaves the setting
unmeasured rather than guessing.

### 4. Codepage (skipped if your profile supports none of the candidates)

The printer prints one line per candidate codepage your selected printer
profile can actually switch to — each starts with its number and codepage
name (for example `1 CP858:`) followed by the sample text rendered under
that codepage. The checkbox label for each line shows the text that line
is *supposed* to look like (including any `?` substitutions for
characters the codepage can't represent).

Check every line whose printout matches its own expected text shown in
the label. If none match, or you'd rather leave the codepage unchanged,
choose **Skip this step**.

This step never appears at all if the selected profile doesn't support
any of the candidate codepages — there's nothing to test, so the wizard
skips straight to the summary.

### 5. Summary — save or discard

The final step lists everything measured so far and builds a **share
link**: a prefilled GitHub issue containing your measured results and a
draft `escpos-printer-db` profile entry. Enter your printer's model name
and choose **Update share link with my model** to personalize it, or
leave it as-is.

Choose one:

- **Save calibration** — merges the measured settings into the printer's
  options. Anything you didn't measure (skipped, left unclear, or never
  reached because an earlier step was skipped) is left untouched.
- **Discard (save nothing)** — closes the wizard without changing
  anything.

Saving closes the wizard, which takes the on-screen share link with it. If
at least one setting was measured, a persistent notification carrying the
same link is posted so you can still find it afterwards. A run where every
step was skipped or left unmeasured saves nothing and posts no
notification.

### Contributing your results

Submitting the share link's prefilled GitHub issue helps grow the bundled
printer database: every printer model that gets calibrated and shared
makes setup easier for the next owner of that same model, since their
profile will already have accurate width/codepage/implementation data
instead of falling back to generic defaults. See
[Contributing printer profiles](../CONTRIBUTING.md#contributing-printer-profiles)
for details.

## Manual fallback

If you'd rather measure by hand, or the wizard can't run (the printer
must be connected and the config entry loaded):

- **Printer self-test.** Hold the FEED button while powering the printer
  on. Most printers print a self-test sheet showing the model, interface
  type, and often the dots-per-line (printable width in pixels).
- **Two-bar width test.** Print the same source image once at
  `image_width: 576` and once at `image_width: 640`, with
  `auto_resize: false`. The source image must be **at least 640px wide** —
  images are only ever downscaled, never upscaled, so a narrower source
  would print identically at both settings regardless of the printer's
  true width, giving a false result.

  ```yaml
  service: escpos_printer.print_image
  data:
    image: /config/www/width_test.png  # 640px wide or larger
    image_width: 576
    auto_resize: false
  ```

  If both prints come out the same length, your printer's printable width
  is 576px; if the 640px print is visibly longer, it's 640px.

See [Configuration reference](configuration.md) for setting these values
by hand, and [Images guide](images.md) for the image-implementation
selector and reliability-profile settings the wizard doesn't touch.
