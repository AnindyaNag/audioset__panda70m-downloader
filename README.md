# AudioSet & Panda-70M Video Clip Downloader

Scripts to download video clips from two large-scale video datasets — **AudioSet** and **Panda-70M** — using `yt-dlp` and `ffmpeg`.

Both scripts:
- Download each YouTube video **once**
- Cut all clips from it using ffmpeg
- Save each clip as a separate `.mp4` with audio
- Skip already-downloaded clips — safe to resume if interrupted

---

## Downloading Dataset CSV Files

### AudioSet CSV Files → place in `audioset/` folder

Download the files below and put them in the `audioset/` folder:

| File | Download Link |
|---|---|
| `audioset_eval_segments.csv` | http://storage.googleapis.com/us_audioset/youtube_corpus/v1/csv/eval_segments.csv |
| `audioset_balanced_train_segments.csv` | http://storage.googleapis.com/us_audioset/youtube_corpus/v1/csv/balanced_train_segments.csv |
| `audioset_unbalanced_train_segments.csv` | http://storage.googleapis.com/us_audioset/youtube_corpus/v1/csv/unbalanced_train_segments.csv |
| `audioset_class_labels_indices.csv` | http://storage.googleapis.com/us_audioset/youtube_corpus/v1/csv/class_labels_indices.csv |

### Panda-70M CSV Files → place in `Panda70m/` folder

Go to **[https://github.com/snap-research/Panda-70M](https://github.com/snap-research/Panda-70M)** and download the CSV files from the dataset table:

| File | Size | Description |
|---|---|---|
| `panda70m_testing_with_additional_annotation.csv` | ~1.2 MB | Testing split — 6,000 clips, 2,000 videos |
| `panda70m_validation_with_additional_annotation.csv` | ~1.2 MB | Validation split — 6,000 clips, 2,000 videos |
| `panda70m_training_2m.csv` | ~118 MB | Training — 2.4M clips (quick prototyping) |
| `panda70m_training_10m.csv` | ~504 MB | Training — 10.5M clips |
| `panda70m_training_full.csv` | ~2.73 GB | Full training — 70.7M clips |

After downloading, place all files in the `Panda70m/` folder.

## Requirements

### Windows

**1. Python 3.10+**
https://www.python.org/downloads/

**2. ffmpeg**
```powershell
winget install ffmpeg
```

**3. Deno** (required for YouTube format unlocking)
```powershell
winget install DenoLand.Deno
```
Restart your terminal after installing both.

**4. Python packages**
```powershell
pip install -r requirements.txt
```

---

### Ubuntu / Linux

Run these commands **one by one**:

**Step 1 — Create & activate conda environment (Python 3.10)**
```bash
conda env list | grep -q 'audioset' || conda create -n audioset python=3.10 -y
conda activate audioset
```

**Step 2 — ffmpeg**
```bash
ffmpeg -version 2>/dev/null || { pip install imageio-ffmpeg && mkdir -p ~/bin && cp $(python3 -c "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())") ~/bin/ffmpeg && grep -q 'HOME/bin' ~/.bashrc || echo 'export PATH="$HOME/bin:$PATH"' >> ~/.bashrc && export PATH="$HOME/bin:$PATH"; }
```

**Step 3 — Deno**
```bash
deno --version 2>/dev/null || curl -fsSL https://deno.land/install.sh | sh
grep -q 'deno/bin' ~/.bashrc || echo 'export PATH="$HOME/.deno/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
conda activate audioset
```

**Step 4 — Python packages**
```bash
pip install -r requirements.txt
```

---

## Cookie Setup (required to bypass YouTube bot detection)

1. Install the **"Get cookies.txt LOCALLY"** Chrome extension:
   https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc

2. Go to **youtube.com** while logged into your Google account

3. Click the extension icon → **Export** → save as `cookies.txt`

4. Place `cookies.txt` in the same folder as the scripts



> **Before running any script**, activate the conda environment:
> ```bash
> conda activate audioset
> ```

## Dataset 1 — AudioSet

**Script:** `download_audioset.py`
**Source:** [AudioSet](https://research.google.com/audioset/)
**CSV format:** `YTID, start_seconds, end_seconds, positive_labels` (3 comment lines at top, then data)

### Available CSVs

| File | Description |
|---|---|
| `audioset/audioset_eval_segments.csv` | Evaluation split |
| `audioset/audioset_balanced_train_segments.csv` | Balanced training split |
| `audioset/audioset_unbalanced_train_segments.csv` | Unbalanced training split (large) |

### Usage

```bash
# Test run — first 10 videos (eval CSV)
python download_audioset.py --n_videos 10

# Use the balanced training CSV
python download_audioset.py --csv audioset/audioset_balanced_train_segments.csv --n_videos 10

# Download all videos from a CSV
python download_audioset.py --csv audioset/audioset_balanced_train_segments.csv --n_videos 0

# Custom output folder
python download_audioset.py --csv audioset/audioset_eval_segments.csv --output_dir my_audioset_clips --n_videos 100

# Custom cookies path
python download_audioset.py --csv audioset/audioset_eval_segments.csv --cookies /path/to/cookies.txt
```


## Dataset 2 — Panda-70M

**Script:** `download_panda70m.py`
**Source:** [Panda-70M dataset](https://github.com/snap-research/Panda-70M)
**CSV format:** each row = one YouTube video with multiple clip segments (timestamps + captions)


### Usage

```bash
# Test run — first 10 videos (testing CSV)
python download_panda70m.py --n_videos 10

# Use the 2M training CSV
python download_panda70m.py --csv Panda70m/panda70m_training_2m.csv --n_videos 10

# Download all videos from a CSV
python download_panda70m.py --csv Panda70m/panda70m_training_2m.csv --n_videos 0

# Custom output folder
python download_panda70m.py --csv Panda70m/panda70m_training_2m.csv --output_dir my_clips --n_videos 100

# Custom cookies path
python download_panda70m.py --csv Panda70m/panda70m_training_2m.csv --cookies /path/to/cookies.txt
```

## Notes

- Some videos may be **private or deleted** from YouTube — those are skipped with a `[FAIL]` log
- If interrupted, re-run the same command — already downloaded clips are skipped automatically
- Disk space estimates:
  - Panda-70M testing set (~2000 videos): ~20–60 GB
  - AudioSet eval split: ~5–15 GB
  - Training sets: significantly more
- Each AudioSet clip is ~10 seconds; Panda-70M clips average 5–50 seconds
