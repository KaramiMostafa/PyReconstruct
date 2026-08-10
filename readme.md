[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python 3.11](https://img.shields.io/badge/Python-3.11-blue.svg)](https://www.python.org/)

# Customized PyReconstruct

This branch extends [PyReconstruct](https://github.com/SynapseWeb/PyReconstruct)
with microscopy plug-ins for segmentation, DAPI tracking, mRNA ROI mapping,
expert review, and antibody-intensity analysis.

The customized application uses two repositories. They must be cloned beside
one another:

```text
GitHub/
├── PyReconstruct/
└── PyReconstruct_connector_tracking_plugin/
```

Both repositories must use the `cellpose-custom-model` branch.

## Customized features

- Cellpose-SAM segmentation using one or multiple image channels, built-in
  models, or a local custom checkpoint.
- Hungarian and Bayesian DAPI tracking across available sections.
- Separate DAPI, tracked-DAPI, anchor-mRNA, and mapped-mRNA ROI layers with
  optional labels.
- Local displacement-field propagation of anchor mRNA ROIs through tracked
  DAPI nuclei.
- Explicit expert feedback for mRNA↔DAPI associations, DAPI track links, and
  mapped mRNA ROIs.
- Validation against independent expert ROIs.
- Antibody-intensity CSVs, overlays, scatter plots, and summary reports.
- Flexible handling of missing sections and missing image/ROI inputs.

## Requirements for every operating system

| Requirement | Supported/recommended value |
|---|---|
| Python | **3.11** (do not use Python 3.14) |
| Environment manager | Miniconda, Anaconda, or Miniforge |
| Git | Recent Git with command-line access |
| RAM | 8 GB minimum; 16 GB or more recommended for Cellpose |
| Disk | Allow several GB for PyTorch, Qt, VTK, and model files |
| Repositories | Both customized repositories on the same branch |

GPU acceleration is optional. CPU mode is slower but is the easiest first
installation to verify. Install and test CPU mode before adding CUDA.

## macOS installation

### macOS requirements

- Install the Xcode command-line tools if Git is unavailable:

  ```bash
  xcode-select --install
  ```

- On Apple Silicon, use a native `arm64` Terminal and native Conda. Check with:

  ```bash
  uname -m
  python -c "import platform; print(platform.machine())"
  ```

  Both should report `arm64`. Do not mix Rosetta/x86 Python with arm64 Qt or
  PyTorch packages.

### Install on macOS

```bash
mkdir -p ~/GitHub/pyreconstruct-custom
cd ~/GitHub/pyreconstruct-custom

git clone --branch cellpose-custom-model https://github.com/KaramiMostafa/PyReconstruct.git
git clone --branch cellpose-custom-model https://github.com/KaramiMostafa/PyReconstruct_connector_tracking_plugin.git

conda create -n pyreconstruct-custom python=3.11 pip setuptools wheel -y
conda activate pyreconstruct-custom
python -m pip install --upgrade pip setuptools wheel
```

Apple Silicon:

```bash
python -m pip install "torch==2.5.1" "torchvision==0.20.1"
```

Intel Mac:

```bash
python -m pip install "torch==2.2.2" "torchvision==0.17.2"
```

Install both repositories:

```bash
python -m pip install -e ./PyReconstruct
python -m pip install -e ./PyReconstruct_connector_tracking_plugin
```

## Linux installation

### Linux requirements

Git and the Qt/OpenGL runtime libraries are required. For Ubuntu/Debian:

```bash
sudo apt update
sudo apt install -y git libgl1 libegl1 libxkbcommon-x11-0 libxcb-cursor0
```

Equivalent packages may have different names on Fedora, Rocky Linux, or other
distributions. A graphical desktop/X11 or Wayland session is required to show
the PyReconstruct interface.

### Install on Linux

```bash
mkdir -p ~/GitHub/pyreconstruct-custom
cd ~/GitHub/pyreconstruct-custom

git clone --branch cellpose-custom-model https://github.com/KaramiMostafa/PyReconstruct.git
git clone --branch cellpose-custom-model https://github.com/KaramiMostafa/PyReconstruct_connector_tracking_plugin.git

conda create -n pyreconstruct-custom python=3.11 pip setuptools wheel -y
conda activate pyreconstruct-custom
python -m pip install --upgrade pip setuptools wheel
```

For a reliable CPU installation:

```bash
python -m pip install --index-url https://download.pytorch.org/whl/cpu \
  "torch==2.5.1" "torchvision==0.20.1"
```

Then install the application and connector:

```bash
python -m pip install -e ./PyReconstruct
python -m pip install -e ./PyReconstruct_connector_tracking_plugin
```

For NVIDIA GPU use, install the PyTorch 2.5.1 wheel matching the machine's
driver/CUDA support from the [official PyTorch selector](https://pytorch.org/get-started/locally/)
before installing the connector. Do not install a second PyTorch build over a
working CPU environment.

## Windows installation

### Windows requirements

- Use **Anaconda Prompt** or a Windows Terminal profile where `conda` works.
- Install [Git for Windows](https://git-scm.com/download/win).
- Install the Microsoft [Visual C++ 2015–2022 Redistributable (x64)](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist).
  PyTorch may otherwise fail while loading `c10.dll` with `WinError 1114`.
- Do not use the system Python 3.14 installation.

### Install on Windows PowerShell

```powershell
cd $HOME
mkdir GitHub -ErrorAction SilentlyContinue
cd GitHub

git clone --branch cellpose-custom-model https://github.com/KaramiMostafa/PyReconstruct.git
git clone --branch cellpose-custom-model https://github.com/KaramiMostafa/PyReconstruct_connector_tracking_plugin.git

conda create -n pyreconstruct-custom python=3.11 pip setuptools wheel -y
conda activate pyreconstruct-custom
python -m pip install --upgrade pip setuptools wheel
```

Install the stable CPU build first:

```powershell
python -m pip install --index-url https://download.pytorch.org/whl/cpu `
  "torch==2.5.1" "torchvision==0.20.1"
```

Install both customized repositories from their parent folder:

```powershell
python -m pip install -e .\PyReconstruct
python -m pip install -e .\PyReconstruct_connector_tracking_plugin
```

For NVIDIA acceleration, use the PyTorch 2.5.1 command generated by the
[official PyTorch selector](https://pytorch.org/get-started/locally/) instead
of the CPU command.

If `conda activate` is unavailable in PowerShell, run `conda init powershell`,
close every Terminal window, and open it again.

## Verify the installation

Run these checks while `pyreconstruct-custom` is activated:

```bash
python --version
python -c "import PyReconstruct; print(PyReconstruct.__file__)"
python -c "import pyrecon_connector; print(pyrecon_connector.__file__)"
python -c "import torch, torchvision, cellpose; print(torch.__version__, torchvision.__version__)"
```

Expected results:

- Python reports `3.11.x`.
- The first two paths point into the two cloned repositories.
- PyTorch, torchvision, and Cellpose import without errors.

## Launch

From any directory after activating the environment:

```bash
python -m PyReconstruct.run
```

Alternatively, from the PyReconstruct repository:

```bash
python PyReconstruct/run.py
```

Open **Plug-In**. The first submenu should be
**⚠ Expert feedback (HIGH RISK)**, followed by Tracking, Segmentation,
Channels/overlays, and Multiplex mRNA mapping.

## Updating an existing installation

macOS/Linux:

```bash
conda activate pyreconstruct-custom
git -C PyReconstruct switch cellpose-custom-model
git -C PyReconstruct pull --ff-only origin cellpose-custom-model
git -C PyReconstruct_connector_tracking_plugin switch cellpose-custom-model
git -C PyReconstruct_connector_tracking_plugin pull --ff-only origin cellpose-custom-model
python -m pip install -e ./PyReconstruct
python -m pip install -e ./PyReconstruct_connector_tracking_plugin
```

PowerShell uses the same commands; replace `./` with `.\` if desired.

## Troubleshooting

### Plug-In menu is missing

Confirm both the branch and imported source path:

```bash
git -C PyReconstruct branch --show-current
python -c "import PyReconstruct; print(PyReconstruct.__file__)"
```

The branch must be `cellpose-custom-model`, and the path must point to the
clone—not an old package under `site-packages`.

### `No module named 'torchvision'`

Activate the correct environment and reinstall the connector:

```bash
conda activate pyreconstruct-custom
python -m pip install -e ./PyReconstruct_connector_tracking_plugin
```

### Windows `c10.dll` or `WinError 1114`

Install/repair the Microsoft Visual C++ x64 Redistributable, restart Windows,
activate the environment, and reinstall the matching CPU pair:

```powershell
python -m pip uninstall -y torch torchvision
python -m pip install --index-url https://download.pytorch.org/whl/cpu `
  "torch==2.5.1" "torchvision==0.20.1"
```

### Qt reports an incompatible processor

The Python environment and Qt wheel have different CPU architectures. Delete
and recreate the Conda environment from a native Terminal. On Apple Silicon,
both architecture checks in the macOS section must report `arm64`.

### Clean environment recreation

```bash
conda deactivate
conda env remove -n pyreconstruct-custom -y
conda create -n pyreconstruct-custom python=3.11 pip setuptools wheel -y
```

Then repeat the appropriate OS installation section.

## Typical multiplex workflow

1. Open or create the image series.
2. Import separate DAPI and mRNA ROI folders, or segment them with distinct
   prefixes such as `dapi_` and `rna_`.
3. Track only DAPI ROIs.
4. Map anchor mRNA ROIs through the DAPI tracks.
5. Review low-confidence mappings and record expert feedback carefully.
6. Re-run tracking/mapping with saved feedback enabled.
7. Optionally validate against independent expert ROIs and measure antibody
   intensity.

Feedback is stored beside the `.jser` in
`<series>.multiplex_feedback.json`. A wrong correction can affect many mapped
ROIs, so always verify both cell identities and section numbers.

## Development and commit messages

This customized branch follows [Conventional Commits 1.0.0](https://www.conventionalcommits.org/en/v1.0.0/):

```text
type(scope): short description
```

Examples:

```text
feat(mapping): add displacement-field fallback
fix(cellpose): validate selected channel indexes
docs(install): clarify Windows DLL requirements
test(feedback): cover incorrect DAPI track links
```

Enable the repository's local commit-message hook once per clone:

```bash
git config core.hooksPath .githooks
```

GitHub Actions also validates every customized-branch commit. See
[CONTRIBUTING.md](CONTRIBUTING.md) for the allowed format and breaking-change
syntax.

## Upstream documentation and citation

The upstream user guide is available in the
[PyReconstruct wiki](https://github.com/SynapseWeb/PyReconstruct/wiki).

If you use PyReconstruct in published work, cite:

```bibtex
@article{Chirillo2025,
  title = {{PyReconstruct}: {A} fully open-source, collaborative successor to {Reconstruct}},
  author = {Chirillo, Michael A. and Falco, Julian N. and Musslewhite, Michael D. and Lindsey, Larry F. and Harris, Kristen M.},
  journal = {Proceedings of the National Academy of Sciences},
  volume = {122},
  number = {31},
  pages = {e2505822122},
  year = {2025},
  doi = {10.1073/pnas.2505822122}
}
```

## License

PyReconstruct is distributed under the GNU GPL v3. See [license.md](license.md).
