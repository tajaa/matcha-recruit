# Beetlejuse iOS Icon Ideas

The current icon is two orange chat bubbles. It matches the original feedback
concept, but it does not give Beetlejuse a memorable character. The next icon
should make the beetle the hero and let the feedback/rewards meaning live in
the product UI.

## Recommended Direction: Marigold Beetle

Visual mockups:

- [Marigold Beetle](docs/design/tellus-ios-icons/marigold-beetle.svg)
- [Calavera Shell](docs/design/tellus-ios-icons/calavera-shell.svg)
- [Papel Picado Beetle](docs/design/tellus-ios-icons/papel-picado-beetle.svg)
- [Comparison sheet](docs/design/tellus-ios-icons/comparison.svg)

A friendly, front-facing beetle centered inside the iOS app-icon field.

- Rounded beetle shell in coral, marigold, and soft orange
- Two large shell panels divided by a clean vertical seam
- Four-petal marigold motif on the shell, small enough to survive at 60px
- Short curved antennae and simple dot eyes for personality
- Deep plum-black background with a soft pastel halo
- Tiny star or point-shaped highlight on one shell panel

This is the strongest direction because it is identifiable without text, feels
like a real mascot rather than an abstract badge, and can connect naturally to
the existing ember palette.

## Other Directions

### 1. Calavera Shell

A beetle viewed from above with decorative floral shell markings inspired by
Día de los Muertos sugar-art patterns.

- Keep the beetle silhouette unmistakable
- Use floral eye-like markings only on the shell, not a literal skull face
- Add a small marigold center and symmetrical linework
- Use cream, lilac, coral, and marigold against midnight

This gives the icon the strongest Día de los Muertos reference, but it needs
restraint. Too much linework will disappear at small sizes.

### 2. Papel Picado Beetle

A simplified beetle silhouette formed from a festive papel picado cut-paper
pattern.

- Solid pastel beetle body
- Two or three meaningful cutouts: flower, star, and heart
- Warm cream background with coral and teal accents
- A subtle paper edge or scallop shape around the body

This is more graphic and editorial. It would pair well with the receipt/ticket
language in the landing screen.

### 3. Marigold Night Parade

A luminous beetle walking through a small arc of marigold petals.

- Dark near-black background
- Coral-orange beetle with a soft pastel rim light
- Three floating marigold petals or stars
- No literal chat bubble or reward coin

This keeps continuity with the current dark app while making the icon warmer
and more alive.

### 4. Pastel Jewel Beetle

A jewel beetle rendered like a tiny enamel pin or papel-maché ornament.

- Mint, lavender, peach, and butter-yellow shell panels
- Thick dark outline for small-size legibility
- One simple marigold flower behind the shell
- Slightly asymmetrical pose to feel handmade

This is the most playful option and would stand apart from typical orange
fintech/rewards icons.

## Palette Candidates

Use a small, controlled palette instead of a rainbow gradient:

| Role | Color | Hex |
| --- | --- | --- |
| Night ground | Near-black plum | `#0D0912` |
| Marigold | Warm yellow | `#F6B544` |
| Coral | Pastel coral | `#F27B73` |
| Peach | Shell highlight | `#FFB56B` |
| Lilac | Floral accent | `#B9A7E8` |
| Mint | Optional cool counterpoint | `#8FD8C8` |
| Cream | Paper/petal detail | `#FFF0D2` |

The existing `TU.ember` orange can remain the app's interaction accent while
the icon gains coral, lilac, and marigold character.

## iOS Icon Rules

- Design at 1024x1024, but check the result at 60x60 and 32x32.
- Keep the beetle body inside roughly the central 70% of the canvas.
- Use a strong silhouette before adding decoration.
- Avoid text, chat bubbles, QR codes, tiny legs, and thin linework.
- Avoid a transparent canvas; let the iOS mask handle the rounded corners.
- Test the icon on light mode, dark mode, and a noisy home-screen wallpaper.
- Make the eyes and shell seam readable without relying on a border.
- Keep the visual reference celebratory and respectful; avoid turning sacred
  imagery into generic spooky decoration.

## Suggested First Pass

Create three 1024px sketches side by side:

1. Marigold Beetle: symmetrical mascot, dark ground
2. Calavera Shell: floral shell markings, cream ground
3. Papel Picado Beetle: cut-paper silhouette, coral ground

Review them at actual home-screen size before choosing detail. My pick is the
Marigold Beetle with the Calavera Shell's restrained floral geometry: a
distinctive Beetlejuse mascot with cultural texture, not a decorated chat icon.

## Asset Plan

The current XcodeGen project already uses one universal asset at:

`platforms/ios/TellUs/Resources/Assets.xcassets/AppIcon.appiconset/AppIcon.png`

The first implementation can replace that PNG without changing the asset
catalog structure. If alternate light/dark variants are eventually needed,
move to an appearance-aware asset catalog only after the core silhouette is
proven.
