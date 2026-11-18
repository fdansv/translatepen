# Manga mode for Anki photos

Manga mode attaches a small photo when saving a word to Anki. The scanner's
close-focus camera can produce grainy, dark or blurry pictures. Think of the
photo as a page reminder. Hold the pen close to a detail you want to remember.

## Set up and try it

1. Use the supported MSE09 and exact executable checksum in [setup](setup.md).
   Build the native plugin from this branch and stage it with the matching app.
   The guided installer includes the camera helper. The pen needs `v4l2-ctl`,
   `/dev/video0`, and the camera LED exposed by this model. Run
   `command -v v4l2-ctl` on the pen before testing capture.
2. Configure the API with the [companion Anki adapter](https://github.com/fdansv/migaku-api/pull/1)
   and run a text-card test
   first. With the updated pen app open, wait for the **Manga OFF** button to
   appear. The button is available once the API reports Anki photo support.
3. Tap **Manga OFF**, scan and choose a word, then double-press **B**. Aim the
   tip during the four-second illuminated countdown. The picture is saved
   automatically and uploaded with the card when the server is available.
4. Check the note's **Screenshot** field in desktop Anki. For a phone check,
   wait for desktop media sync and then sync AnkiMobile.
5. Try cancelling a capture. The card stays in **Queue** with **Retake photo**.
   With Manga mode off, saving a new word uses the normal text-only path.

The photo queue survives restarts and can upload when the server returns.
After the pen has contacted a compatible server, the capture itself can finish
even if the connection drops. This PR keeps the upstream scan OCR setup.

## Capture and storage

The helper restores the camera light and any temporary format or exposure
settings after capture or cancellation. Advanced settings on the matching
device include `/userdata/translatepen/photo-full-resolution` containing
`1` to request 528×360, and `/userdata/translatepen/photo-exposure` with an
integer from 4 to 412. These settings are optional. Keep the pen at rest while
testing them. Resolution increases pixel count within the same view.

The pen holds unsent JPEGs and stops new captures if its storage budget is
reached. After a server confirms the card, the local photo becomes eligible for
cleanup after seven days. Anki stores its own copy.
