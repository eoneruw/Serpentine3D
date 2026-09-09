# Trace over a picture

A photo or a blueprint in the model is the quickest way to get the
lines of a real thing in front of you. Serpentine3D keeps a picture as
an object: it sits on a layer, it is picked and moved like anything
else, and it shows whichever part of its image you frame.

## Put one in

Drag an image file (PNG, JPEG, TIFF, WebP) from your file browser onto
a viewport. It lands on that pane's construction plane at the drop
point — drop it on **Front** and it stands up facing you, on **Top** and
it lies flat — sized to about a third of the view. Or type `picture`,
give the file's path, and click two corners.

The picture is selected as it arrives. The gumball moves, rotates and
scales it; `scale` with a reference length sets it to a known size
(click the two ends of a wheelbase, type the real distance).

## Crop with the corners

A blueprint sheet usually has the front, side and top on one page. You
do not cut it up in an image editor: put the sheet in three times and
show a different part each time.

Select the picture and press **F10** (or the **Crop corners** button in
Properties). The whole image ghosts in and four blue points mark the
window it shows. Drag a corner and the two edges it owns follow; the
image itself stays where it is. **F11** hides the corners again, and
**Whole image** in Properties shows all of it. Cmd-C, Cmd-V makes the
next copy.

Because a corner is a control point, everything that works on control
points works here: the gumball moves a held corner, `undo` takes a
crop back, and the Osnaps apply while you drag.

## See through it

The **Opacity** slider in Properties fades the picture so your curves
read over it. Lock its layer once the curves are down, and it stops
taking clicks.

## Where the pixels live

The drawing stores where the picture is and which file it shows, not
the pixels: move the image file and the picture goes blank until it is
found again, as in every modeller.
