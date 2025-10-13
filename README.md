# Music Library Tool - Prepare my local music library for use with [Auxio](https://github.com/OxygenCobalt/Auxio/)

This repository contains a small Python scipt I wrote to prepare my huge local music library for use on my mobile phone with [Auxio](https://github.com/OxygenCobalt/Auxio/). It performs the following operations:
- Validation of the music tags: Ensures all music files contain proper tags (artist, album, title, genre, etc.) following [Auxio’s tag format conventions](https://github.com/OxygenCobalt/Auxio/wiki/Supported-Metadata). Invalid or missing tags are reported.
- Transcoding & Loudness Normalization: Use FFMPEG to convert different file formats to Opus (for disk space saving), while also performing loudness normalization (I prefer baking it into the music file over ReplayGain tags)
- Playlists Generation: Creates .m3u playlists based tags.

At the end of the script, the files are stored in an output folder, ready to be copyied to the phone.

Note: This is a tool built for my specific personal needs. It will likely need significant adaptation to fit other setups. I guess it demonstrates calling ffmpeg efficiently from Python in parallel. If that is useful to you, take a peak!
