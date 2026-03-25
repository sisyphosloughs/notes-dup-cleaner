# Notes Dedup

**Notes Dedup** is a **duplicate finder** and **similarity analysis** tool for your personal notes. It helps you identify redundant files, compare similar content, and clean up your notes through a **web interface**.

## Features

* **Similarity Detection**: Find notes that are not just exact byte-copies but conceptually similar.
* **Parallel Processing**: Fully optimized using `multiprocessing.Pool` to utilize all available **CPU cores** for fast analysis.
* **Smart Filtering**: Includes a size-based pre-filter to instantly eliminate pairs that cannot be similar, saving computation time.
* **Interactive Web UI**: View your results in your browser via a local **web server**.
* **File Preview**: Use the **Quick-look functionality** via the **Eye** icon to inspect file content.
* **Side-by-Side Diff**: Select exactly two files and use the **Compare** feature to see a detailed difference analysis.
* **Media Control**: Optional exclusion of **images** from the similarity analysis.

## Installation

Ensure that you have `Python` installed. Clone the repository and install any necessary dependencies.

**Bash**
```bash
git clone [https://github.com/yourusername/notes-dedup.git](https://github.com/yourusername/notes-dedup.git)
cd notes-dedup
```

## Usage

Run the script by pointing it to your notes directory:

**Bash**
```bash
python notes_dedup.py /path/to/your/notes
```

## Advanced Options

| Option | Description | Default |
| :--- | :--- | :--- |
| `--threshold` | **Similarity threshold** in percent (0-100). | `85` |
| `--port` | Local **port** for the browser interface. | `8742` |
| `--no-images` | Exclude **image files** from the similarity analysis. | Disabled |

Example with custom threshold and port:

**Bash**
```bash
python notes_dedup.py /path/to/your/notes --threshold 80 --port 8765
```

## How it works

* **Scanning**: The tool scans the provided directory for note files.
* **Pre-filtering**: It ignores pairs with vast differences in **file size** to optimize performance.
* **Comparison**: It calculates the **similarity score** for the remaining pairs.
* **Review**: Open the provided local `URL` in your browser to manage, preview, and compare the detected duplicates.