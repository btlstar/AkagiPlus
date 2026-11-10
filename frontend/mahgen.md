# Mahjong tile sizing

`src/components/Mahgen.tsx` wraps the `mah-gen` component. Sizing and image
updates are managed by `src/lib/mahgenRegistry.ts`.

- `mah-gen` renders one asynchronous image inside an open shadow root.
- Set pixel dimensions on both the host and its image. Percentage sizing
  can create a circular dependency between image and container width.
- Register a container whose width or height is independent of the image.
  Avoid observing a content-sized container that changes with the tiles.
- Reapply sizing after the image loads and when its container resizes.
- Hide empty sequences instead of displaying an empty sized image box.
- Use `registerMahgen`, `setMahgenSeq` and `unregisterMahgen` for lifecycle
  management. Remove registry entries when a widget unmounts.

The registry defines size modes per widget, including width-based dashboard
tiles and height-based overlay rows. Keep these constraints when changing
scrolling or responsive layouts.
